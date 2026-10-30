# -*- mode: python ; coding: utf-8 -*-
# PyInstaller 配置：把桌面端 sidecar（界面服务 + 本机工具 + 内嵌 gateway）打成一个目录（onedir），
# 产物：<distpath>/soulprout-desktop-sidecar/soulprout-desktop-sidecar.exe + _internal/。
# 打包前需要先构建界面：desktop/ui 下 npm run build（产物 desktop/ui/dist）。

from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

sidecar_dir = Path(SPEC).resolve().parent
desktop_dir = sidecar_dir.parent
project_root = desktop_dir.parent
ui_dist = desktop_dir / "ui" / "dist"

if not (ui_dist / "index.html").exists():
    raise SystemExit(f"桌面界面尚未构建：{ui_dist}（先在 desktop/ui 下执行 npm run build）")

datas = [
    (str(ui_dist), "ui"),
    (str(project_root / "gateway" / "static"), "gateway/static"),
]
binaries = []
hiddenimports = (
    collect_submodules("gateway")
    + collect_submodules("soulprout_desktop")
    + [
        "uvicorn.logging",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.http.h11_impl",
        "uvicorn.protocols.websockets",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan",
        "uvicorn.lifespan.on",
        "websockets",
        "websockets.legacy",
        "websockets.legacy.server",
        "multipart",
        "certifi",
    ]
)

for pkg in ("fastapi", "uvicorn", "aiohttp", "cryptography", "pdfminer", "docx", "pptx", "openpyxl"):
    try:
        pkg_datas, pkg_binaries, pkg_hidden = collect_all(pkg)
        datas += pkg_datas
        binaries += pkg_binaries
        hiddenimports += pkg_hidden
    except Exception:
        pass

# lark_oapi 有一万多个生成出来的 API 模块：collect_all 会把它们的 .py 源码也原样塞进包里（和编进 PYZ 的那份重复），
# 白白多出上万个文件，拖慢安装。只收子模块（进 PYZ）和非 .py 的数据文件即可。
try:
    hiddenimports += collect_submodules("lark_oapi")
    datas += collect_data_files("lark_oapi")
except Exception:
    pass

a = Analysis(
    [str(sidecar_dir / "main.py")],
    pathex=[str(sidecar_dir), str(project_root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # 开发环境里常装着但桌面端用不到的大包，排除掉避免安装包膨胀
    excludes=["tkinter", "matplotlib", "scipy", "pandas", "IPython", "notebook", "pytest"],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

# 单目录（onedir）而不是单文件（onefile）：
# onefile 每次启动都要把全部内容（二百多 MB、上万个文件）解压到临时目录，冷启动要等二十多秒，
# 退出时进程被强杀，临时目录还清理不掉，越攒越多。onedir 在安装时一次性释放，启动直接加载。
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="soulprout-desktop-sidecar",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # UPX 压缩的 DLL 每次加载都要先解压，启动更慢
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="soulprout-desktop-sidecar",
)

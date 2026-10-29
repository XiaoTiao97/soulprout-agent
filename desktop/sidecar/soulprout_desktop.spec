# -*- mode: python ; coding: utf-8 -*-
# PyInstaller 配置：把桌面端 sidecar（界面服务 + 本机工具 + 内嵌 gateway）打成单个可执行文件。
# 打包前需要先构建界面：desktop/ui 下 npm run build（产物 desktop/ui/dist）。

from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

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

for pkg in ("lark_oapi", "fastapi", "uvicorn", "aiohttp", "cryptography", "pdfminer", "docx", "pptx", "openpyxl"):
    try:
        pkg_datas, pkg_binaries, pkg_hidden = collect_all(pkg)
        datas += pkg_datas
        binaries += pkg_binaries
        hiddenimports += pkg_hidden
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

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="soulprout-desktop-sidecar",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

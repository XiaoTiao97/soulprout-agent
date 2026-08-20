# Soulprout Gateway — 桌面应用（Tauri）

将微信、飞书等平台接入 Soulprout Agent 的跨平台桌面工具。  
用户**无需安装 Python 或任何依赖**，下载即用。

---

## 打包原理

```
soulprout-agent/
├── gateway/             ← Python 后端
│   ├── main.py          ← FastAPI + 平台适配器主入口
│   ├── chat_caller.py   ← 调用 Agent Chat，收集完整回复
│   ├── platforms/
│   │   ├── weixin.py    ← 个人微信适配器（参考 hermes-agent）
│   │   ├── feishu.py    ← 飞书 WebSocket 适配器（参考 hermes-agent）
│   │   └── wecom.py     ← 企业微信 WebSocket 适配器（参考 hermes-agent）
│   ├── static/
│   │   ├── index.html   ← 管理面板
│   │   ├── weixin.html  ← 微信扫码登录
│   │   ├── feishu.html  ← 飞书扫码 / 手动凭证
│   │   └── wecom.html   ← 企业微信扫码 / 手动凭证
│   └── gateway.spec     ← PyInstaller 打包配置
│
└── gateway-app/         ← Tauri 桌面外壳（Rust）
    ├── src-tauri/
    │   ├── binaries/
    │   │   └── gateway-x86_64-pc-windows-msvc.exe  ← PyInstaller 产物（构建后生成）
    │   ├── src/lib.rs   ← 启动 sidecar + 自动更新检查
    │   ├── src/main.rs  ← 桌面端入口
    │   └── tauri.conf.json
    ├── release/         ← 发布产物汇总（构建后生成，不入库）
    └── scripts/
        ├── build.ps1    ← 构建脚本
        └── release.ps1  ← 一键发版（构建 + 上传 OSS）
```

**打包流程：**
1. **PyInstaller** 把 `gateway/main.py` + 所有 Python 依赖 → 单个 `gateway.exe`  
2. `gateway.exe` 复制到 `src-tauri/binaries/`（Tauri sidecar 目录）  
3. **Tauri build** 把 Rust 外壳 + sidecar `gateway.exe` → 最终安装包（`.msi` / `.exe` / `.dmg`）

用户拿到安装包后，无需 Python，双击即可运行。

---

## 构建前提条件（仅开发者需要）

| 工具 | 用途 | 安装方式 |
|------|------|---------|
| Python 3.10+ | 运行 PyInstaller | https://python.org |
| PyInstaller | 打包 Python 为 exe | `pip install pyinstaller` |
| Rust + Cargo | 编译 Tauri | https://rustup.rs |
| Node.js 18+ | Tauri CLI | https://nodejs.org |

---

## 一键构建（Windows）

```powershell
# 在项目根目录执行：
.\gateway-app\scripts\build.ps1
```

脚本自动完成以下步骤：

| 步骤 | 内容 |
|------|------|
| Step 1 | `pip install -r gateway/requirements.txt` 安装依赖 |
| Step 2 | `pyinstaller gateway/gateway.spec` 打包 Python 为 gateway.exe |
| Step 3 | 复制 gateway.exe → `src-tauri/binaries/gateway-<target>.exe` |
| Step 4 | `npm install` 安装 Tauri CLI |
| Step 5 | `npm run build` 编译并打包 Tauri 安装程序 |
| Step 6 | 汇总产物到 `release/`，生成版本清单 `version.json` |

构建产物汇总在 `gateway-app/release/`，共三个文件：

```
gateway-app/release/
├── Soulprout-Gateway-0.1.1-setup.exe   ← 版本化安装包，自动更新下载用
├── Soulprout-Gateway-setup.exe         ← 固定名副本，前端下载按钮用
└── version.json                        ← 版本清单，客户端检测新版本用
```

> 平时发版不用直接跑 `build.ps1`，用 `release.ps1` 一条命令即可（见下节），它会调用 `build.ps1` 并自动上传 OSS。

---

## 发布新版本

### 一条命令搞定

```powershell
.\gateway-app\scripts\release.ps1 -Notes "修复微信断线重连问题"
```

脚本依次完成：版本号自动 +1 → 构建安装包 → 上传阿里云 OSS。跑完已安装的客户端下次启动就会提示更新。

`-Notes` 的内容会显示在用户的更新弹窗里，写用户看得懂的话。想指定版本号就加 `-Version 0.2.0`，不加则在当前版本上递增 patch（`0.1.1` → `0.1.2`）。只想构建不上传加 `-NoUpload`。

首次运行会生成 `gateway-app/.release.local.json` 模板，填入阿里云 AccessKey 即可，只需填一次。该文件已在 `.gitignore` 中，不会进仓库。建议为它单独建一个 RAM 用户，只授予这一个 bucket 的读写权限，别用主账号的 AccessKey。

上传工具 ossutil 由脚本首次运行时自动下载并校验，缓存在 `scripts/.tools/`，你不需要预先安装任何东西。

### 用户侧会发生什么

已安装的客户端启动 3 秒后会在后台读一次 OSS 上的 `version.json`，发现版本号比自己高就弹出原生对话框。点「立即更新」则下载新安装包、静默安装、自动启动新版本；点「稍后再说」则下次启动再问。

检查更新失败（断网、OSS 不可达、清单格式错误）只写日志，不影响 Gateway 正常使用。下载完成后才会停掉 gateway 进程，所以实际服务中断只有安装的几秒。

配置不会丢：NSIS 在升级模式下不执行卸载，`gateway_data/` 会完整保留，用户不需要重新扫码登录。

### OSS 上的文件布局

脚本会往 bucket 里写三个位置：

| 对象 | 缓存策略 | 用途 |
|------|---------|------|
| `Soulprout-Gateway-setup.exe` | `no-cache` | 前端下载按钮，每次覆盖 |
| `updates/<版本>/Soulprout-Gateway-<版本>-setup.exe` | 一年 | 自动更新下载，内容不变 |
| `updates/version.json` | `no-cache, no-store` | 版本清单，每次覆盖 |

清单必须禁用缓存，否则发了新版而客户端仍读到旧清单，会出现「明明传了新版但检测不到」且很难排查的情况。客户端请求时还会额外带一个时间戳参数兜底。清单**最后**上传，确保客户端读到新版本号时安装包已经在线。

`version.json` 的内容很简单，必要时可以手改后传上去：

```json
{
  "version": "0.1.2",
  "notes": "修复微信断线重连问题",
  "url": "https://soulprout-gateway-app.oss-cn-hongkong.aliyuncs.com/updates/0.1.2/Soulprout-Gateway-0.1.2-setup.exe",
  "pub_date": "2026-08-20T08:00:00Z"
}
```

### 上传失败后重试

构建要十几分钟，如果构建成功但上传失败（凭证过期、网络中断等），不用重新构建，直接重试上传：

```powershell
.\gateway-app\scripts\release.ps1 -UploadOnly
```

它会跳过构建，直接发布 `gateway-app/release/` 里已有的产物，版本号取 `tauri.conf.json` 当前值，并校验 `version.json` 里的版本号与之一致。

### 手动上传（不用脚本上传）

加 `-NoUpload` 只构建，然后把 `gateway-app/release/` 里的三个文件按上面表格传到 OSS 控制台对应位置即可。注意给 `version.json` 设置 `Cache-Control: no-cache, no-store`，并确认三个对象都是公共读。

### 首个带自动更新的版本仍需手动通知

目前已安装的客户端里没有更新检查逻辑，收不到推送。带自动更新的第一个版本发布后，还是要用原来的方式通知用户手动下载一次，从此之后才开始自动更新。

### 自定义地址

前端下载链接与更新检查地址可分别覆盖：

```env
# Web 构建时，前端下载按钮指向的地址
VITE_GATEWAY_DOWNLOAD_URL=https://your-cdn.example.com/Soulprout-Gateway-setup.exe
```

```powershell
# 写入 version.json 的 URL 前缀
$env:GATEWAY_UPDATE_BASE_URL = "https://your-cdn.example.com"
```

客户端读取清单的地址硬编码在 `src-tauri/src/lib.rs` 的 `UPDATE_MANIFEST_URL`，改地址时两处要一致。

---

## 跳过部分步骤

```powershell
# 跳过 pip install（依赖已装好）
.\gateway-app\scripts\build.ps1 -SkipDeps

# 跳过 PyInstaller（已有 dist/gateway.exe）
.\gateway-app\scripts\build.ps1 -SkipPyInstaller

# 只做 PyInstaller，不跑 tauri build
.\gateway-app\scripts\build.ps1 -SkipTauri
```

---

## 开发模式（不打包，直接调试）

Tauri dev 模式会自动用 `python gateway/main.py` 启动后端：

```bash
# 1. 先安装 Python 依赖
pip install -r gateway/requirements.txt

# 2. 安装 Node 依赖
cd gateway-app
npm install

# 3. 启动 Tauri 开发模式
npm run dev
```

或者只启动后端（不打开 Tauri 窗口）：

```bash
python gateway/main.py
# 然后浏览器打开 http://localhost:8082
```

---

## 用户使用流程

1. 下载安装包并安装
2. 打开 **Soulprout Gateway**，完成 Agent 账号登录
3. 在「接入平台」中选择平台：
   - **微信**：获取二维码 → 微信 App 扫描 → 确认登录
   - **飞书**：默认「扫码创建」→ 飞书 App 扫描；或切换「手动填写」App ID / Secret
   - **企业微信**：默认「扫码获取」→ 企业微信 App 扫描；或切换「手动填写」Bot ID / Secret
4. 完成！对应平台消息将自动转发给 Soulprout Agent 并回复

---

## 环境配置（可选）

在 `gateway/.env` 中可配置（参见 `gateway/.env.example`）：

```dotenv
# 管理界面端口（默认 8082）
GATEWAY_WEB_PORT=8082

# 飞书（可选，通常通过 Web UI 配置）
# FEISHU_APP_ID=cli_xxx
# FEISHU_APP_SECRET=secret_xxx
# FEISHU_DOMAIN=feishu
```

微信凭证保存在 `gateway_data/weixin/`，飞书凭证保存在 `gateway_data/feishu/config.json`，企业微信凭证保存在 `gateway_data/wecom/config.json`，重启无需重新配置。

---

## 参考

- 微信 iLink Bot API 接入参考：[hermes-agent](https://github.com/NousResearch/hermes-agent)
- 飞书 WebSocket 长连接接入参考：[hermes-agent `gateway/platforms/feishu.py`](https://github.com/NousResearch/hermes-agent/blob/main/gateway/platforms/feishu.py)
- 企业微信 WebSocket 长连接接入参考：[hermes-agent `gateway/platforms/wecom.py`](https://github.com/NousResearch/hermes-agent/blob/main/gateway/platforms/wecom.py)
- Tauri 文档：https://tauri.app
- PyInstaller 文档：https://pyinstaller.org

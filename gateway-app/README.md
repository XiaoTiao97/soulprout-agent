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
    │   ├── src/main.rs  ← 启动 sidecar + 等待就绪 + 打开 webview
    │   └── tauri.conf.json
    └── scripts/
        └── build.ps1    ← 一键构建脚本
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

构建产物：`gateway-app/src-tauri/target/release/bundle/`

同时会生成固定文件名的安装包（供 GitHub Release 与前端下载链接使用）：

```
gateway-app/src-tauri/target/release/bundle/nsis/Soulprout-Gateway-setup.exe
```

---

## 发布 Gateway 客户端（GitHub Releases）

前端下载链接采用 **A2 方案**：始终指向 GitHub Releases 的 `latest` 资产，文件名固定为 `Soulprout-Gateway-setup.exe`，发新版后**无需修改前端代码**。

默认下载地址：

```
https://github.com/XiaoTiao97/soulprout-agent/releases/latest/download/Soulprout-Gateway-setup.exe
```

### 每次发新版（3 步）

**1. 更新版本号（可选但建议）**

编辑 `gateway-app/src-tauri/tauri.conf.json` 中的 `version` 字段，例如 `0.1.0` → `0.1.1`。

**2. 打 tag 并推送，触发 CI 自动构建**

```powershell
# 在项目根目录，tag 必须以 gateway-v 开头
git tag gateway-v0.1.1
git push origin gateway-v0.1.1
```

GitHub Actions 工作流 `.github/workflows/gateway-release.yml` 会自动：

- 在 Windows runner 上执行 `build.ps1`
- 生成 `Soulprout-Gateway-setup.exe`
- 上传到对应 GitHub Release

可在 GitHub 仓库 **Actions** 页查看构建进度，在 **Releases** 页确认安装包已上传。

**3. 验证下载**

浏览器打开上面的 `latest/download/...` 链接，确认能下载最新安装包。  
前端主页「多端互联」与用户菜单「Soulprout 互联」会自动指向该地址。

### 本地手动发布（不依赖 CI）

若 CI 暂不可用，可本地构建后手动上传：

```powershell
# 1. 本地构建
.\gateway-app\scripts\build.ps1

# 2. 产物路径
# gateway-app\src-tauri\target\release\bundle\nsis\Soulprout-Gateway-setup.exe

# 3. GitHub → Releases → Draft a new release
#    - Tag: gateway-v0.1.1
#    - 上传 Soulprout-Gateway-setup.exe
#    - Publish release
```

> 注意：Release 资产必须命名为 **`Soulprout-Gateway-setup.exe`**，与 CI 和前端默认链接保持一致。
>
> 不要上传 Tauri 默认生成的 `Soulprout.Gateway_0.1.0_x64-setup.exe`（带点号、带版本号），否则前端 `latest/download/Soulprout-Gateway-setup.exe` 会 404，下载无效。应上传 `build.ps1` 复制后的 **`Soulprout-Gateway-setup.exe`**。

### 自定义下载地址

若改用 OSS 等托管，在 Web 构建时设置环境变量即可：

```env
VITE_GATEWAY_DOWNLOAD_URL=https://your-cdn.example.com/Soulprout-Gateway-setup.exe
```

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

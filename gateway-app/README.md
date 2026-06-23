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

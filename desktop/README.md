# Soulprout Desktop（桌面端）

桌面端 = 现有网页界面 + 内嵌 gateway + 一层「本机执行」。Agent 本身仍然是云端 SaaS 的 Agent，
桌面端只是它的界面；凡是要碰用户电脑的工具（`read` / `write` / `edit` / `read_picture` / `bash`），
云端把调用发到用户电脑上执行，再把结果取回去。

> 安全检测的设计参考了 [deepseek-harness](https://github.com/deepseek-ai/deepseek-harness)（MIT），详见 [NOTICE.md](NOTICE.md)。

## 目录

```
desktop/
├── sidecar/            Python 本机服务（打成一个 exe，由 Tauri 拉起）
│   └── soulprout_desktop/
│       ├── server.py       127.0.0.1 上的 HTTP：静态界面、/api 反向代理、本地会话文件接口、审批 SSE
│       ├── cloud_client.py 到云端 /desktop/ws 的长连接（hello / 心跳 / tool_call / cancel）
│       ├── local_tools.py  read/write/edit/read_picture/bash 的本机实现 + 智能体文件同步
│       ├── policy.py       权限策略（参考 deepseek-harness）
│       ├── approvals.py    需要用户批准时的请求队列
│       ├── gateway_host.py 内嵌运行 gateway，数据目录重定向到受保护的状态目录
│       └── …               settings / device / auth_store / conversations / file_parse / paths
├── ui/                 桌面界面：复用 web/src 的页面，只加外壳（标题栏、审批弹窗、本机设置）
├── src-tauri/          Tauri 外壳：无边框圆角窗口，起 sidecar、等就绪、导航到界面、退出时清理
├── scripts/build.ps1   一键构建（界面 → PyInstaller → tauri build）
└── tests/              sidecar 的单元 / 集成测试
```

云端只改了很少的地方（见 `agent/services/desktop_bridge.py` 与 `desktop_hub.py` 的文件头说明）：
`/desktop/ws` 通道、工具调用的路由点、灵芽模式提示词里的设备状态、`Source:` 来源行。
环境变量 `DESKTOP_BRIDGE_ENABLED=0` 可整体关闭，行为退回到没有桌面端时的样子。

## 工作方式

| | 任务模式 | 灵芽模式 |
| --- | --- | --- |
| 会话标签 | 创建时定死：桌面端新建 = `local`，网页端新建 = `cloud`，之后不变（网页上显示「本地」标签） | 永远是同一个会话 |
| 工具在哪执行 | `local` 会话的本地类工具全部发往用户电脑；`cloud` 会话照旧 | 本地类工具多一个 `target`（`cloud` / `local`），由 Agent 自己选 |
| 本机工作区 | `~/Soulprout/workspaces/<conversation_id>`，每个会话一个固定目录 | 整台电脑（受权限设置约束） |
| 设备状态 | 不检测 | 系统提示词里写明桌面端在线 / 离线；其它渠道（微信等）只在在线时列出；每条用户消息带一行 `Source: Wechat 2026-10-29 11:15 Thu` |
| 文档解析 | 跟随会话标签（本地会话在本机解析） | 同左 |
| 智能体卡片文件 / 知识库 | 仍在云端；本地会话开始前把卡片文件、技能同步（只补缺失文件）到本机工作区 | 知识库在云端 |

设备离线时，工具会返回带原因的错误，Agent 能如实告诉用户；`list_info(category="device")` 可随时重新查询。

## 权限与安全

- **三档预设**（只存在本机，云端无法修改）：`只读`、`工作区读写`（默认）、`完全访问`。
  超出范围的操作 Agent 可以在调用里带 `sandbox_permissions` + `justification` 申请升级，
  由用户在弹窗里**逐次**批准；批准只对这一次有效。
- **bash**：Windows 上 v1 没有系统级隔离，所以在前两档里每条命令都要用户批准；`完全访问` 才直接执行。
- 受保护目录（桌面端状态目录：登录令牌、gateway 凭证等）任何档位下都不允许读写；敏感位置（如 `.ssh`）读写需要批准。
- sidecar 只监听 `127.0.0.1`，每次启动随机密钥，经 `/__boot?s=` 换取 `HttpOnly` + `SameSite=Strict` Cookie；
  校验 `Host` / `Origin`；云端登录令牌只在 sidecar 里，界面拿不到（代理时由 sidecar 注入）。

### 已知限制（v1）

- 没有操作系统级进程隔离（见上）。bash 命令一旦被批准就以用户权限运行，**也无法按路径限制**，
  所以不要对不信任的内容点「允许」。
- 灵芽模式的「技能」不会同步到本机。
- 本地会话不支持导出 PDF / PPTX；`.doc`（旧版 Word）无法在本机解析。
- 同一个设备同时只允许一个桌面端实例（第二次启动会把已有窗口带到前台）。

## 开发

准备：Python 环境（`pip install -r desktop/sidecar/requirements.txt`）、Node、Rust（Tauri 2）。

```powershell
# 1. 构建界面（直接借用 web/node_modules，不单独安装）
cd desktop/ui; npm run build

# 2a. 不开窗口，只跑 sidecar，用浏览器看界面
$env:SOULPROUT_DESKTOP_PORT = "8765"; $env:SOULPROUT_DESKTOP_SECRET = "dev"
$env:SOULPROUT_NO_GATEWAY = "1"       # 可选：不启动内嵌 gateway
python desktop/sidecar/main.py        # 然后打开 http://127.0.0.1:8765/__boot?s=dev

# 2b. 完整桌面窗口（debug 模式直接用本机 Python，不需要先打包 sidecar）
cd desktop; npm install; npm run dev  # 可用 SOULPROUT_PYTHON 指定解释器
```

常用环境变量：`AGENT_URL`（云端地址，默认官网）、`SOULPROUT_DATA_DIR`（默认 `~/Soulprout`）、
`SOULPROUT_STATE_DIR`、`SOULPROUT_UI_DIR`、`SOULPROUT_GATEWAY_PORT`。

## 构建安装包

```powershell
.\desktop\scripts\build.ps1                 # 全流程，产物在 desktop/release/
.\desktop\scripts\build.ps1 -Version 0.1.5 -Python D:\anaconda\envs\soulprout\python.exe
.\desktop\scripts\build.ps1 -SkipDeps -SkipUi   # 已经装好依赖 / 构建过界面时
```

## 发版（构建 + 上传官网 OSS）

官网「下载 Windows 版」固定指向 `desktop/Soulprout-setup.exe`，发版脚本会按版本号重新打包并覆盖上传。

```powershell
.\desktop\scripts\release.ps1 -Version 0.1.5 -Python D:\anaconda\envs\soulprout\python.exe
.\desktop\scripts\release.ps1                  # 版本号在 tauri.conf.json 上自动 patch +1
.\desktop\scripts\release.ps1 -UploadOnly -Version 0.1.5   # 只上传 desktop/release/ 已有产物
```

OSS 凭证复用 `gateway-app\.release.local.json`。

## 测试

```powershell
python -m unittest discover -s desktop/tests -t .    # sidecar：策略、本机工具、云端连接、HTTP 服务
python -m unittest agent.tests.test_desktop_bridge   # 云端：工具改写、路由、提示词、同步、连接表
```

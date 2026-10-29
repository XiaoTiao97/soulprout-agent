# 致谢与来源说明

## deepseek-harness

桌面端「本机工具的安全检测」**参考了 [deepseek-harness](https://github.com/deepseek-ai/deepseek-harness) 项目的设计**
（MIT License，Copyright (c) 2026 DeepSeek）。

这里没有搬运它的源码：它是 TypeScript / 原生实现，本项目按它的模型用 Python 重新实现，
并按「云端 Agent + 本机执行」的结构做了适配。参考到的部分与对应位置如下：

| deepseek-harness 中的设计 | 参考的包（`packages/` 下） | 本项目中的实现 |
| --- | --- | --- |
| 三种沙盒模式 `read-only` / `workspace-write` / `danger-full-access`；预设把「模式 + 审批策略」捆在一起 | `sandbox/sandbox-policy` | `desktop/sidecar/soulprout_desktop/policy.py`（`PRESETS`、`Standing`） |
| 升级只能到「严格更宽」的模式（`WIDER_MODES`），执行时检查而不是写进 schema；`sandbox_permissions` 与 `justification` 必须成对且理由非空 | `sandbox/sandbox-policy`、`fs/tool-fs` | `policy.py`（`check_strictly_wider`、`validate_escalation_args`）；云端 `agent/services/desktop_bridge.py` 里的工具参数定义 |
| 拒绝时返回给模型的标记 `[sandbox: file access denied under <mode> mode]` 与升级提示 | `fs/tool-fs`、`fs/fs-sandbox` | `policy.py`（`sandbox_denial_marker`、`escalation_hint_marker`、`denial_text`） |
| 审批：`ask` / `never`，结果 `allowed-once` / `rejected` / `cancelled` / `unavailable`；fail-closed 的判断顺序（先看是否更宽 → 再看有无审批通道 → 再映射审批结果） | `interaction/user-approval` | `policy.py`（`escalation_outcome_error`）、`approvals.py`、`local_tools.py` |
| 可写根 = 工作区 + 系统临时目录；路径包含判断先比规范化后的路径，不一致时回退到文件系统身份（dev/inode），覆盖 Windows 8.3 短名与大小写别名 | `fs/fs-sandbox`、`fs/fs-local` | `policy.py`（`canonical_path`、`is_path_under`、`writable_roots`） |
| 子进程环境变量清洗、输出尾部截断、结束整个进程树 | `shell/shell-env`、`shell/tool-bash`、`subprocess/subprocess-local` | `local_tools.py`（`scrubbed_env`、`tail_truncate`、进程树结束） |

### 与 deepseek-harness 的差异

- harness 在 Windows 上有基于 ACL 的进程沙盒（`sandbox/sandbox-windows-acl`）。本项目 **v1 没有**操作系统级隔离，
  所以在 `read-only` / `workspace-write` 下，**每一条 bash 命令都需要用户批准**，而不是「先在沙盒里跑、被拒再升级」。
  只有 `danger-full-access` 才会直接执行。后续可以评估引入同类沙盒。
- 本项目的默认预设是 `workspace-write`（与 harness 默认预设一致），审批通过后只对**这一次**调用有效，不会变成长期授权。
- 权限设置只存在用户电脑上，云端无法修改；云端模型只能在每次调用里「申请」升级，是否放行由用户决定。

### 许可证全文（MIT）

```
MIT License

Copyright (c) 2026 DeepSeek

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## 其他

- 桌面外壳的 sidecar 启动、进程树结束、NSIS 打包流程沿用了本仓库 `gateway-app/` 的做法。
- 界面页面全部复用 `web/src`，`desktop/ui` 只增加桌面外壳。

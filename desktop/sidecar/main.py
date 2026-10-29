"""桌面端 sidecar 入口。

开发时：``python desktop/sidecar/main.py``（需要 gateway 的依赖：pip install -r gateway/requirements.txt）
打包后：由 desktop/sidecar/soulprout_desktop.spec 打成单个可执行文件，作为 Tauri 的 sidecar 启动。
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

_here = Path(__file__).resolve().parent
_repo_root = _here.parent.parent
for candidate in (str(_here), str(_repo_root)):  # sidecar 包自己 + 仓库根（用于 import gateway）
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

from soulprout_desktop.app import run_app  # noqa: E402


def main() -> None:
    # 无控制台的打包形态下 stdout/stderr 可能是 None，直接 print / logging 会出错
    for name in ("stdout", "stderr"):
        if getattr(sys, name) is None:
            setattr(sys, name, open(os.devnull, "w", encoding="utf-8"))
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())  # 子进程（bash 工具）需要
    try:
        asyncio.run(run_app())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()

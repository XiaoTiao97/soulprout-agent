"""桌面端用到的目录。

- ``data_root``        用户可见的数据目录（默认 ``~/Soulprout``），本地会话的工作区放在它下面；
- ``state_dir``        桌面端自己的状态（登录凭证、设备 ID、权限设置），**Agent 的任何本地工具都不得访问**；
- ``ui_dist_dir``      桌面界面的静态产物。

所有函数每次调用都重新读环境变量，方便测试里临时改目录。
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

APP_DIR_NAME = "Soulprout"

_CONVERSATION_ID_SAFE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


def data_root() -> Path:
    env = os.getenv("SOULPROUT_DATA_DIR", "").strip()
    return Path(env).expanduser() if env else Path.home() / APP_DIR_NAME


def workspaces_root() -> Path:
    return data_root() / "workspaces"


def state_dir() -> Path:
    env = os.getenv("SOULPROUT_STATE_DIR", "").strip()
    if env:
        return Path(env).expanduser()
    if sys.platform == "win32":
        base = os.getenv("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / APP_DIR_NAME / "desktop"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_DIR_NAME / "desktop"
    base = os.getenv("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "soulprout-desktop"


def ui_dist_dir() -> Path:
    env = os.getenv("SOULPROUT_UI_DIR", "").strip()
    if env:
        return Path(env)
    meipass = getattr(sys, "_MEIPASS", None)
    if getattr(sys, "frozen", False) and meipass:
        return Path(meipass) / "ui"
    return Path(__file__).resolve().parents[2] / "ui" / "dist"


def is_valid_conversation_id(conversation_id: str) -> bool:
    return bool(conversation_id and _CONVERSATION_ID_SAFE.match(conversation_id))


def workspace_dir(conversation_id: str) -> Path:
    """本地会话的工作区目录（不创建）。会话 ID 只允许安全字符，杜绝借 ID 逃出工作区根目录。"""
    if not is_valid_conversation_id(conversation_id):
        raise ValueError(f"invalid conversation_id: {conversation_id!r}")
    return workspaces_root() / conversation_id

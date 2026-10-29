"""本机信息：上报给云端，让 Agent 知道它在哪个系统上工作。"""

from __future__ import annotations

import os
import platform
import sys
from pathlib import Path
from typing import Dict

from . import __version__, settings


def os_family() -> str:
    if sys.platform == "win32":
        return "windows"
    if sys.platform == "darwin":
        return "darwin"
    return "linux"


def _os_label() -> str:
    family = os_family()
    if family == "windows":
        try:
            build = int(platform.version().split(".")[-1])
        except (ValueError, IndexError):
            build = 0
        return "Windows 11" if build >= 22000 else f"Windows {platform.release()}"
    if family == "darwin":
        return f"macOS {platform.mac_ver()[0] or platform.release()}"
    return f"Linux {platform.release()}"


def default_shell() -> str:
    if sys.platform == "win32":
        return "cmd.exe"
    return os.getenv("SHELL") or "/bin/sh"


def device_info() -> Dict[str, str]:
    return {
        "os": _os_label(),
        "os_family": os_family(),
        "shell": Path(default_shell()).name,
        "home": str(Path.home()),
        "app_version": __version__,
        "arch": platform.machine() or "",
    }


def hello_frame(channels: Dict[str, bool]) -> Dict[str, object]:
    return {
        "type": "hello",
        "device_id": settings.device_id(),
        "device_name": settings.device_name(),
        "info": device_info(),
        "channels": channels,
    }

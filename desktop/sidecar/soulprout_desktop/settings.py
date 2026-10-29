"""桌面端本地设置（``<state_dir>/settings.json``）。

只存桌面端自己的东西：设备 ID / 名称、权限预设、本地会话 ID 集合。
登录凭证由 gateway 的 config_store 管理（见 ``auth_store``），这样合并进来的 gateway 能直接复用同一个登录态。
"""

from __future__ import annotations

import json
import logging
import os
import socket
import threading
import uuid
from typing import Any, Dict, List, Optional

from . import paths

logger = logging.getLogger(__name__)

DEFAULT_PRESET = "workspace-write"

_lock = threading.RLock()


def _settings_path():
    return paths.state_dir() / "settings.json"


def _load() -> Dict[str, Any]:
    path = _settings_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except Exception as exc:
        logger.warning("settings 读取失败，使用默认值: %s", exc)
        return {}


def _save(data: Dict[str, Any]) -> None:
    path = _settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def get(key: str, default: Any = None) -> Any:
    with _lock:
        return _load().get(key, default)


def update(**partial: Any) -> Dict[str, Any]:
    with _lock:
        data = _load()
        data.update(partial)
        _save(data)
        return data


# --- 设备 ---------------------------------------------------------------

def device_id() -> str:
    """稳定的设备 ID：第一次启动时生成并落盘，之后一直用同一个。"""
    with _lock:
        data = _load()
        value = str(data.get("device_id") or "")
        if not value:
            value = f"dk-{uuid.uuid4().hex[:16]}"
            data["device_id"] = value
            _save(data)
        return value


def device_name() -> str:
    with _lock:
        value = str(_load().get("device_name") or "").strip()
    return value or (socket.gethostname() or "My computer")[:80]


# --- 权限预设 --------------------------------------------------------------

def preset() -> str:
    return str(get("preset") or DEFAULT_PRESET)


def set_preset(name: str) -> None:
    update(preset=name)


# --- 本地会话集合 ------------------------------------------------------------
#
# 云端会话库里才是「这个会话是不是本地会话」的权威记录；这里只是桌面端自己创建过的会话 ID，
# 用来覆盖「刚发出第一条消息、云端还没落库」的空档，也避免每次都去云端查。

def local_conversations() -> List[str]:
    value = get("local_conversations") or []
    return [str(v) for v in value] if isinstance(value, list) else []


def add_local_conversation(conversation_id: str) -> None:
    with _lock:
        data = _load()
        items = [str(v) for v in (data.get("local_conversations") or [])]
        if conversation_id not in items:
            items.append(conversation_id)
            data["local_conversations"] = items[-5000:]
            _save(data)


def remove_local_conversation(conversation_id: str) -> None:
    with _lock:
        data = _load()
        items = [str(v) for v in (data.get("local_conversations") or [])]
        if conversation_id in items:
            items.remove(conversation_id)
            data["local_conversations"] = items
            _save(data)


def agent_url_override() -> Optional[str]:
    value = str(get("agent_url") or "").strip()
    return value.rstrip("/") or None


def set_agent_url_override(url: Optional[str]) -> None:
    """记住用户手动指定的云端地址；传 None / 空串表示恢复默认（官方云服务）。"""
    value = (url or "").strip().rstrip("/")
    with _lock:
        data = _load()
        if value:
            data["agent_url"] = value
        else:
            data.pop("agent_url", None)
        _save(data)

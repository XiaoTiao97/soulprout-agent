"""
Gateway 本地配置持久化。

将用户在管理界面修改的运行时设置存储到 ``gateway_data/settings.json``：

- ``agent_url``：目标 Agent HTTP 地址（本地或官方托管）
- ``agent_token``：已登录后的 JWT，由邮箱验证码登录 / SSO 登录得到，由 gateway 自动写入
- ``agent_user_id``：当前账号 ID，调用 Agent 时同时作为会话 ID，由登录流程自动写入
- ``agent_email``：登录使用的邮箱（仅用于显示与「重新发送验证码」）
- ``agent_login_mode``：``email`` | ``sso`` | ``token``，便于 UI 还原选择
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_SETTINGS_PATH = Path(__file__).resolve().parent.parent / "gateway_data" / "settings.json"

# ---------------------------------------------------------------------------
# 默认值
# ---------------------------------------------------------------------------

_DEFAULT_AGENT_URL = "https://www.mengya.chat"

_DEFAULTS: dict = {
    # Agent HTTP 服务地址（不含路径），支持：
    #   https://www.mengya.chat  → Soulprout 官方云服务（默认）
    #   http://localhost:8080    → 本地自部署
    "agent_url": _DEFAULT_AGENT_URL,

    # 已登录后保存的 JWT token。可由 gateway 自动写入，也允许用户手动填写。
    "agent_token": "",

    # 调用 Agent 时使用的 user_id，同时作为 conversation_id 保持对话上下文。
    "agent_user_id": "",

    # 邮箱（仅用于回显；实际验证发生在 Agent 服务上）
    "agent_email": "",

    # 登录方式：'email' | 'sso' | 'token'
    "agent_login_mode": "email",
}


# ---------------------------------------------------------------------------
# 读 / 写
# ---------------------------------------------------------------------------

def load_settings() -> dict:
    if not _SETTINGS_PATH.exists():
        return dict(_DEFAULTS)
    try:
        data = json.loads(_SETTINGS_PATH.read_text(encoding="utf-8"))
        merged = dict(_DEFAULTS)
        merged.update({k: v for k, v in data.items() if k in _DEFAULTS})
        return merged
    except Exception as exc:
        logger.warning("settings 读取失败，使用默认值: %s", exc)
        return dict(_DEFAULTS)


def save_settings(settings: dict) -> None:
    _SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    safe = {k: settings.get(k, v) for k, v in _DEFAULTS.items()}
    tmp = _SETTINGS_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(safe, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(_SETTINGS_PATH)
    logger.info("settings 已保存: agent_url=%s mode=%s", safe.get("agent_url"), safe.get("agent_login_mode"))


def update_settings(**partial) -> dict:
    """部分更新设置并落盘，返回完整设置。"""
    current = load_settings()
    allowed = set(_DEFAULTS.keys())
    for key, value in partial.items():
        if key in allowed:
            current[key] = "" if value is None else str(value)
    if "agent_url" in current:
        current["agent_url"] = current["agent_url"].rstrip("/")
    save_settings(current)
    return current


# ---------------------------------------------------------------------------
# 便捷读取
# ---------------------------------------------------------------------------

def get_agent_url() -> str:
    env_url = os.getenv("AGENT_URL", "").strip()
    if env_url:
        return env_url.rstrip("/")
    return load_settings().get("agent_url", _DEFAULTS["agent_url"]).rstrip("/")


def get_agent_token() -> str:
    env_token = os.getenv("AGENT_TOKEN", "").strip()
    if env_token:
        return env_token
    return load_settings().get("agent_token", "")


def get_agent_user_id() -> str:
    return load_settings().get("agent_user_id", _DEFAULTS["agent_user_id"])


def get_agent_email() -> str:
    return load_settings().get("agent_email", "")


def get_agent_login_mode() -> str:
    return load_settings().get("agent_login_mode", _DEFAULTS["agent_login_mode"]) or "email"


def get_default_agent_url() -> str:
    env_url = os.getenv("AGENT_URL", "").strip()
    if env_url:
        return env_url.rstrip("/")
    return _DEFAULT_AGENT_URL


def normalize_agent_url(url: str) -> str:
    return (url or "").strip().rstrip("/")


def is_local_agent(url: Optional[str] = None) -> bool:
    target = (url or get_agent_url()).lower()
    return any(
        target.startswith(prefix)
        for prefix in ("http://localhost", "http://127.0.0.1", "http://0.0.0.0")
    )


# ---------------------------------------------------------------------------
# 兼容旧调用（chat_caller 之前从这里获取密码）
# ---------------------------------------------------------------------------

def get_agent_password() -> str:  # pragma: no cover - kept for backwards compat
    """旧版密码登录已废弃，仅返回空串以兼容历史调用。"""
    return ""

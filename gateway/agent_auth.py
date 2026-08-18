"""Soulprout 账号邮箱验证码登录（CLI / Web 共用逻辑）。"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


async def verify_agent_session() -> Dict[str, Any]:
    """检查当前本地 token 是否仍有效。返回 {ok, user_id, email, message}。"""
    from gateway.config_store import (
        api_path,
        get_agent_email,
        get_agent_token,
        get_agent_url,
        get_agent_user_id,
    )

    token = get_agent_token()
    if not token:
        return {"ok": False, "message": "尚未登录"}

    try:
        import aiohttp
    except ImportError:
        return {"ok": False, "message": "aiohttp 未安装"}

    agent_url = get_agent_url()
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                api_path(agent_url, "/user/me"),
                cookies={"token": token},
                headers={"Authorization": f"Bearer {token}"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                data = await resp.json(content_type=None)
    except Exception as exc:
        return {"ok": False, "message": f"验证登录态失败：{exc}"}

    if isinstance(data, dict) and data.get("success"):
        return {
            "ok": True,
            "user_id": str(data.get("user_id") or get_agent_user_id()),
            "email": get_agent_email(),
            "message": "登录有效",
        }
    return {"ok": False, "message": "登录已过期，请重新验证邮箱"}


async def send_email_code(*, email: str, agent_url: Optional[str] = None) -> Dict[str, Any]:
    from gateway.config_store import api_path, get_agent_url, get_auth_url, normalize_agent_url, update_settings

    email = email.strip()
    if not email:
        return {"success": False, "message": "请填写邮箱"}

    url = normalize_agent_url(agent_url or get_agent_url())
    update_settings(agent_url=url)
    auth_url = get_auth_url(url)

    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.post(
                api_path(auth_url, "/user/email/send-code"),
                json={"email": email},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                data = await resp.json(content_type=None)
    except Exception as exc:
        return {"success": False, "message": f"发送验证码失败：{exc}"}

    if not isinstance(data, dict):
        return {"success": False, "message": "服务端返回格式异常"}
    data["agent_url"] = url
    return data


async def login_with_email_code(
    *,
    email: str,
    code: str,
    agent_url: Optional[str] = None,
    username: Optional[str] = None,
) -> Dict[str, Any]:
    from gateway.config_store import api_path, get_auth_url, normalize_agent_url, update_settings

    email = email.strip()
    code = code.strip()
    if not email or not code:
        return {"success": False, "message": "邮箱与验证码不能为空"}

    url = normalize_agent_url(agent_url or "")
    if url:
        update_settings(agent_url=url)
    from gateway.config_store import get_agent_url

    url = get_agent_url()
    auth_url = get_auth_url(url)

    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.post(
                api_path(auth_url, "/user/email/login"),
                json={"email": email, "code": code, "username": username},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                data = await resp.json(content_type=None)
    except Exception as exc:
        return {"success": False, "message": f"登录失败：{exc}"}

    if not isinstance(data, dict):
        return {"success": False, "message": "服务端返回格式异常"}

    if data.get("success") and data.get("token"):
        update_settings(
            agent_url=url,
            agent_token=str(data["token"]),
            agent_user_id=str(data.get("user_id", "")),
            agent_email=email,
            agent_login_mode="email",
        )
        logger.info("Soulprout 邮箱登录成功 user_id=%s", data.get("user_id"))

    data["agent_url"] = url
    return data

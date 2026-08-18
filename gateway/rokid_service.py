"""Rokid 灵珠凭证生成与同步（CLI / Web 共用）。"""

from __future__ import annotations

from typing import Any, Dict


async def rokid_agent_request(
    method: str,
    path: str,
    *,
    token: str,
    json_body: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    import aiohttp
    from gateway.config_store import api_path, get_agent_url

    url = api_path(get_agent_url(), path)
    headers = {"Authorization": f"Bearer {token}"}
    cookies = {"token": token}
    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.request(
            method,
            url,
            json=json_body,
            headers=headers,
            cookies=cookies,
        ) as resp:
            data = await resp.json(content_type=None)
            if resp.status >= 400:
                msg = (
                    (data or {}).get("message")
                    or (data or {}).get("detail")
                    or (data or {}).get("msg")
                    or f"HTTP {resp.status}"
                )
                raise RuntimeError(str(msg))
            if not isinstance(data, dict):
                raise RuntimeError("主站返回格式异常")
            return data


async def ensure_rokid_credentials() -> Dict[str, Any]:
    """生成或同步 Rokid API Key，返回凭证与说明字段。"""
    from gateway.config_store import (
        cache_rokid_credentials,
        generate_local_rokid_pair,
        get_agent_token,
        get_agent_user_id,
        get_rokid_agent_id,
    )
    from gateway.platforms.rokid import ROKID_PUBLIC_SSE_URL

    user_id = get_agent_user_id()
    token = get_agent_token()
    if not user_id or not token:
        return {"success": False, "error": "请先登录 Soulprout 账号（邮箱验证码）"}

    try:
        remote = await rokid_agent_request("GET", "/rokid/credentials", token=token)
        remote_agent_id = (remote.get("agent_id") or "").strip()
        need_fix_id = bool(remote.get("configured") and remote_agent_id and len(remote_agent_id) > 20)

        if remote.get("configured") and remote.get("api_key") and not need_fix_id:
            cache_rokid_credentials(
                api_key=remote["api_key"],
                agent_id=remote_agent_id,
                user_id=remote.get("user_id") or user_id,
            )
            return {
                "success": True,
                "api_key": remote["api_key"],
                "agent_id": remote_agent_id,
                "bound_user_id": remote.get("user_id") or user_id,
                "sse_url": remote.get("sse_url") or ROKID_PUBLIC_SSE_URL,
                "message": "已从主站同步 API Key（不会重复生成）",
            }

        pair = generate_local_rokid_pair(
            user_id=user_id,
            reuse_agent_id="" if need_fix_id else (get_rokid_agent_id() or remote_agent_id),
            force_new_agent_id=need_fix_id,
        )
        uploaded = await rokid_agent_request(
            "POST",
            "/rokid/credentials",
            token=token,
            json_body={
                "api_key": pair["api_key"],
                "agent_id": pair["agent_id"],
                "force_new_key": need_fix_id,
            },
        )
        final_agent_id = (uploaded.get("agent_id") or pair["agent_id"] or "").strip()
        if len(final_agent_id) > 20:
            return {"success": False, "error": "主站返回的智能体 ID 超过 20 字符限制"}

        api_key = (uploaded.get("api_key") or pair["api_key"] or "").strip()
        cache_rokid_credentials(
            api_key=api_key,
            agent_id=final_agent_id,
            user_id=user_id,
        )
        return {
            "success": True,
            "api_key": api_key,
            "agent_id": final_agent_id,
            "bound_user_id": user_id,
            "sse_url": uploaded.get("sse_url") or ROKID_PUBLIC_SSE_URL,
            "message": "API Key 已生成并上传主站",
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}

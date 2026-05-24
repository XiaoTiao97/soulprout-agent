"""
Agent Chat HTTP 调用封装。

所有消息统一通过 HTTP POST 请求发送给 Agent ``/message/chat`` 接口（SSE 流），
收集所有 ``role=assistant``、``type=text`` 的内容后拼接为完整回复返回。

认证策略
-------
1. 优先使用 ``agent_token``（由邮箱验证码登录或 SSO 登录获得，由 gateway 持久化）。
2. ``agent_token`` 为空时，请通过管理 Web 服务先完成登录；本模块不再尝试自动登录。
3. 当 token 失效（HTTP 401）时清掉本地 token 缓存，调用方需在 UI 重新登录。
"""

from __future__ import annotations

import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 主调用入口
# ---------------------------------------------------------------------------

async def call_agent_chat(
    message: str,
    user_id: str,
    conversation_id: str = "",
    model_source: Optional[str] = None,
    model: Optional[str] = None,
) -> str:
    """
    调用 Agent ``/message/chat``，返回完整的 assistant 回复文本（非流式）。

    始终通过 HTTP 调用，无论 ``agent_url`` 是本地还是远端。
    """
    from gateway.config_store import get_agent_token, get_agent_url, get_agent_user_id

    agent_url = get_agent_url()
    configured_user_id = get_agent_user_id() or user_id
    effective_conversation_id = conversation_id or configured_user_id

    logger.debug(
        "[ChatCaller] url=%s user=%s conv=%s",
        agent_url, configured_user_id, effective_conversation_id,
    )

    token = get_agent_token()
    if not token:
        logger.warning(
            "[ChatCaller] agent_token 为空，请先在管理 Web 界面完成登录"
            "（http://<gateway-host>:8082）"
        )

    return await _call_http(
        agent_url=agent_url,
        message=message,
        user_id=configured_user_id,
        conversation_id=effective_conversation_id,
        token=token,
        model_source=model_source,
        model=model,
    )


# ---------------------------------------------------------------------------
# HTTP SSE 调用
# ---------------------------------------------------------------------------

async def _call_http(
    agent_url: str,
    message: str,
    user_id: str,
    conversation_id: str,
    token: str,
    model_source: Optional[str],
    model: Optional[str],
) -> str:
    """
    POST ``/message/chat``，逐行读取 SSE 流，拼接所有 ``role=assistant type=text`` 片段。
    """
    try:
        import aiohttp
    except ImportError:
        return "（aiohttp 未安装，无法调用 Agent）"

    endpoint = f"{agent_url.rstrip('/')}/message/chat"

    chat_req: dict = {
        "message": message,
        "user_id": user_id,
        "conversation_id": conversation_id,
        "tools_use": True,
        "kb_use": [],
        "agent_use": "soulprout",
        "agent_id": None,
        "temp_file_path": None,
        "file_name_list": [],
        "skills_use": False,
    }
    if model_source:
        chat_req["model_source"] = model_source
    if model:
        chat_req["model"] = model

    headers: dict = {}
    cookies: dict = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
        cookies["token"] = token

    try:
        timeout = aiohttp.ClientTimeout(total=300)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            form = aiohttp.FormData()
            form.add_field("chat_request", json.dumps(chat_req, ensure_ascii=False))

            async with session.post(
                endpoint,
                data=form,
                headers=headers,
                cookies=cookies,
            ) as resp:

                if resp.status == 401:
                    logger.error(
                        "[ChatCaller] HTTP 401：token 已失效，请在管理界面重新登录"
                    )
                    # 主动清空设置中的 token，便于 UI 提示重新登录
                    try:
                        from gateway.config_store import update_settings
                        update_settings(agent_token="")
                    except Exception:
                        pass
                    return "（Agent 认证失败，请在 Gateway 管理界面重新登录）"

                if resp.status >= 400:
                    body = await resp.text()
                    logger.error(
                        "[ChatCaller] API 错误 HTTP %d: %s", resp.status, body[:200]
                    )
                    return f"（Agent 请求失败 HTTP {resp.status}）"

                parts: list[str] = []
                async for raw_line in resp.content:
                    line = raw_line.decode("utf-8", errors="replace").strip()
                    if not line.startswith("data:"):
                        continue
                    data_str = line[5:].strip()
                    if data_str in ("", "[DONE]"):
                        continue
                    try:
                        chunk = json.loads(data_str)
                        if chunk.get("role") == "assistant" and chunk.get("type") == "text":
                            content = chunk.get("content", "")
                            if content:
                                parts.append(content)
                    except (json.JSONDecodeError, TypeError):
                        pass

                reply = "".join(parts).strip()
                return reply if reply else "（无回复）"

    except Exception as exc:
        logger.error("[ChatCaller] HTTP 调用失败 url=%s: %s", endpoint, exc, exc_info=True)
        return f"（Agent 调用失败: {exc}）"

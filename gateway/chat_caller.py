"""
Agent Chat HTTP 调用封装。

所有消息统一通过 HTTP POST 请求发送给 Agent ``/message/chat`` 接口（SSE 流），
收集 ``role=assistant type=text`` 与 ``type=user_feedback`` 的内容后拼接为完整回复返回。

认证策略
-------
1. 优先使用 ``agent_token``（由邮箱验证码登录或 SSO 登录获得，由 gateway 持久化）。
2. ``agent_token`` 为空时，请通过管理 Web 服务先完成登录；本模块不再尝试自动登录。
3. 当 token 失效（HTTP 401）时清掉本地 token 缓存，调用方需在 UI 重新登录。
"""

from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator, Optional

logger = logging.getLogger(__name__)

# web_search 等工具执行期间可能长时间无业务数据；总时长与读空闲需足够宽松
_HTTP_TIMEOUT_TOTAL_S = 600
_HTTP_TIMEOUT_CONNECT_S = 60
_HTTP_TIMEOUT_SOCK_READ_S = 180


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


async def iter_agent_chat_text_chunks(
    message: str,
    user_id: str,
    conversation_id: str = "",
    token: Optional[str] = None,
    model_source: Optional[str] = None,
    model: Optional[str] = None,
) -> AsyncIterator[str]:
    """流式产出 assistant 文本片段（供 Rokid 等 SSE 协议适配使用）。"""
    from gateway.config_store import get_agent_token, get_agent_url

    agent_url = get_agent_url()
    effective_token = (token or get_agent_token() or "").strip()
    effective_conversation_id = conversation_id or user_id

    if not effective_token:
        yield "（Agent 认证失败，请在 Gateway 管理界面重新登录以刷新 Rokid 绑定凭证）"
        return

    async for chunk in _iter_http_text_chunks(
        agent_url=agent_url,
        message=message,
        user_id=user_id,
        conversation_id=effective_conversation_id,
        token=effective_token,
        model_source=model_source,
        model=model,
    ):
        yield chunk


# ---------------------------------------------------------------------------
# HTTP / SSE 工具
# ---------------------------------------------------------------------------

def _make_http_timeout():
    import aiohttp

    return aiohttp.ClientTimeout(
        total=_HTTP_TIMEOUT_TOTAL_S,
        connect=_HTTP_TIMEOUT_CONNECT_S,
        sock_connect=_HTTP_TIMEOUT_CONNECT_S,
        sock_read=_HTTP_TIMEOUT_SOCK_READ_S,
    )


def _make_ssl_connector():
    """与微信侧一致：用 certifi CA，减轻 Windows 上 SSL 握手超时/证书问题。"""
    try:
        import aiohttp
        import certifi
        import ssl

        ssl_ctx = ssl.create_default_context(cafile=certifi.where())
        return aiohttp.TCPConnector(ssl=ssl_ctx)
    except Exception as exc:
        logger.warning("[ChatCaller] 创建 SSL connector 失败，使用默认: %s", exc)
        return None


def _build_chat_request(
    message: str,
    user_id: str,
    conversation_id: str,
    model_source: Optional[str],
    model: Optional[str],
) -> dict:
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
    return chat_req


def _ingest_sse_chunk(
    chunk: dict[str, Any],
    parts: list[str],
    feedback_parts: list[str],
    error_parts: list[str],
) -> None:
    chunk_type = chunk.get("type")
    content = chunk.get("content") or ""
    if not content:
        return
    if chunk_type == "user_feedback":
        feedback_parts.append(content)
    elif chunk_type == "error":
        error_parts.append(content)
    elif chunk.get("role") == "assistant" and chunk_type == "text":
        parts.append(content)


def _compose_reply(
    parts: list[str],
    feedback_parts: list[str],
    error_parts: list[str],
) -> str:
    reply_segments: list[str] = []
    if parts:
        reply_segments.append("".join(parts).strip())
    if feedback_parts:
        reply_segments.append("\n\n".join(feedback_parts).strip())
    if error_parts and not parts:
        reply_segments.append("\n\n".join(error_parts).strip())
    reply = "\n\n".join(seg for seg in reply_segments if seg).strip()
    return reply if reply else "（无回复）"


async def _iter_sse_json_events(resp) -> AsyncIterator[dict[str, Any]]:
    """
    按行缓冲解析 SSE。

    aiohttp 的 ``resp.content`` 按网络块产出，不能当作逻辑行；
    web_search 等大 payload 必须拼完整行后再 ``json.loads``。
    """
    buffer = ""
    async for raw in resp.content.iter_any():
        if not raw:
            continue
        buffer += raw.decode("utf-8", errors="replace")
        while True:
            split_at = buffer.find("\n")
            if split_at < 0:
                break
            line = buffer[:split_at].rstrip("\r")
            buffer = buffer[split_at + 1 :]
            line = line.strip()
            if not line or line.startswith(":"):
                # 空行或 SSE comment（心跳）
                continue
            if not line.startswith("data:"):
                continue
            data_str = line[5:].strip()
            if data_str in ("", "[DONE]"):
                continue
            try:
                yield json.loads(data_str)
            except (json.JSONDecodeError, TypeError):
                logger.debug("[ChatCaller] 跳过无法解析的 SSE 行: %s", data_str[:120])


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
    POST ``/message/chat``，逐行读取 SSE 流，拼接 assistant 正文与 user_feedback 提示文本。
    """
    try:
        import aiohttp
    except ImportError:
        return "（aiohttp 未安装，无法调用 Agent）"

    from gateway.config_store import api_path

    endpoint = api_path(agent_url, "/message/chat")
    chat_req = _build_chat_request(message, user_id, conversation_id, model_source, model)

    headers: dict = {}
    cookies: dict = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
        cookies["token"] = token

    connector = _make_ssl_connector()
    try:
        async with aiohttp.ClientSession(
            timeout=_make_http_timeout(),
            connector=connector,
            trust_env=True,
        ) as session:
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
                feedback_parts: list[str] = []
                error_parts: list[str] = []
                async for chunk in _iter_sse_json_events(resp):
                    _ingest_sse_chunk(chunk, parts, feedback_parts, error_parts)

                return _compose_reply(parts, feedback_parts, error_parts)

    except Exception as exc:
        logger.error("[ChatCaller] HTTP 调用失败 url=%s: %s", endpoint, exc, exc_info=True)
        return f"（Agent 调用失败: {exc}）"


async def _iter_http_text_chunks(
    agent_url: str,
    message: str,
    user_id: str,
    conversation_id: str,
    token: str,
    model_source: Optional[str],
    model: Optional[str],
) -> AsyncIterator[str]:
    """POST ``/message/chat``，逐 chunk 产出 assistant 文本。"""
    try:
        import aiohttp
    except ImportError:
        yield "（aiohttp 未安装，无法调用 Agent）"
        return

    from gateway.config_store import api_path

    endpoint = api_path(agent_url, "/message/chat")
    chat_req = _build_chat_request(message, user_id, conversation_id, model_source, model)

    headers: dict = {"Authorization": f"Bearer {token}"}
    cookies: dict = {"token": token}
    connector = _make_ssl_connector()

    try:
        async with aiohttp.ClientSession(
            timeout=_make_http_timeout(),
            connector=connector,
            trust_env=True,
        ) as session:
            form = aiohttp.FormData()
            form.add_field("chat_request", json.dumps(chat_req, ensure_ascii=False))

            async with session.post(
                endpoint,
                data=form,
                headers=headers,
                cookies=cookies,
            ) as resp:
                if resp.status == 401:
                    logger.error("[ChatCaller] 流式调用 HTTP 401：token 已失效")
                    yield "（Agent 认证失败，请在 Gateway 重新登录以刷新 Rokid 绑定凭证）"
                    return

                if resp.status >= 400:
                    body = await resp.text()
                    logger.error(
                        "[ChatCaller] 流式调用 API 错误 HTTP %d: %s",
                        resp.status,
                        body[:200],
                    )
                    yield f"（Agent 请求失败 HTTP {resp.status}）"
                    return

                async for chunk in _iter_sse_json_events(resp):
                    content = chunk.get("content") or ""
                    if not content:
                        continue
                    chunk_type = chunk.get("type")
                    if chunk_type in ("user_feedback", "error"):
                        yield content
                    elif chunk.get("role") == "assistant" and chunk_type == "text":
                        yield content

    except Exception as exc:
        logger.error(
            "[ChatCaller] 流式 HTTP 调用失败 url=%s: %s", endpoint, exc, exc_info=True
        )
        yield f"（Agent 调用失败: {exc}）"

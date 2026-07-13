"""Rokid / 灵珠协议：凭证管理与 Soul SSE 适配。"""

from __future__ import annotations

import json
import logging
import secrets
import uuid
from datetime import datetime
from typing import Any, AsyncIterator, Dict, List, Optional

from beanie.operators import Eq

from agent.api.models.message import ChatRequest
from agent.database.models.rokid_credential import RokidCredential
from agent.services.agent import Chat

logger = logging.getLogger(__name__)

# 灵珠填写用的公网 SSE（经反向代理 /api 前缀）
ROKID_PUBLIC_SSE_URL = "https://www.soulprout.com/api/metis/agent/api/sse"
ROKID_SSE_PATH = "/metis/agent/api/sse"


def new_api_key() -> str:
    return f"sk-{secrets.token_urlsafe(32)}"


def new_agent_id() -> str:
    return uuid.uuid4().hex


async def get_credential_by_user_id(user_id: str) -> Optional[RokidCredential]:
    return await RokidCredential.find_one(Eq(RokidCredential.user_id, str(user_id)))


async def get_credential_by_api_key(api_key: str) -> Optional[RokidCredential]:
    key = (api_key or "").strip()
    if not key:
        return None
    return await RokidCredential.find_one(Eq(RokidCredential.api_key, key))


async def ensure_credential(
    user_id: str,
    *,
    api_key: Optional[str] = None,
    agent_id: Optional[str] = None,
    force_new_key: bool = False,
) -> RokidCredential:
    """确保用户有凭证；默认不刷新已有 AK。"""
    user_id = str(user_id)
    existing = await get_credential_by_user_id(user_id)
    now = datetime.utcnow()

    if existing and not force_new_key:
        return existing

    if existing and force_new_key:
        existing.api_key = (api_key or "").strip() or new_api_key()
        existing.updated_at = now
        await existing.save()
        return existing

    cred = RokidCredential(
        user_id=user_id,
        agent_id=(agent_id or "").strip() or new_agent_id(),
        api_key=(api_key or "").strip() or new_api_key(),
        created_at=now,
        updated_at=now,
    )
    await cred.insert()
    return cred


async def upload_credential(
    user_id: str,
    *,
    api_key: str,
    agent_id: str,
    force_new_key: bool = False,
) -> RokidCredential:
    """Gateway 生成后上传；已存在且非强制时返回原凭证。"""
    api_key = (api_key or "").strip()
    agent_id = (agent_id or "").strip()
    if not api_key or not agent_id:
        raise ValueError("api_key 与 agent_id 不能为空")

    existing = await get_credential_by_user_id(user_id)
    now = datetime.utcnow()
    if existing and not force_new_key:
        return existing

    if existing and force_new_key:
        # 避免唯一索引冲突：先清掉其它占用同一 api_key 的记录（理论上不应有）
        conflict = await get_credential_by_api_key(api_key)
        if conflict and conflict.user_id != str(user_id):
            raise ValueError("api_key 已被占用")
        existing.api_key = api_key
        # agent_id 保持不变（灵珠侧智能体 ID 尽量固定）
        existing.updated_at = now
        await existing.save()
        return existing

    conflict_key = await get_credential_by_api_key(api_key)
    if conflict_key:
        raise ValueError("api_key 已被占用")
    conflict_agent = await RokidCredential.find_one(Eq(RokidCredential.agent_id, agent_id))
    if conflict_agent:
        raise ValueError("agent_id 已被占用")

    cred = RokidCredential(
        user_id=str(user_id),
        agent_id=agent_id,
        api_key=api_key,
        created_at=now,
        updated_at=now,
    )
    await cred.insert()
    return cred


def parse_bearer_api_key(authorization: Optional[str]) -> str:
    raw = (authorization or "").strip()
    if raw.lower().startswith("bearer "):
        return raw[7:].strip()
    return raw


def build_user_message(body: Dict[str, Any]) -> str:
    parts: List[str] = []
    meta = body.get("metadata") if isinstance(body.get("metadata"), dict) else {}
    ctx = meta.get("context") if isinstance(meta.get("context"), dict) else {}
    if ctx:
        ctx_lines: List[str] = []
        for key in ("location", "latitude", "longitude", "weather", "battery", "currentTime"):
            val = ctx.get(key)
            if val is not None and str(val).strip():
                ctx_lines.append(f"{key}: {val}")
        if ctx_lines:
            parts.append("[设备上下文]\n" + "\n".join(ctx_lines))

    messages = body.get("message")
    if not isinstance(messages, list):
        messages = []
    for item in messages:
        if not isinstance(item, dict):
            continue
        msg_type = (item.get("type") or "text").strip().lower()
        if msg_type == "image":
            url = (item.get("image_url") or item.get("text") or "").strip()
            if url:
                parts.append(f"[图片] {url}")
        else:
            text = (item.get("text") or "").strip()
            if text:
                parts.append(text)
    return "\n\n".join(parts).strip()


def format_sse(event: str, data: Dict[str, Any]) -> str:
    return f"event:{event}\ndata:{json.dumps(data, ensure_ascii=False)}\n\n"


def answer_event(
    *,
    message_id: str,
    agent_id: str,
    answer_stream: str,
    is_finish: bool,
) -> str:
    return format_sse(
        "message",
        {
            "role": "agent",
            "type": "answer",
            "answer_stream": answer_stream,
            "message_id": message_id,
            "agent_id": agent_id,
            "is_finish": is_finish,
        },
    )


def done_event(*, message_id: str, agent_id: str) -> str:
    return format_sse(
        "done",
        {
            "role": "agent",
            "message_id": message_id,
            "agent_id": agent_id,
            "is_finish": True,
        },
    )


async def stream_soul_as_rokid(
    *,
    body: Dict[str, Any],
    user_id: str,
    agent_id: str,
) -> AsyncIterator[str]:
    message_id = str(body.get("message_id") or "").strip() or "0"
    user_text = build_user_message(body)

    if not user_text:
        yield answer_event(
            message_id=message_id,
            agent_id=agent_id,
            answer_stream="（未收到有效文本或图片内容）",
            is_finish=False,
        )
        yield answer_event(
            message_id=message_id,
            agent_id=agent_id,
            answer_stream="",
            is_finish=True,
        )
        yield done_event(message_id=message_id, agent_id=agent_id)
        return

    chat_req = ChatRequest(
        message=user_text,
        user_id=user_id,
        conversation_id=user_id,
        tools_use=True,
        kb_use=[],
        agent_use="soulprout",
        agent_id=None,
        temp_file_path=None,
        file_name_list=[],
        skills_use=False,
    )
    ai_service = Chat(chat_req)

    emitted = False
    try:
        async for raw in ai_service.run():
            try:
                chunk = json.loads(raw) if isinstance(raw, str) else raw
            except (json.JSONDecodeError, TypeError):
                continue
            if not isinstance(chunk, dict):
                continue
            content = chunk.get("content") or ""
            if not content:
                continue
            chunk_type = chunk.get("type")
            if chunk_type == "user_feedback" or (
                chunk.get("role") == "assistant" and chunk_type == "text"
            ):
                emitted = True
                yield answer_event(
                    message_id=message_id,
                    agent_id=agent_id,
                    answer_stream=content,
                    is_finish=False,
                )
    except Exception as exc:
        logger.error("[rokid] Soul 调用失败 user=%s: %s", user_id, exc, exc_info=True)
        emitted = True
        yield answer_event(
            message_id=message_id,
            agent_id=agent_id,
            answer_stream=f"（Agent 调用失败: {exc}）",
            is_finish=False,
        )

    if not emitted:
        yield answer_event(
            message_id=message_id,
            agent_id=agent_id,
            answer_stream="（无回复）",
            is_finish=False,
        )

    yield answer_event(
        message_id=message_id,
        agent_id=agent_id,
        answer_stream="",
        is_finish=True,
    )
    yield done_event(message_id=message_id, agent_id=agent_id)

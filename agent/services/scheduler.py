"""云端定时任务调度：到期后写入对话，微信等渠道入队由 Gateway HTTP 拉取。"""

from __future__ import annotations

import asyncio
import json
import logging

from agent.api.models.message import ChatRequest
from agent.database.crud.outbound_delivery import (
    delivery_to_payload,
    enqueue_delivery,
    list_pending_for_users,
)
from agent.database.crud.scheduled_task import (
    claim_due_tasks,
    finish_scheduled_task,
    recover_stale_running_tasks,
    resolve_task_kind,
)
from agent.database.models.message import AgentMessage
from agent.database.models.scheduled_task import ScheduledTask
from agent.services.gateway_hub import hub
from datetime import datetime

logger = logging.getLogger(__name__)

_POLL_INTERVAL_S = 60.0
_GATEWAY_CHANNELS = {"weixin", "feishu", "wecom", "xiaoai", "rokid"}


def _parse_sse_chunk(raw) -> dict:
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str):
        return {}
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}


def _conversation_id(task: ScheduledTask) -> str:
    return (task.conversation_id or task.user_id or "").strip() or task.user_id


async def _save_context_message(task: ScheduledTask, role: str, content: str) -> None:
    text = (content or "").strip()
    if not text:
        return
    await AgentMessage(
        user_id=task.user_id,
        conversation_id=_conversation_id(task),
        type="text",
        role=role,
        content=text,
        created_at=datetime.utcnow(),
    ).insert()


async def _run_instruction(task: ScheduledTask) -> str:
    from agent.core.config import Config
    from agent.services.agent import Chat

    config = Config()
    request = ChatRequest(
        message=(task.instruction or "").strip(),
        user_id=task.user_id,
        conversation_id=_conversation_id(task),
        agent_use="soulprout",
        tools_use=True,
        skills_use=True,
        kb_use=[],
        runtime_mode="scheduled",
        channel=task.channel,
        chat_id=task.chat_id,
        model_source=config.soulprout_model_source,
        model=config.soulprout_model,
    )
    chat = Chat(request)
    parts: list[str] = []
    async for raw in chat.run():
        chunk = _parse_sse_chunk(raw)
        content = chunk.get("content") or ""
        if not content:
            continue
        chunk_type = chunk.get("type")
        if chunk_type in ("user_feedback", "error"):
            parts.append(content)
        elif chunk.get("role") == "assistant" and chunk_type == "text":
            parts.append(content)
    return "".join(parts).strip()


async def dispatch_to_channel(task: ScheduledTask, content: str) -> None:
    channel = (task.channel or "web").strip().lower() or "web"
    if channel not in _GATEWAY_CHANNELS:
        return
    chat_id = (task.chat_id or "").strip() or None
    if not chat_id:
        from agent.database.crud.user_channel_binding import get_channel_chat_id
        chat_id = await get_channel_chat_id(task.user_id, channel)
        if chat_id:
            task.chat_id = chat_id
            await task.save()
    if not chat_id:
        logger.warning("[Scheduler] 无 chat_id，无法投递 channel=%s task=%s", channel, task.task_id)
        return
    delivery = await enqueue_delivery(
        user_id=task.user_id,
        channel=channel,
        chat_id=chat_id,
        content=content,
        task_id=task.task_id,
    )
    await hub.send_json(task.user_id, delivery_to_payload(delivery))


async def flush_pending_to_online_gateways() -> None:
    pending = await list_pending_for_users(hub.online_user_ids())
    for item in pending:
        if item.channel == "web":
            continue
        await hub.send_json(item.user_id, delivery_to_payload(item))


async def _execute_task(task: ScheduledTask) -> None:
    kind = resolve_task_kind(getattr(task, "kind", None), task.instruction or "", task.notify_text or "")
    logger.info("[Scheduler] 触发 task=%s kind=%s channel=%s", task.task_id, kind, task.channel)
    try:
        if kind == "agent":
            instruction = (task.instruction or "").strip()
            if not instruction:
                raise ValueError("任务模式缺少 instruction")
            reply = await _run_instruction(task)
            if not reply:
                reply = f"定时任务「{task.title}」已执行，但没有生成可发送的结果。"
                await _save_context_message(task, "assistant", reply)
            await dispatch_to_channel(task, reply)
        else:
            content = (task.notify_text or "").strip() or f"定时提醒：{task.title}"
            await _save_context_message(task, "assistant", content)
            await dispatch_to_channel(task, content)
        await finish_scheduled_task(task)
    except Exception as exc:
        logger.error("[Scheduler] 执行失败 task=%s: %s", task.task_id, exc, exc_info=True)
        try:
            await finish_scheduled_task(task, error=str(exc))
        except Exception:
            logger.exception("[Scheduler] 回写任务状态失败 task=%s", task.task_id)


async def run_scheduler_loop() -> None:
    logger.info("[Scheduler] 已启动，间隔 %.0fs", _POLL_INTERVAL_S)
    while True:
        try:
            await recover_stale_running_tasks()
            due = await claim_due_tasks()
            for task in due:
                await _execute_task(task)
            await flush_pending_to_online_gateways()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("[Scheduler] 调度循环异常: %s", exc, exc_info=True)
        await asyncio.sleep(_POLL_INTERVAL_S)

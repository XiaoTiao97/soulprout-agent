"""云端定时任务调度：扫描到期任务、写入对话上下文、再推给 Gateway。"""

from __future__ import annotations

import asyncio
import json
import logging

from agent.api.models.message import ChatRequest
from agent.database.crud.outbound_delivery import (
    delivery_to_payload,
    enqueue_delivery,
    list_pending_deliveries,
)
from agent.database.crud.scheduled_task import (
    backfill_task_kind,
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
scheduler_started_at: str | None = None
scheduler_last_tick: str | None = None
scheduler_last_claimed: int = 0


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


def _task_kind(task: ScheduledTask) -> str:
    kind = getattr(task, "kind", None)
    inferred = resolve_task_kind(kind, task.instruction or "", task.notify_text or "")
    if (
        (task.notify_text or "").strip()
        and (task.instruction or "").strip() == (task.notify_text or "").strip()
    ):
        return "notify"
    return inferred


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
    """把 instruction 当作用户消息写入对话并跑一轮 Soul。"""
    from agent.core.config import Config
    from agent.services.agent import Chat

    config = Config()
    instruction = (task.instruction or "").strip()
    request = ChatRequest(
        message=instruction,
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
        if chunk_type == "user_feedback" or chunk_type == "error":
            parts.append(content)
        elif chunk.get("role") == "assistant" and chunk_type == "text":
            parts.append(content)
    return "".join(parts).strip()


async def push_delivery(delivery) -> bool:
    payload = delivery_to_payload(delivery)
    return await hub.send_json(delivery.user_id, payload)


async def dispatch_to_channel(task: ScheduledTask, content: str) -> None:
    channel = (task.channel or "web").strip().lower() or "web"
    chat_id = (task.chat_id or "").strip() or None
    if channel in _GATEWAY_CHANNELS and not chat_id:
        from agent.database.crud.user_channel_binding import get_channel_chat_id
        chat_id = await get_channel_chat_id(task.user_id, channel)
        if chat_id and not task.chat_id:
            task.chat_id = chat_id
            await task.save()
    if channel not in _GATEWAY_CHANNELS:
        print(
            f"[Scheduler] 网页渠道已写入对话 task={task.task_id} user={task.user_id}",
            flush=True,
        )
        return
    if not chat_id:
        msg = f"[Scheduler] 无 chat_id，无法投递到 {channel} task={task.task_id}"
        print(msg, flush=True)
        logger.warning(msg)
        return
    delivery = await enqueue_delivery(
        user_id=task.user_id,
        channel=channel,
        chat_id=chat_id,
        content=content,
        task_id=task.task_id,
    )
    pushed = await push_delivery(delivery)
    if pushed:
        msg = f"[Scheduler] 已推给 Gateway task={task.task_id} user={task.user_id} channel={channel}"
        print(msg, flush=True)
        logger.info(msg)
    else:
        msg = (
            f"[Scheduler] Gateway WebSocket 不在线，已入队等 HTTP/WS 拉取 "
            f"task={task.task_id} user={task.user_id} channel={channel}"
        )
        print(msg, flush=True)
        logger.info(msg)


async def _execute_notify(task: ScheduledTask) -> None:
    content = (task.notify_text or "").strip() or f"定时提醒：{task.title}"
    await _save_context_message(task, "assistant", content)
    await dispatch_to_channel(task, content)


async def _execute_agent(task: ScheduledTask) -> None:
    instruction = (task.instruction or "").strip()
    if not instruction:
        raise ValueError("任务模式缺少 instruction")
    reply = await _run_instruction(task)
    if not reply:
        reply = f"定时任务「{task.title}」已执行，但没有生成可发送的结果。"
        await _save_context_message(task, "assistant", reply)
    await dispatch_to_channel(task, reply)


async def _execute_task(task: ScheduledTask) -> None:
    kind = _task_kind(task)
    msg = (
        f"[Scheduler] 触发 task={task.task_id} kind={kind} user={task.user_id} "
        f"title={task.title} channel={task.channel} chat_id={task.chat_id} "
        f"next_run_at={task.next_run_at}"
    )
    print(msg, flush=True)
    logger.info(msg)
    try:
        if kind == "agent":
            await _execute_agent(task)
        else:
            await _execute_notify(task)
        await finish_scheduled_task(task)
    except Exception as exc:
        logger.error("[Scheduler] 执行失败 task=%s: %s", task.task_id, exc, exc_info=True)
        print(f"[Scheduler] 执行失败 task={task.task_id}: {exc}", flush=True)
        try:
            await finish_scheduled_task(task, error=str(exc))
        except Exception:
            logger.exception("[Scheduler] 回写任务状态失败 task=%s", task.task_id)


async def flush_pending_to_online_gateways() -> None:
    for user_id in hub.online_user_ids():
        pending = await list_pending_deliveries(user_id)
        for item in pending:
            if item.channel == "web":
                continue
            await hub.send_json(user_id, delivery_to_payload(item))


async def run_scheduler_loop() -> None:
    global scheduler_started_at, scheduler_last_tick, scheduler_last_claimed
    scheduler_started_at = datetime.utcnow().isoformat() + "Z"
    start_msg = f"[Scheduler] 定时任务调度器已启动，间隔 {_POLL_INTERVAL_S:.0f}s"
    print(start_msg, flush=True)
    logger.info(start_msg)
    try:
        filled = await backfill_task_kind()
        if filled:
            print(f"[Scheduler] 已补全 {filled} 条任务的 kind", flush=True)
    except Exception as exc:
        logger.warning("[Scheduler] 补全 kind 失败: %s", exc)
    while True:
        try:
            recovered = await recover_stale_running_tasks()
            due = await claim_due_tasks()
            online = hub.online_user_ids()
            scheduler_last_tick = datetime.utcnow().isoformat() + "Z"
            scheduler_last_claimed = len(due)
            tick = (
                f"[Scheduler] tick utc={scheduler_last_tick} "
                f"claimed={len(due)} recovered={recovered} gateway_online={len(online)}"
            )
            print(tick, flush=True)
            logger.info(tick)
            for task in due:
                await _execute_task(task)
            await flush_pending_to_online_gateways()
        except asyncio.CancelledError:
            logger.info("[Scheduler] 调度器已停止")
            raise
        except Exception as exc:
            logger.error("[Scheduler] 调度循环异常: %s", exc, exc_info=True)
            print(f"[Scheduler] 调度循环异常: {exc}", flush=True)
        await asyncio.sleep(_POLL_INTERVAL_S)

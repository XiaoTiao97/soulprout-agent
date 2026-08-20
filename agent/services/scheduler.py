"""云端定时任务调度：扫描到期任务、执行、再推给在线 Gateway。"""

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
    backfill_empty_notify_text,
    claim_due_tasks,
    finish_scheduled_task,
    recover_stale_running_tasks,
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


async def _run_instruction(task: ScheduledTask) -> str:
    from agent.core.config import Config
    from agent.services.agent import Chat

    config = Config()
    prompt = (
        f"【定时任务】{task.title}\n"
        f"{task.instruction.strip()}\n"
        "请直接执行并给出给用户看的最终结果。不要再创建或修改定时任务。"
    )
    request = ChatRequest(
        message=prompt,
        user_id=task.user_id,
        conversation_id=task.user_id,
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


async def _save_web_message(user_id: str, content: str) -> None:
    await AgentMessage(
        user_id=user_id,
        conversation_id=user_id,
        type="text",
        role="assistant",
        content=content,
        created_at=datetime.utcnow(),
    ).insert()


async def push_delivery(delivery) -> bool:
    if delivery.channel == "web" or not delivery.channel:
        try:
            await _save_web_message(delivery.user_id, delivery.content)
            from agent.database.crud.outbound_delivery import mark_delivery_sent
            await mark_delivery_sent(delivery.delivery_id)
            return True
        except Exception as exc:
            logger.error("[Scheduler] 写入网页对话失败 user=%s: %s", delivery.user_id, exc)
            return False

    payload = delivery_to_payload(delivery)
    return await hub.send_json(delivery.user_id, payload)


async def dispatch_task_result(task: ScheduledTask, content: str) -> None:
    channel = (task.channel or "web").strip().lower() or "web"
    chat_id = (task.chat_id or "").strip() or None
    if channel in _GATEWAY_CHANNELS and not chat_id:
        from agent.database.crud.user_channel_binding import get_channel_chat_id
        chat_id = await get_channel_chat_id(task.user_id, channel)
        if chat_id and not task.chat_id:
            task.chat_id = chat_id
            await task.save()
    delivery = await enqueue_delivery(
        user_id=task.user_id,
        channel=channel,
        chat_id=chat_id,
        content=content,
        task_id=task.task_id,
    )
    pushed = await push_delivery(delivery)
    if pushed:
        msg = f"[Scheduler] 已投递 task={task.task_id} user={task.user_id} channel={channel}"
        print(msg, flush=True)
        logger.info(msg)
    elif channel in _GATEWAY_CHANNELS:
        msg = (
            f"[Scheduler] Gateway 不在线，任务结果已入队 task={task.task_id} "
            f"user={task.user_id} channel={channel}"
        )
        print(msg, flush=True)
        logger.info(msg)


def _delivery_content(task: ScheduledTask) -> tuple[str, bool]:
    """返回 (投递文案, 是否还需要跑 Agent)。

    微信提醒必须能直接发出去：有 notify_text 就不再跑模型。
    只有「instruction 与 notify_text 不同」时才到点执行 Agent。
    """
    notify = (task.notify_text or "").strip()
    instruction = (task.instruction or "").strip()
    title = (task.title or "").strip()
    if notify and (not instruction or notify == instruction):
        return notify, False
    if instruction and notify and instruction != notify:
        return notify, True
    if notify:
        return notify, False
    if instruction:
        return instruction, False
    return f"定时提醒：{title}" if title else "定时提醒", False


async def _execute_task(task: ScheduledTask) -> None:
    msg = (
        f"[Scheduler] 触发 task={task.task_id} user={task.user_id} "
        f"title={task.title} channel={task.channel} next_run_at={task.next_run_at}"
    )
    print(msg, flush=True)
    logger.info(msg)
    try:
        fallback, need_agent = _delivery_content(task)
        content = fallback
        if need_agent and (task.instruction or "").strip():
            ran = await _run_instruction(task)
            if ran:
                content = ran
        if not content:
            content = f"定时提醒：{task.title}"
        await dispatch_task_result(task, content)
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
    start_msg = f"[Scheduler] 定时任务调度器已启动，间隔 {_POLL_INTERVAL_S:.0f}s"
    print(start_msg, flush=True)
    logger.info(start_msg)
    try:
        filled = await backfill_empty_notify_text()
        if filled:
            print(f"[Scheduler] 已补全 {filled} 条任务的 notify_text", flush=True)
    except Exception as exc:
        logger.warning("[Scheduler] 补全 notify_text 失败: %s", exc)
    while True:
        try:
            recovered = await recover_stale_running_tasks()
            due = await claim_due_tasks()
            online = hub.online_user_ids()
            tick = (
                f"[Scheduler] tick utc={datetime.utcnow().isoformat()}Z "
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

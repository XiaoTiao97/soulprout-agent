"""会话运行核心。

Agent 的一轮执行挂在这里，不挂在某条 SSE 连接上。
连接只是订阅者：断开只退订，不取消运行。
同一会话只保留最新一条待执行消息；新消息会打断当前轮并在结束后注入。
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional
from uuid import uuid4

from agent.api.models.message import ChatRequest

logger = logging.getLogger(__name__)


@dataclass
class PendingTurn:
    turn_id: str
    request: ChatRequest


@dataclass
class SubmitHandle:
    conversation_id: str
    turn_id: str
    queue: asyncio.Queue


@dataclass
class ConversationRun:
    conversation_id: str
    user_id: str
    mode: str = "task"
    abstract: str = ""
    status: str = "idle"
    started_at: float = 0.0
    turn_id: str = ""
    pending: Optional[PendingTurn] = None
    stop_requested: bool = False
    subscribers: set[asyncio.Queue] = field(default_factory=set)
    partial_text: str = ""
    partial_reasoning: str = ""
    partial_plan: str = ""
    partial_plan_progress: str = ""
    chat: Any = None
    turn_task: Optional[asyncio.Task] = None
    flush_task: Optional[asyncio.Task] = None
    supervisor: Optional[asyncio.Task] = None
    wakeup: asyncio.Event = field(default_factory=asyncio.Event)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class RunManager:
    def __init__(self) -> None:
        self._runs: dict[str, ConversationRun] = {}
        self._user_subs: dict[str, set[asyncio.Queue]] = {}
        self._lock = asyncio.Lock()

    def assign_conversation_id(self, request: ChatRequest) -> str:
        if request.agent_use == "soulprout":
            request.conversation_id = request.user_id or ""
            return request.conversation_id
        conversation_id = (request.conversation_id or "").strip()
        if not conversation_id:
            conversation_id = str(uuid4())
            request.conversation_id = conversation_id
        return conversation_id

    async def submit(self, request: ChatRequest) -> SubmitHandle:
        conversation_id = self.assign_conversation_id(request)
        if not conversation_id:
            raise ValueError("conversation_id 为空")
        turn_id = str(uuid4())
        queue: asyncio.Queue = asyncio.Queue()
        mode = "soulprout" if request.agent_use == "soulprout" else "task"

        async with self._lock:
            run = self._runs.get(conversation_id)
            if run is None:
                run = ConversationRun(
                    conversation_id=conversation_id,
                    user_id=request.user_id or "",
                    mode=mode,
                )
                self._runs[conversation_id] = run
            elif run.user_id and request.user_id and run.user_id != request.user_id:
                raise PermissionError("会话不属于当前用户")

        async with run.lock:
            run.user_id = request.user_id or run.user_id
            run.mode = mode
            queue.put_nowait(self._event(run, "accepted", turn_id, content=""))
            run.subscribers.add(queue)
            if run.pending is not None:
                self._broadcast(
                    run,
                    self._event(run, "interrupted", run.pending.turn_id, content=""),
                )
            run.pending = PendingTurn(turn_id=turn_id, request=request)
            run.stop_requested = False
            if run.chat is not None:
                run.chat.cancel_cleanup = False
            if run.turn_task is not None and not run.turn_task.done():
                run.turn_task.cancel()
            run.wakeup.set()
            self._ensure_supervisor(run)

        return SubmitHandle(conversation_id=conversation_id, turn_id=turn_id, queue=queue)

    async def stop(self, conversation_id: str, user_id: str) -> bool:
        conversation_id = (conversation_id or "").strip()
        if not conversation_id:
            return False
        async with self._lock:
            run = self._runs.get(conversation_id)
        if run is None or (run.user_id and run.user_id != user_id):
            return False
        async with run.lock:
            if run.status != "running" and run.pending is None and (
                run.turn_task is None or run.turn_task.done()
            ):
                return False
            run.stop_requested = True
            run.pending = None
            if run.chat is not None:
                run.chat.cancel_cleanup = True
            if run.turn_task is not None and not run.turn_task.done():
                run.turn_task.cancel()
            run.wakeup.set()
            self._ensure_supervisor(run)
        return True

    async def attach(self, conversation_id: str, user_id: str) -> tuple[ConversationRun, asyncio.Queue, Optional[dict]]:
        conversation_id = (conversation_id or "").strip()
        if not conversation_id:
            raise ValueError("conversation_id 为空")
        async with self._lock:
            run = self._runs.get(conversation_id)
            if run is None:
                run = ConversationRun(conversation_id=conversation_id, user_id=user_id)
                self._runs[conversation_id] = run
            elif run.user_id and run.user_id != user_id:
                raise PermissionError("会话不属于当前用户")
        queue: asyncio.Queue = asyncio.Queue()
        # 同步拷贝快照再加入订阅，避免和广播交叉导致重复或漏片段
        snapshot = self._snapshot(run)
        run.subscribers.add(queue)
        return run, queue, snapshot

    def detach(self, conversation_id: str, queue: asyncio.Queue) -> None:
        run = self._runs.get(conversation_id)
        if run is None:
            return
        run.subscribers.discard(queue)

    def detach_status(self, user_id: str, queue: asyncio.Queue) -> None:
        subs = self._user_subs.get(user_id)
        if not subs:
            return
        subs.discard(queue)
        if not subs:
            self._user_subs.pop(user_id, None)

    def list_running(self, user_id: str) -> list[dict]:
        items = []
        for run in self._runs.values():
            if run.user_id == user_id and run.status == "running":
                items.append(self._public_state(run))
        items.sort(key=lambda item: item.get("started_at") or 0, reverse=True)
        return items

    def subscribe_status(self, user_id: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        self._user_subs.setdefault(user_id, set()).add(queue)
        for item in self.list_running(user_id):
            queue.put_nowait({"type": "run_started", **item})
        return queue

    async def collect_reply(self, request: ChatRequest) -> tuple[str, str]:
        """跑完本轮。返回 (回复文本, done|interrupted|stopped)。被打断或停止时文本为空。"""
        handle = await self.submit(request)
        parts: list[str] = []
        feedback_parts: list[str] = []
        error_parts: list[str] = []
        try:
            while True:
                event = await handle.queue.get()
                status = self._observe_own_turn(event, handle.turn_id, parts, feedback_parts, error_parts)
                if status == "done":
                    return _compose_parts(parts, feedback_parts, error_parts), "done"
                if status in ("interrupted", "stopped"):
                    return "", status
        finally:
            self.detach(handle.conversation_id, handle.queue)

    def _ensure_supervisor(self, run: ConversationRun) -> None:
        if run.supervisor is not None and not run.supervisor.done():
            return
        run.supervisor = asyncio.create_task(self._supervise(run), name=f"run:{run.conversation_id}")

    async def _supervise(self, run: ConversationRun) -> None:
        while True:
            await run.wakeup.wait()
            while True:
                async with run.lock:
                    stop = run.stop_requested
                    pending = run.pending
                    run.stop_requested = False
                    run.pending = None
                    run.wakeup.clear()
                if pending is not None:
                    await self._execute(run, pending)
                    continue
                if stop:
                    await self._finish_stop(run)
                async with run.lock:
                    if run.pending is not None or run.stop_requested or run.wakeup.is_set():
                        continue
                await self._mark_idle(run)
                break

    async def _fill_abstract(self, run: ConversationRun) -> None:
        """已有会话的标题在建会话时写过一次。跟进消息不再发 abstract，这里从库里补上。"""
        if run.abstract:
            return
        from agent.database.crud.conversation import get_conversation_by_id

        existing = await get_conversation_by_id(run.conversation_id)
        abstract = (getattr(existing, "abstract", None) or "").strip() if existing else ""
        if not abstract:
            return
        async with run.lock:
            if not run.abstract:
                run.abstract = abstract

    async def _execute(self, run: ConversationRun, pending: PendingTurn) -> None:
        from agent.services.agent import Chat

        await self._fill_abstract(run)
        async with run.lock:
            if run.stop_requested:
                return
            was_running = run.status == "running"
            run.status = "running"
            run.turn_id = pending.turn_id
            if not was_running or not run.started_at:
                run.started_at = time.time()
            self._clear_partial(run)
            chat = Chat(pending.request)
            run.chat = chat
            started = None if was_running else {"type": "run_started", **self._public_state(run)}
        if started is not None:
            self._publish_user(run.user_id, started)
        self._broadcast(run, self._event(run, "turn_started", pending.turn_id, content=""))

        turn_task = asyncio.create_task(self._drive_turn(run, chat, pending.turn_id))
        async with run.lock:
            run.turn_task = turn_task
            if run.stop_requested:
                chat.cancel_cleanup = True
                turn_task.cancel()
        try:
            await turn_task
        except asyncio.CancelledError:
            if not turn_task.done():
                turn_task.cancel()
            raise
        finally:
            flush_task = run.flush_task
            run.flush_task = None
        if flush_task is not None:
            try:
                await flush_task
            except Exception as exc:
                logger.warning("[RunManager] 取消后落库失败: %s", exc)

    async def _drive_turn(self, run: ConversationRun, chat: Any, turn_id: str) -> None:
        try:
            async for raw in chat.run():
                event = json.loads(raw) if isinstance(raw, str) else dict(raw)
                if not isinstance(event, dict):
                    continue
                event["turn_id"] = turn_id
                self._note_and_broadcast(run, event)
        except asyncio.CancelledError:
            # 不要在已取消的任务里 await 落库，否则取消会立刻再次抛出，落库任务得不到执行。
            run.flush_task = asyncio.create_task(chat.flush_partial())
            self._clear_partial(run)
            if not run.stop_requested:
                self._broadcast(run, self._event(run, "interrupted", turn_id, content=""))
            return
        except Exception as exc:
            logger.exception("[RunManager] 会话运行失败 conv=%s", run.conversation_id)
            self._clear_partial(run)
            self._broadcast(
                run,
                self._event(run, "error", turn_id, content=f"回复异常，原因：{exc}"),
            )
            self._broadcast(run, self._event(run, "turn_done", turn_id, content=""))
            return
        self._clear_partial(run)
        self._broadcast(run, self._event(run, "turn_done", turn_id, content=""))

    async def _finish_stop(self, run: ConversationRun) -> None:
        async with run.lock:
            was_running = run.status == "running" or run.turn_id
            turn_id = run.turn_id
            run.status = "idle"
            run.chat = None
            run.turn_task = None
            self._clear_partial(run)
        if not was_running:
            return
        self._broadcast(run, self._event(run, "stopped", turn_id, content=""))
        self._publish_user(run.user_id, {"type": "run_finished", "conversation_id": run.conversation_id})

    async def _mark_idle(self, run: ConversationRun) -> None:
        async with run.lock:
            if run.status != "running":
                return
            if run.pending is not None or run.stop_requested:
                return
            if run.turn_task is not None and not run.turn_task.done():
                return
            run.status = "idle"
            run.chat = None
            run.turn_task = None
            self._clear_partial(run)
            conversation_id = run.conversation_id
            user_id = run.user_id
        self._publish_user(user_id, {"type": "run_finished", "conversation_id": conversation_id})

    def _note_and_broadcast(self, run: ConversationRun, event: dict) -> None:
        event_type = event.get("type")
        content = event.get("content") or ""
        if event_type == "text" and event.get("role", "assistant") == "assistant":
            run.partial_text += content
        elif event_type == "reasoner_content":
            run.partial_reasoning += content
        elif event_type == "plan":
            run.partial_plan += content
        elif event_type == "plan_progress":
            run.partial_plan_progress += content
        elif event_type in ("get_tools", "get_agents"):
            run.partial_text = ""
            run.partial_reasoning = ""
        elif event_type == "tool" and event.get("role") == "tool":
            run.partial_plan = ""
            run.partial_plan_progress = ""
        if event_type == "abstract" and content:
            run.abstract = content
            self._publish_user(
                run.user_id,
                {"type": "run_updated", "conversation_id": run.conversation_id, "abstract": content},
            )
        self._broadcast(run, event)

    def _clear_partial(self, run: ConversationRun) -> None:
        run.partial_text = ""
        run.partial_reasoning = ""
        run.partial_plan = ""
        run.partial_plan_progress = ""

    def _snapshot(self, run: ConversationRun) -> Optional[dict]:
        if run.status != "running":
            return None
        if not any((run.partial_text, run.partial_reasoning, run.partial_plan, run.partial_plan_progress)):
            return {
                "type": "snapshot",
                "turn_id": run.turn_id,
                "conversation_id": run.conversation_id,
                "user_id": run.user_id,
                "role": "assistant",
                "content": "",
                "reasoning_content": "",
                "plan": "",
                "plan_progress": "",
                "running": True,
            }
        return {
            "type": "snapshot",
            "turn_id": run.turn_id,
            "conversation_id": run.conversation_id,
            "user_id": run.user_id,
            "role": "assistant",
            "content": run.partial_text,
            "reasoning_content": run.partial_reasoning,
            "plan": run.partial_plan,
            "plan_progress": run.partial_plan_progress,
            "running": True,
        }

    def _broadcast(self, run: ConversationRun, event: dict) -> None:
        for queue in list(run.subscribers):
            try:
                queue.put_nowait(event)
            except Exception as exc:
                logger.warning("[RunManager] 推送失败 conv=%s: %s", run.conversation_id, exc)

    def _publish_user(self, user_id: str, event: dict) -> None:
        if not user_id:
            return
        for queue in list(self._user_subs.get(user_id) or ()):
            try:
                queue.put_nowait(event)
            except Exception as exc:
                logger.warning("[RunManager] 状态推送失败 user=%s: %s", user_id, exc)

    def _public_state(self, run: ConversationRun) -> dict:
        return {
            "conversation_id": run.conversation_id,
            "user_id": run.user_id,
            "mode": run.mode,
            "abstract": run.abstract,
            "started_at": int(run.started_at * 1000) if run.started_at else 0,
            "turn_id": run.turn_id,
            "status": run.status,
        }

    def _event(self, run: ConversationRun, event_type: str, turn_id: str, content: str = "") -> dict:
        return {
            "type": event_type,
            "turn_id": turn_id,
            "conversation_id": run.conversation_id,
            "user_id": run.user_id,
            "role": "assistant",
            "content": content,
        }

    @staticmethod
    def _observe_own_turn(
        event: dict,
        turn_id: str,
        parts: list[str],
        feedback_parts: list[str],
        error_parts: list[str],
    ) -> Optional[str]:
        event_turn = event.get("turn_id")
        event_type = event.get("type")
        if event_turn and event_turn != turn_id:
            return None
        if event_type in ("interrupted", "stopped", "turn_done") and event_turn == turn_id:
            if event_type == "turn_done":
                return "done"
            return event_type
        if event_turn != turn_id:
            return None
        _ingest_reply_chunk(event, parts, feedback_parts, error_parts)
        return None


def _ingest_reply_chunk(
    chunk: dict,
    parts: list[str],
    feedback_parts: list[str],
    error_parts: list[str],
) -> None:
    content = chunk.get("content") or ""
    if not content:
        return
    chunk_type = chunk.get("type")
    if chunk_type == "user_feedback":
        feedback_parts.append(content)
    elif chunk_type == "error":
        error_parts.append(content)
    elif chunk.get("role", "assistant") == "assistant" and chunk_type == "text":
        parts.append(content)


def _compose_parts(parts: list[str], feedback_parts: list[str], error_parts: list[str]) -> str:
    segments: list[str] = []
    if parts:
        segments.append("".join(parts).strip())
    if feedback_parts:
        segments.append("\n\n".join(feedback_parts).strip())
    if error_parts and not parts:
        segments.append("\n\n".join(error_parts).strip())
    reply = "\n\n".join(segment for segment in segments if segment).strip()
    return reply if reply else "（无回复）"


run_manager = RunManager()

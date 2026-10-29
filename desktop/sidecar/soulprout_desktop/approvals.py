"""用户审批：本地工具需要用户点头时，把请求推给桌面界面，等用户决定。

结果词表沿用 deepseek-harness 的 approval 结果（见 desktop/NOTICE.md）：
``allowed-once`` / ``rejected`` / ``cancelled`` / ``unavailable``，调用方据此 fail-closed：

- 没有任何界面在监听（用户没开窗口）→ ``unavailable``；
- 用户拒绝 → ``rejected``；
- 等待超时、或这次工具调用已被云端取消（比如用户在网页上点了「停止」）→ ``cancelled``。

只有一次性放行（``allowed-once``）：批准只对当前这一次调用有效，不会变成长期授权。
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

ALLOWED_ONCE = "allowed-once"
REJECTED = "rejected"
CANCELLED = "cancelled"
UNAVAILABLE = "unavailable"

APPROVAL_TIMEOUT_S = 600.0
SUBSCRIBER_GRACE_S = 3.0


@dataclass
class ApprovalRequest:
    id: str
    tool: str
    title: str
    detail: str
    reason: str
    mode: str
    target_mode: str
    conversation_id: str
    created_at: float = field(default_factory=time.time)
    call_id: Optional[str] = None
    future: Optional["asyncio.Future"] = None

    def public(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "tool": self.tool,
            "title": self.title,
            "detail": self.detail,
            "reason": self.reason,
            "mode": self.mode,
            "target_mode": self.target_mode,
            "conversation_id": self.conversation_id,
            "created_at": self.created_at,
        }


class ApprovalBroker:
    def __init__(self, timeout: float = APPROVAL_TIMEOUT_S, subscriber_grace: float = SUBSCRIBER_GRACE_S):
        self._pending: Dict[str, ApprovalRequest] = {}
        self._subscribers: List["asyncio.Queue"] = []
        self._timeout = timeout
        self._grace = subscriber_grace

    # ------------------------------------------------------------------ 订阅（界面侧）

    def subscribe(self) -> "asyncio.Queue":
        queue: "asyncio.Queue" = asyncio.Queue()
        for req in self._pending.values():
            queue.put_nowait({"type": "request", "request": req.public()})
        self._subscribers.append(queue)
        return queue

    def unsubscribe(self, queue: "asyncio.Queue") -> None:
        if queue in self._subscribers:
            self._subscribers.remove(queue)

    @property
    def has_subscribers(self) -> bool:
        return bool(self._subscribers)

    def _publish(self, event: Dict[str, Any]) -> None:
        for queue in list(self._subscribers):
            queue.put_nowait(event)

    def pending(self) -> List[Dict[str, Any]]:
        return [req.public() for req in self._pending.values()]

    # ------------------------------------------------------------------ 请求（工具侧）

    async def request(
        self,
        *,
        tool: str,
        title: str,
        detail: str,
        reason: str,
        mode: str,
        target_mode: str,
        conversation_id: str,
        call_id: Optional[str] = None,
    ) -> str:
        deadline = time.monotonic() + self._grace
        while not self._subscribers and time.monotonic() < deadline:
            await asyncio.sleep(0.1)  # 界面刚启动/刚重连时 SSE 可能还没连上，给个短暂缓冲
        if not self._subscribers:
            return UNAVAILABLE

        req = ApprovalRequest(
            id=uuid.uuid4().hex,
            tool=tool,
            title=title,
            detail=detail,
            reason=reason,
            mode=mode,
            target_mode=target_mode,
            conversation_id=conversation_id,
            call_id=call_id,
            future=asyncio.get_running_loop().create_future(),
        )
        self._pending[req.id] = req
        self._publish({"type": "request", "request": req.public()})
        try:
            return await asyncio.wait_for(asyncio.shield(req.future), self._timeout)
        except asyncio.TimeoutError:
            return CANCELLED
        except asyncio.CancelledError:
            # 工具调用被取消：撤回待办，界面上的弹窗随 resolved 事件关闭
            raise
        finally:
            self._pending.pop(req.id, None)
            if not req.future.done():
                req.future.cancel()
            self._publish({"type": "resolved", "id": req.id})

    # ------------------------------------------------------------------ 决定（界面侧）

    def decide(self, request_id: str, decision: str) -> bool:
        req = self._pending.get(request_id)
        if req is None or req.future is None or req.future.done():
            return False
        outcome = ALLOWED_ONCE if decision in ("allow", "allow-once", ALLOWED_ONCE) else REJECTED
        req.future.set_result(outcome)
        return True

    def cancel_call(self, call_id: str) -> None:
        for req in list(self._pending.values()):
            if req.call_id == call_id and req.future is not None and not req.future.done():
                req.future.set_result(CANCELLED)

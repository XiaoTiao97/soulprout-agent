"""Gateway 长连接登记：user_id -> 当前 WebSocket 集合。"""

from __future__ import annotations

import asyncio
import logging
from typing import Dict, Set

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class GatewayHub:
    def __init__(self):
        self._conns: Dict[str, Set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def register(self, user_id: str, ws: WebSocket) -> None:
        async with self._lock:
            self._conns.setdefault(user_id, set()).add(ws)
        n = len(self._conns.get(user_id, ()))
        logger.info("[GatewayHub] 已连接 user=%s 当前连接数=%d", user_id, n)
        print(f"[GatewayHub] 已连接 user={user_id} 当前连接数={n}", flush=True)

    async def unregister(self, user_id: str, ws: WebSocket) -> None:
        async with self._lock:
            conns = self._conns.get(user_id)
            if not conns:
                return
            conns.discard(ws)
            if not conns:
                self._conns.pop(user_id, None)
        logger.info("[GatewayHub] 已断开 user=%s", user_id)

    def online_user_ids(self) -> list[str]:
        return [user_id for user_id, conns in self._conns.items() if conns]

    async def send_json(self, user_id: str, payload: dict) -> bool:
        conns = list(self._conns.get(user_id) or ())
        if not conns:
            return False
        sent = False
        dead: list[WebSocket] = []
        for ws in conns:
            try:
                await ws.send_json(payload)
                sent = True
            except Exception as exc:
                logger.warning("[GatewayHub] 推送失败 user=%s: %s", user_id, exc)
                dead.append(ws)
        for ws in dead:
            await self.unregister(user_id, ws)
        return sent


hub = GatewayHub()

"""Gateway 在线连接：user_id → WebSocket。空闲连接不跑业务，只在投递时写一帧。"""

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

    async def unregister(self, user_id: str, ws: WebSocket) -> None:
        async with self._lock:
            conns = self._conns.get(user_id)
            if not conns:
                return
            conns.discard(ws)
            if not conns:
                self._conns.pop(user_id, None)

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

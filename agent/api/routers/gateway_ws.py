"""Gateway 长连接：登记在线状态，下发到期任务结果。"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import asyncio

from agent.database.crud.outbound_delivery import (
    delivery_to_payload,
    list_pending_deliveries,
    mark_delivery_sent,
)
from agent.services.auth import get_current_user
from agent.services.gateway_hub import hub

logger = logging.getLogger(__name__)

router = APIRouter()


def _token_from_ws(ws: WebSocket) -> Optional[str]:
    token = (ws.query_params.get("token") or "").strip()
    if token:
        return token
    auth = ws.headers.get("authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    cookie = ws.cookies.get("token") or ""
    return cookie.strip() or None


@router.websocket("/gateway/ws")
async def gateway_outbound_ws(ws: WebSocket):
    await ws.accept()
    token = _token_from_ws(ws)
    if not token:
        await ws.close(code=1008)
        return
    try:
        user = await get_current_user(token)
    except Exception:
        await ws.close(code=1008)
        return

    user_id = str(user.user_id)
    await hub.register(user_id, ws)
    try:
        pending = await list_pending_deliveries(user_id)
        for item in pending:
            if item.channel == "web":
                continue
            try:
                await ws.send_json(delivery_to_payload(item))
            except Exception as exc:
                logger.warning("[GatewayWS] 补发失败 user=%s: %s", user_id, exc)
                break

        while True:
            try:
                data = await asyncio.wait_for(ws.receive_json(), timeout=25)
            except asyncio.TimeoutError:
                await ws.send_json({"type": "ping"})
                continue
            if not isinstance(data, dict):
                continue
            msg_type = data.get("type")
            if msg_type in ("pong", "ping"):
                if msg_type == "ping":
                    await ws.send_json({"type": "pong"})
                continue
            if msg_type == "ack":
                delivery_id = str(data.get("delivery_id") or "").strip()
                if delivery_id:
                    await mark_delivery_sent(delivery_id)
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.warning("[GatewayWS] 连接异常 user=%s: %s", user_id, exc)
    finally:
        await hub.unregister(user_id, ws)

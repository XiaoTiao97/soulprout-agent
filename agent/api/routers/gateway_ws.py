"""Gateway 长连接与 HTTP 拉取：登记在线状态，下发到期任务结果。"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from pydantic import BaseModel
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


def _token_from_request(request: Request) -> Optional[str]:
    token = (request.cookies.get("token") or "").strip()
    if token:
        return token
    auth = request.headers.get("Authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    token = (request.query_params.get("token") or "").strip()
    return token or None


async def _user_from_token(token: Optional[str]):
    if not token:
        return None
    try:
        return await get_current_user(token)
    except Exception as exc:
        logger.warning("[GatewayWS] 鉴权失败: %s", exc)
        return None


async def _push_pending(ws: WebSocket, user_id: str) -> int:
    pending = await list_pending_deliveries(user_id)
    sent = 0
    for item in pending:
        if item.channel == "web":
            continue
        try:
            await ws.send_json(delivery_to_payload(item))
            sent += 1
        except Exception as exc:
            logger.warning("[GatewayWS] 下发失败 user=%s: %s", user_id, exc)
            break
    return sent


@router.get("/gateway/outbound/pending")
async def list_outbound_pending(request: Request):
    user = await _user_from_token(_token_from_request(request))
    if user is None:
        return JSONResponse({"deliveries": [], "error": "unauthorized"}, status_code=401)
    items = await list_pending_deliveries(str(user.user_id))
    return {
        "deliveries": [
            delivery_to_payload(item)
            for item in items
            if (item.channel or "") != "web"
        ]
    }


@router.get("/gateway/outbound/status")
async def outbound_status(request: Request):
    user = await _user_from_token(_token_from_request(request))
    if user is None:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    from agent.services import scheduler as scheduler_mod
    pending = await list_pending_deliveries(str(user.user_id))
    return {
        "ok": True,
        "user_id": str(user.user_id),
        "scheduler_started_at": scheduler_mod.scheduler_started_at,
        "scheduler_last_tick": scheduler_mod.scheduler_last_tick,
        "scheduler_last_claimed": scheduler_mod.scheduler_last_claimed,
        "gateway_ws_online": str(user.user_id) in hub.online_user_ids(),
        "gateway_ws_online_count": len(hub.online_user_ids()),
        "pending_count": len([i for i in pending if (i.channel or "") != "web"]),
    }


class OutboundAckBody(BaseModel):
    delivery_id: str


@router.post("/gateway/outbound/ack")
async def ack_outbound(request: Request, body: OutboundAckBody):
    user = await _user_from_token(_token_from_request(request))
    if user is None:
        return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
    delivery_id = (body.delivery_id or "").strip()
    if not delivery_id:
        return {"ok": False, "error": "delivery_id required"}
    item = await mark_delivery_sent(delivery_id)
    return {"ok": bool(item), "delivery_id": delivery_id}


@router.websocket("/gateway/ws")
async def gateway_outbound_ws(ws: WebSocket):
    await ws.accept()
    token = _token_from_ws(ws)
    user = await _user_from_token(token)
    if user is None:
        print("[GatewayWS] 连接被拒绝：token 无效或缺失", flush=True)
        await ws.close(code=1008)
        return

    user_id = str(user.user_id)
    await hub.register(user_id, ws)
    try:
        await _push_pending(ws, user_id)
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
            if msg_type == "pull":
                await _push_pending(ws, user_id)
                continue
            if msg_type == "ack":
                delivery_id = str(data.get("delivery_id") or "").strip()
                if delivery_id:
                    await mark_delivery_sent(delivery_id)
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.warning("[GatewayWS] 连接异常 user=%s: %s", user_id, exc)
        print(f"[GatewayWS] 连接异常 user={user_id}: {exc}", flush=True)
    finally:
        await hub.unregister(user_id, ws)

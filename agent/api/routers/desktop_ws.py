"""桌面端长连接：``/desktop/ws``。

帧约定（JSON）：

桌面端 → 云端
    hello        {device_id, device_name, info:{os, os_family, shell, home, app_version}, channels:{weixin: bool, ...}}
                 连上后必须先发这一帧。
    ping         {channels?}           心跳（约 25 秒一次），可顺带上报渠道连接状态
    channels     {channels:{...}}      渠道状态变化时上报
    tool_result  {call_id, ok, result|error}

云端 → 桌面端
    ready        {heartbeat_timeout}
    pong
    tool_call    {call_id, tool, arguments, conversation_id, context}
    cancel       {call_id}

与 ``/gateway/ws``（消息投递通道）互不影响：桌面端合并 gateway 后会同时连这两条。
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Any, Dict, Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from agent.services.auth import get_current_user
from agent.services.desktop_hub import HEARTBEAT_TIMEOUT_S, DesktopConn, hub

logger = logging.getLogger(__name__)
router = APIRouter()

_DEVICE_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_HELLO_TIMEOUT_S = 15.0
_INFO_KEYS = ("os", "os_family", "shell", "home", "app_version", "arch")


def _token_from_ws(ws: WebSocket) -> Optional[str]:
    token = (ws.query_params.get("token") or "").strip()
    if token:
        return token
    auth = ws.headers.get("authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return (ws.cookies.get("token") or "").strip() or None


def _clean_info(raw: Any) -> Dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    return {k: str(raw[k])[:200] for k in _INFO_KEYS if raw.get(k) is not None}


def _clean_channels(raw: Any) -> Dict[str, bool]:
    if not isinstance(raw, dict):
        return {}
    return {str(k)[:32]: bool(v) for k, v in list(raw.items())[:20]}


@router.websocket("/desktop/ws")
async def desktop_ws(ws: WebSocket):
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

    try:
        hello = await asyncio.wait_for(ws.receive_json(), timeout=_HELLO_TIMEOUT_S)
    except Exception:
        await ws.close(code=1008)
        return
    device_id = str((hello or {}).get("device_id") or "").strip() if isinstance(hello, dict) else ""
    if not isinstance(hello, dict) or hello.get("type") != "hello" or not _DEVICE_ID_RE.match(device_id):
        await ws.close(code=1008)
        return

    conn = DesktopConn(
        ws=ws,
        user_id=user_id,
        device_id=device_id,
        device_name=str(hello.get("device_name") or "")[:80],
        info=_clean_info(hello.get("info")),
        channels=_clean_channels(hello.get("channels")),
    )
    await hub.register(conn)
    logger.info("[DesktopWS] 上线 user=%s device=%s", user_id, device_id)
    try:
        await ws.send_json({"type": "ready", "heartbeat_timeout": HEARTBEAT_TIMEOUT_S})
        while True:
            try:
                data = await asyncio.wait_for(ws.receive_json(), timeout=HEARTBEAT_TIMEOUT_S)
            except asyncio.TimeoutError:
                logger.info("[DesktopWS] 心跳超时，判定离线 user=%s device=%s", user_id, device_id)
                break
            if not isinstance(data, dict):
                continue
            conn.last_seen = time.time()  # 任何帧都算活跃
            msg_type = data.get("type")
            if msg_type == "ping":
                channels = _clean_channels(data["channels"]) if "channels" in data else None
                await hub.touch(conn, channels)
                await ws.send_json({"type": "pong"})
            elif msg_type == "channels":
                await hub.touch(conn, _clean_channels(data.get("channels")))
            elif msg_type == "tool_result":
                hub.handle_result(conn, data)
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.warning("[DesktopWS] 连接异常 user=%s device=%s: %s", user_id, device_id, exc)
    finally:
        await hub.unregister(conn)
        try:
            await ws.close()
        except Exception:
            pass
        logger.info("[DesktopWS] 下线 user=%s device=%s", user_id, device_id)

"""Gateway 到云端 Agent 的投递长连接。"""

from __future__ import annotations

import asyncio
import json
import logging
from collections import deque
from typing import Deque, Set

logger = logging.getLogger(__name__)

_seen_ids: Deque[str] = deque(maxlen=500)
_seen_set: Set[str] = set()


def _remember(delivery_id: str) -> bool:
    """返回 True 表示已经处理过。"""
    if not delivery_id:
        return False
    if delivery_id in _seen_set:
        return True
    if len(_seen_ids) == _seen_ids.maxlen:
        old = _seen_ids.popleft()
        _seen_set.discard(old)
    _seen_ids.append(delivery_id)
    _seen_set.add(delivery_id)
    return False


async def _deliver_to_platform(channel: str, chat_id: str, content: str) -> bool:
    from gateway.main import get_platform_adapter

    adapter = get_platform_adapter(channel)
    if adapter is None:
        logger.warning("[Outbound] 无对应 adapter channel=%s", channel)
        return False
    connected = getattr(adapter, "is_connected", False)
    if not connected:
        logger.warning("[Outbound] adapter 未连接 channel=%s", channel)
        return False
    if not chat_id:
        logger.warning("[Outbound] chat_id 为空 channel=%s", channel)
        return False
    result = await adapter.send(chat_id, content)
    if not result.success:
        logger.error("[Outbound] 发送失败 channel=%s: %s", channel, result.error)
        return False
    logger.info("[Outbound] 已投递 channel=%s chat=%s", channel, chat_id)
    return True


async def _handle_message(ws, data: dict) -> None:
    msg_type = data.get("type")
    if msg_type == "ping":
        await ws.send_json({"type": "pong"})
        return
    if msg_type != "deliver":
        return

    delivery_id = str(data.get("delivery_id") or "").strip()
    channel = str(data.get("channel") or "").strip()
    chat_id = str(data.get("chat_id") or "").strip()
    content = data.get("content") or ""
    already = _remember(delivery_id)
    if already:
        if delivery_id:
            await ws.send_json({"type": "ack", "delivery_id": delivery_id})
        return
    ok = await _deliver_to_platform(channel, chat_id, content)
    if ok and delivery_id:
        await ws.send_json({"type": "ack", "delivery_id": delivery_id})
    elif delivery_id:
        _seen_set.discard(delivery_id)
        try:
            _seen_ids.remove(delivery_id)
        except ValueError:
            pass


async def _connect_and_listen(token: str, stop_event: asyncio.Event) -> None:
    import aiohttp
    from urllib.parse import quote
    from gateway.chat_caller import _make_ssl_connector
    from gateway.config_store import get_agent_url, ws_path

    url = ws_path(get_agent_url(), "/gateway/ws")
    headers = {"Authorization": f"Bearer {token}"}
    connect_url = f"{url}?token={quote(token)}"
    connector = _make_ssl_connector()
    timeout = aiohttp.ClientTimeout(total=None, sock_read=90)
    logger.info("[Outbound] 连接云端投递通道 %s", url)
    async with aiohttp.ClientSession(
        timeout=timeout,
        connector=connector,
        trust_env=True,
    ) as session:
        async with session.ws_connect(
            connect_url,
            headers=headers,
            heartbeat=20,
            receive_timeout=90,
        ) as ws:
            logger.info("[Outbound] 投递通道已连接")
            async for msg in ws:
                if stop_event.is_set():
                    await ws.close()
                    return
                if msg.type == aiohttp.WSMsgType.TEXT:
                    try:
                        data = json.loads(msg.data)
                    except (json.JSONDecodeError, TypeError):
                        continue
                    if isinstance(data, dict):
                        await _handle_message(ws, data)
                elif msg.type in (
                    aiohttp.WSMsgType.CLOSED,
                    aiohttp.WSMsgType.ERROR,
                    aiohttp.WSMsgType.CLOSE,
                ):
                    logger.warning("[Outbound] 投递通道断开 type=%s", msg.type)
                    return


async def run_outbound_loop(stop_event: asyncio.Event) -> None:
    """登录后维持与 Agent 的 WebSocket，接收定时任务投递。"""
    delay = 3.0
    while not stop_event.is_set():
        from gateway.config_store import get_agent_token

        token = (get_agent_token() or "").strip()
        if not token:
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=8)
            except asyncio.TimeoutError:
                continue
            continue
        try:
            await _connect_and_listen(token, stop_event)
            delay = 3.0
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("[Outbound] 投递通道异常: %s", exc)
            delay = min(delay * 1.5, 30)
        if stop_event.is_set():
            break
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=delay)
        except asyncio.TimeoutError:
            pass

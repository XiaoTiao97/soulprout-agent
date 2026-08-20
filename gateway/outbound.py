"""Gateway 到云端的空闲 WebSocket：到点收推送，不轮询。"""

from __future__ import annotations

import asyncio
import json
import logging
from collections import deque
from typing import Deque, Set
from urllib.parse import quote

import aiohttp

logger = logging.getLogger(__name__)

_seen_ids: Deque[str] = deque(maxlen=500)
_seen_set: Set[str] = set()


def _remember(delivery_id: str) -> bool:
    if not delivery_id or delivery_id in _seen_set:
        return bool(delivery_id)
    if len(_seen_ids) == _seen_ids.maxlen:
        _seen_set.discard(_seen_ids.popleft())
    _seen_ids.append(delivery_id)
    _seen_set.add(delivery_id)
    return False


def _forget(delivery_id: str) -> None:
    if not delivery_id:
        return
    _seen_set.discard(delivery_id)
    try:
        _seen_ids.remove(delivery_id)
    except ValueError:
        pass


def _ws_urls(agent_url: str) -> list[str]:
    from gateway.config_store import ws_path

    primary = ws_path(agent_url, "/gateway/ws")
    urls = [primary]
    alt = primary.replace("/api/gateway/ws", "/gateway/ws")
    if alt != primary:
        urls.append(alt)
    return urls


async def _deliver_to_platform(channel: str, chat_id: str, content: str) -> bool:
    from gateway.platform_registry import get_platform_adapter

    channel = (channel or "").strip().lower()
    adapter = get_platform_adapter(channel)
    if adapter is None:
        logger.warning("[Outbound] 无对应 adapter channel=%s", channel)
        return False
    if not getattr(adapter, "is_connected", False):
        logger.warning("[Outbound] adapter 未连接 channel=%s", channel)
        return False
    if not chat_id or not (content or "").strip():
        logger.warning("[Outbound] chat_id 或内容为空 channel=%s", channel)
        return False
    result = await adapter.send(chat_id, content)
    if not result.success:
        logger.error("[Outbound] 发送失败 channel=%s: %s", channel, result.error)
        return False
    logger.info("[Outbound] 已投递 channel=%s", channel)
    return True


async def _handle_message(ws, data: dict) -> None:
    msg_type = data.get("type")
    if msg_type == "ping":
        await ws.send_json({"type": "pong"})
        return
    if msg_type != "deliver":
        return
    delivery_id = str(data.get("delivery_id") or "").strip()
    if _remember(delivery_id):
        if delivery_id:
            await ws.send_json({"type": "ack", "delivery_id": delivery_id})
        return
    ok = await _deliver_to_platform(
        str(data.get("channel") or ""),
        str(data.get("chat_id") or ""),
        data.get("content") or "",
    )
    if ok and delivery_id:
        await ws.send_json({"type": "ack", "delivery_id": delivery_id})
    else:
        _forget(delivery_id)


async def _connect_and_listen(token: str, url: str, stop_event: asyncio.Event) -> None:
    from gateway.chat_caller import _make_ssl_connector

    headers = {"Authorization": f"Bearer {token}"}
    connect_url = f"{url}?token={quote(token)}"
    timeout = aiohttp.ClientTimeout(total=None, sock_connect=30, sock_read=None)
    logger.info("[Outbound] 连接投递通道 %s", url)
    async with aiohttp.ClientSession(
        timeout=timeout,
        connector=_make_ssl_connector(),
        trust_env=True,
    ) as session:
        async with session.ws_connect(
            connect_url,
            headers=headers,
            heartbeat=20,
            receive_timeout=None,
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
    delay = 3.0
    url_index = 0
    while not stop_event.is_set():
        from gateway.config_store import get_agent_token, get_agent_url

        token = (get_agent_token() or "").strip()
        if not token:
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=8)
            except asyncio.TimeoutError:
                continue
            continue
        urls = _ws_urls(get_agent_url())
        url = urls[url_index % len(urls)]
        try:
            await _connect_and_listen(token, url, stop_event)
            delay = 3.0
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("[Outbound] 投递通道异常 %s: %s", url, exc)
            if "404" in str(exc) and len(urls) > 1:
                url_index += 1
            delay = min(delay * 1.5, 30)
        if stop_event.is_set():
            break
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=delay)
        except asyncio.TimeoutError:
            pass

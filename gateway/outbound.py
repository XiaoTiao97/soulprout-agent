"""Gateway 到云端 Agent 的投递通道：WebSocket + HTTP 拉取。"""

from __future__ import annotations

import asyncio
import json
import logging
from collections import deque
from typing import Deque, Set

logger = logging.getLogger(__name__)

_seen_ids: Deque[str] = deque(maxlen=500)
_seen_set: Set[str] = set()
_HTTP_PULL_INTERVAL_S = 15.0
_warned_pending_404 = False


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


def _forget(delivery_id: str) -> None:
    if not delivery_id:
        return
    _seen_set.discard(delivery_id)
    try:
        _seen_ids.remove(delivery_id)
    except ValueError:
        pass


async def _deliver_to_platform(channel: str, chat_id: str, content: str) -> bool:
    from gateway.main import get_platform_adapter

    channel = (channel or "").strip().lower()
    adapter = get_platform_adapter(channel)
    if adapter is None:
        logger.warning("[Outbound] 无对应 adapter channel=%s", channel)
        print(f"[Outbound] 无对应 adapter channel={channel}", flush=True)
        return False
    connected = bool(getattr(adapter, "is_connected", False))
    if not connected:
        logger.warning("[Outbound] adapter 未连接 channel=%s", channel)
        print(f"[Outbound] adapter 未连接 channel={channel}", flush=True)
        return False
    if not chat_id:
        logger.warning("[Outbound] chat_id 为空 channel=%s", channel)
        print(f"[Outbound] chat_id 为空 channel={channel}", flush=True)
        return False
    if not (content or "").strip():
        logger.warning("[Outbound] 内容为空 channel=%s", channel)
        return False
    result = await adapter.send(chat_id, content)
    if not result.success:
        logger.error("[Outbound] 发送失败 channel=%s chat=%s: %s", channel, chat_id, result.error)
        print(f"[Outbound] 发送失败 channel={channel}: {result.error}", flush=True)
        return False
    logger.info("[Outbound] 已投递 channel=%s chat=%s", channel, chat_id)
    print(f"[Outbound] 已投递 channel={channel} chat={chat_id[:12]}", flush=True)
    return True


async def _handle_deliver(data: dict) -> bool:
    delivery_id = str(data.get("delivery_id") or "").strip()
    channel = str(data.get("channel") or "").strip()
    chat_id = str(data.get("chat_id") or "").strip()
    content = data.get("content") or ""
    already = _remember(delivery_id)
    if already:
        return True
    ok = await _deliver_to_platform(channel, chat_id, content)
    if ok:
        return True
    _forget(delivery_id)
    return False


async def _ack_delivery(session, token: str, delivery_id: str, ws=None) -> None:
    if not delivery_id:
        return
    if ws is not None:
        try:
            await ws.send_json({"type": "ack", "delivery_id": delivery_id})
            return
        except Exception:
            pass
    try:
        from gateway.chat_caller import _make_ssl_connector
        from gateway.config_store import api_path, get_agent_url
        import aiohttp

        url = api_path(get_agent_url(), "/gateway/outbound/ack")
        headers, cookies = _auth_headers(token)
        async with session.post(
            url,
            json={"delivery_id": delivery_id},
            headers=headers,
            cookies=cookies,
        ) as resp:
            if resp.status >= 400:
                body = await resp.text()
                logger.warning("[Outbound] ack HTTP %s: %s", resp.status, body[:200])
    except Exception as exc:
        logger.warning("[Outbound] ack 失败 delivery=%s: %s", delivery_id, exc)


async def _handle_message(ws, data: dict, token: str, session) -> None:
    msg_type = data.get("type")
    if msg_type == "ping":
        await ws.send_json({"type": "pong"})
        return
    if msg_type != "deliver":
        return
    ok = await _handle_deliver(data)
    delivery_id = str(data.get("delivery_id") or "").strip()
    if ok and delivery_id:
        await _ack_delivery(session, token, delivery_id, ws=ws)


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
    print(f"[Outbound] 连接云端投递通道 {url}", flush=True)
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
            print("[Outbound] 投递通道已连接", flush=True)
            await ws.send_json({"type": "pull"})
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
                        await _handle_message(ws, data, token, session)
                elif msg.type in (
                    aiohttp.WSMsgType.CLOSED,
                    aiohttp.WSMsgType.ERROR,
                    aiohttp.WSMsgType.CLOSE,
                ):
                    logger.warning("[Outbound] 投递通道断开 type=%s", msg.type)
                    return


def _auth_headers(token: str) -> tuple[dict, dict]:
    headers = {
        "Authorization": f"Bearer {token}",
        "User-Agent": "SoulproutGateway/1.0",
    }
    cookies = {"token": token}
    return headers, cookies


async def _http_pull_once(token: str, *, log_status: bool = False) -> None:
    import aiohttp
    from gateway.chat_caller import _make_http_timeout, _make_ssl_connector
    from gateway.config_store import api_path, get_agent_url

    headers, cookies = _auth_headers(token)
    connector = _make_ssl_connector()
    async with aiohttp.ClientSession(
        timeout=_make_http_timeout(),
        connector=connector,
        trust_env=True,
    ) as session:
        if log_status:
            status_url = api_path(get_agent_url(), "/gateway/outbound/status")
            try:
                async with session.get(status_url, headers=headers, cookies=cookies) as resp:
                    if resp.status == 200:
                        info = await resp.json(content_type=None)
                        print(
                            "[Outbound] 云端状态 "
                            f"scheduler_tick={info.get('scheduler_last_tick')} "
                            f"ws_online={info.get('gateway_ws_online')} "
                            f"pending={info.get('pending_count')}",
                            flush=True,
                        )
                    else:
                        print(f"[Outbound] 云端状态 HTTP {resp.status}", flush=True)
            except Exception as exc:
                print(f"[Outbound] 读取云端状态失败: {exc}", flush=True)

        url = api_path(get_agent_url(), "/gateway/outbound/pending")
        async with session.get(url, headers=headers, cookies=cookies) as resp:
            if resp.status == 404:
                global _warned_pending_404
                if not _warned_pending_404:
                    _warned_pending_404 = True
                    logger.warning("[Outbound] HTTP 拉取 404，云端可能尚未部署 /gateway/outbound/pending")
                    print("[Outbound] HTTP 拉取 404：云端还没有投递接口，请把本地未提交的改动提交后再 git pull", flush=True)
                return
            if resp.status == 401:
                logger.warning("[Outbound] HTTP 拉取 401，请重新登录")
                return
            if resp.status >= 400:
                body = await resp.text()
                logger.warning("[Outbound] HTTP 拉取失败 HTTP %s: %s", resp.status, body[:200])
                return
            payload = await resp.json(content_type=None)
        deliveries = payload.get("deliveries") if isinstance(payload, dict) else None
        if not isinstance(deliveries, list) or not deliveries:
            return
        print(f"[Outbound] HTTP 拉到 {len(deliveries)} 条待投递", flush=True)
        for item in deliveries:
            if not isinstance(item, dict):
                continue
            ok = await _handle_deliver(item)
            delivery_id = str(item.get("delivery_id") or "").strip()
            if ok and delivery_id:
                await _ack_delivery(session, token, delivery_id)


async def _ws_loop(stop_event: asyncio.Event) -> None:
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
            print(f"[Outbound] 投递通道异常: {exc}", flush=True)
            delay = min(delay * 1.5, 30)
        if stop_event.is_set():
            break
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=delay)
        except asyncio.TimeoutError:
            pass


async def _http_pull_loop(stop_event: asyncio.Event) -> None:
    print("[Outbound] HTTP 拉取已启动", flush=True)
    first = True
    while not stop_event.is_set():
        from gateway.config_store import get_agent_token

        token = (get_agent_token() or "").strip()
        if token:
            try:
                await _http_pull_once(token, log_status=first)
                first = False
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("[Outbound] HTTP 拉取异常: %s", exc)
                print(f"[Outbound] HTTP 拉取异常: {exc}", flush=True)
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=_HTTP_PULL_INTERVAL_S)
        except asyncio.TimeoutError:
            pass


async def run_outbound_loop(stop_event: asyncio.Event) -> None:
    """登录后维持与 Agent 的投递通道：WebSocket 推送 + HTTP 定时拉取。"""
    await asyncio.gather(
        _ws_loop(stop_event),
        _http_pull_loop(stop_event),
    )

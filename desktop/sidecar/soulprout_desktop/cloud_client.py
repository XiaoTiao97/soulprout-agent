"""桌面端到云端 ``/desktop/ws`` 的长连接。

连上后先发 ``hello``（设备 ID / 名称 / 系统信息 / 渠道状态），之后：

- 每 25 秒发一次 ``ping``（顺带上报渠道连接状态），云端据此判断「电脑在线」；
- 收到 ``tool_call`` 就交给 ``LocalToolRunner`` 执行，把结果以 ``tool_result`` 发回；
- 收到 ``cancel`` 就取消对应的执行（比如用户在网页上点了「停止」，正在跑的 bash 会被杀掉）。

断线自动重连（指数退避）；没有登录凭证时安静等待，登录后由 ``poke()`` 立即触发连接。
协议帧定义见云端 ``agent/api/routers/desktop_ws.py``。
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Awaitable, Callable, Dict, Optional
from urllib.parse import quote

import aiohttp

from . import device

logger = logging.getLogger(__name__)

HEARTBEAT_INTERVAL_S = 25.0
RECONNECT_MIN_S = 2.0
RECONNECT_MAX_S = 30.0
AUTH_RETRY_S = 30.0

ChannelsProvider = Callable[[], Dict[str, bool]]
Executor = Callable[..., Awaitable[Any]]
TokenProvider = Callable[[], str]
UrlProvider = Callable[[], str]


class CloudClient:
    def __init__(
        self,
        *,
        executor: Executor,
        get_token: TokenProvider,
        get_agent_url: UrlProvider,
        get_channels: ChannelsProvider,
        on_cancel: Optional[Callable[[str], None]] = None,
        ws_url_builder: Optional[Callable[[str], list]] = None,
        ssl_connector_factory: Optional[Callable[[], Any]] = None,
    ):
        self._executor = executor
        self._get_token = get_token
        self._get_agent_url = get_agent_url
        self._get_channels = get_channels
        self._on_cancel = on_cancel
        self._ws_url_builder = ws_url_builder or _default_ws_urls
        self._ssl_connector_factory = ssl_connector_factory
        self._wake = asyncio.Event()
        self._ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self._send_lock = asyncio.Lock()
        self._tasks: Dict[str, asyncio.Task] = {}
        self.connected = False
        self.state = "idle"  # idle | no_login | connecting | online | auth_failed | offline
        self.last_error = ""

    # ------------------------------------------------------------------ 外部控制

    def poke(self) -> None:
        """登录态变化后立即重新连接（或让等待中的循环马上醒来）。"""
        self._wake.set()

    async def disconnect(self) -> None:
        ws = self._ws
        if ws is not None and not ws.closed:
            await ws.close()

    # ------------------------------------------------------------------ 主循环

    async def run(self, stop_event: asyncio.Event) -> None:
        delay = RECONNECT_MIN_S
        url_index = 0
        while not stop_event.is_set():
            token = (self._get_token() or "").strip()
            if not token:
                self.state = "no_login"
                await self._sleep(stop_event, AUTH_RETRY_S)
                continue
            urls = self._ws_url_builder(self._get_agent_url())
            url = urls[url_index % len(urls)]
            # 已经在线时短暂重连不要把状态打成 connecting/offline，设置页否则会闪断
            if self.state != "online":
                self.state = "connecting"
            reached_ready = False
            try:
                reached_ready = await self._session(token, url, stop_event)
                if reached_ready:
                    delay = RECONNECT_MIN_S
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.last_error = str(exc)
                logger.warning("[Desktop] 云端连接异常 %s: %s", url, exc)
                if "404" in str(exc) and len(urls) > 1:
                    url_index += 1
            finally:
                self.connected = False
                self._ws = None
                await self._cancel_running()
            if stop_event.is_set():
                break
            if self.state == "auth_failed":
                await self._sleep(stop_event, AUTH_RETRY_S)
            else:
                if not reached_ready:
                    self.state = "offline"
                await self._sleep(stop_event, delay)
                delay = min(delay * 1.6, RECONNECT_MAX_S)

    async def _sleep(self, stop_event: asyncio.Event, seconds: float) -> None:
        self._wake.clear()
        waiters = [asyncio.ensure_future(stop_event.wait()), asyncio.ensure_future(self._wake.wait())]
        try:
            await asyncio.wait(waiters, timeout=seconds, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for w in waiters:
                w.cancel()

    # ------------------------------------------------------------------ 一次连接

    async def _session(self, token: str, url: str, stop_event: asyncio.Event) -> bool:
        timeout = aiohttp.ClientTimeout(total=None, sock_connect=30, sock_read=None)
        connector = self._ssl_connector_factory() if self._ssl_connector_factory else None
        reached_ready = False
        async with aiohttp.ClientSession(timeout=timeout, connector=connector, trust_env=True) as session:
            async with session.ws_connect(
                f"{url}?token={quote(token)}",
                headers={"Authorization": f"Bearer {token}"},
                heartbeat=None,
                receive_timeout=None,
                max_msg_size=32 * 1024 * 1024,
            ) as ws:
                self._ws = ws
                await self._send(ws, device.hello_frame(self._safe_channels()))
                heartbeat = asyncio.create_task(self._heartbeat(ws), name="desktop-heartbeat")
                try:
                    async for msg in ws:
                        if stop_event.is_set():
                            await ws.close()
                            break
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            data = _parse(msg.data)
                            if data is None:
                                continue
                            kind = data.get("type")
                            if kind == "ready":
                                reached_ready = True
                                self.connected = True
                                self.state = "online"
                                self.last_error = ""
                                logger.info("[Desktop] 已连接云端，设备在线")
                            elif kind == "tool_call":
                                self._start_call(ws, data)
                            elif kind == "cancel":
                                self._cancel_call(str(data.get("call_id") or ""))
                        elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.ERROR):
                            break
                finally:
                    heartbeat.cancel()
                    try:
                        await heartbeat
                    except (asyncio.CancelledError, Exception):
                        pass
                if not reached_ready and ws.close_code == 1008:
                    # 云端在握手后立刻以 1008 关闭：凭证无效/过期，别再高频重试
                    self.state = "auth_failed"
                    self.last_error = "登录已失效，请重新登录"
        return reached_ready

    def _safe_channels(self) -> Dict[str, bool]:
        try:
            return dict(self._get_channels() or {})
        except Exception:
            return {}

    async def _send(self, ws: aiohttp.ClientWebSocketResponse, frame: Dict[str, Any]) -> None:
        async with self._send_lock:
            await ws.send_str(json.dumps(frame, ensure_ascii=False))

    async def _heartbeat(self, ws: aiohttp.ClientWebSocketResponse) -> None:
        while not ws.closed:
            await asyncio.sleep(HEARTBEAT_INTERVAL_S)
            await self._send(ws, {"type": "ping", "channels": self._safe_channels()})

    async def push_channels(self) -> None:
        """渠道连接状态变化时马上上报，不等下一次心跳。"""
        ws = self._ws
        if ws is not None and not ws.closed and self.connected:
            try:
                await self._send(ws, {"type": "channels", "channels": self._safe_channels()})
            except Exception:
                pass

    # ------------------------------------------------------------------ 工具调用

    def _start_call(self, ws: aiohttp.ClientWebSocketResponse, data: Dict[str, Any]) -> None:
        call_id = str(data.get("call_id") or "")
        if not call_id:
            return
        task = asyncio.create_task(self._handle_call(ws, call_id, data), name=f"desktop-call-{call_id[:8]}")
        self._tasks[call_id] = task
        task.add_done_callback(lambda _t, cid=call_id: self._tasks.pop(cid, None))

    async def _handle_call(self, ws: aiohttp.ClientWebSocketResponse, call_id: str, data: Dict[str, Any]) -> None:
        tool = str(data.get("tool") or "")
        try:
            result = await self._executor(
                tool,
                data.get("arguments") or {},
                conversation_id=str(data.get("conversation_id") or ""),
                context=data.get("context") or {},
                call_id=call_id,
            )
            frame = {"type": "tool_result", "call_id": call_id, "ok": True, "result": result}
        except asyncio.CancelledError:
            raise  # 被云端取消：云端已经不再等这个结果，不用回帧
        except Exception as exc:
            logger.warning("[Desktop] 工具执行异常 tool=%s: %s", tool, exc, exc_info=True)
            frame = {"type": "tool_result", "call_id": call_id, "ok": False, "error": f"错误：本地工具执行失败：{exc}"}
        if not ws.closed:
            try:
                await self._send(ws, frame)
            except Exception as exc:
                logger.warning("[Desktop] 回传结果失败 call=%s: %s", call_id, exc)

    def _cancel_call(self, call_id: str) -> None:
        task = self._tasks.get(call_id)
        if task is not None and not task.done():
            task.cancel()
        if self._on_cancel is not None:
            self._on_cancel(call_id)

    async def _cancel_running(self) -> None:
        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()


def _parse(raw: str) -> Optional[Dict[str, Any]]:
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    return data if isinstance(data, dict) else None


def _default_ws_urls(agent_url: str) -> list:
    from gateway.config_store import ws_path

    primary = ws_path(agent_url, "/desktop/ws")
    urls = [primary]
    alt = primary.replace("/api/desktop/ws", "/desktop/ws")
    if alt != primary:
        urls.append(alt)
    return urls

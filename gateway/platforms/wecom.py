"""
企业微信（WeCom）AI Bot 平台适配器（WebSocket 长连接）。

实现参考：https://github.com/NousResearch/hermes-agent
（gateway/platforms/wecom.py — WebSocket 连接、扫码注册、消息收发核心流程）

本模块为轻量化移植，仅包含：
- WebSocket 连接 wss://openws.work.weixin.qq.com
- 扫码获取 Bot ID / Secret 或手动填写凭证
- 文本消息收发（群聊自动去掉 @ 前缀；回复优先走 aibot_respond_msg）
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
import uuid
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import quote
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

try:
    import aiohttp
    AIOHTTP_AVAILABLE = True
except ImportError:
    aiohttp = None  # type: ignore[assignment]
    AIOHTTP_AVAILABLE = False

from gateway.base import (
    BasePlatformAdapter,
    MessageEvent,
    MessageType,
    SendResult,
)

# ---------------------------------------------------------------------------
# 常量（参考 hermes-agent gateway/platforms/wecom.py）
# ---------------------------------------------------------------------------

DEFAULT_WS_URL = "wss://openws.work.weixin.qq.com"

APP_CMD_SUBSCRIBE = "aibot_subscribe"
APP_CMD_CALLBACK = "aibot_msg_callback"
APP_CMD_LEGACY_CALLBACK = "aibot_callback"
APP_CMD_SEND = "aibot_send_msg"
APP_CMD_RESPONSE = "aibot_respond_msg"
APP_CMD_PING = "ping"

CALLBACK_COMMANDS = {APP_CMD_CALLBACK, APP_CMD_LEGACY_CALLBACK}
NON_RESPONSE_COMMANDS = CALLBACK_COMMANDS | {"aibot_event_callback"}

CONNECT_TIMEOUT_SECONDS = 20.0
REQUEST_TIMEOUT_SECONDS = 15.0
HEARTBEAT_INTERVAL_SECONDS = 30.0
RECONNECT_BACKOFF = [2, 5, 10, 30, 60]
MAX_MESSAGE_LENGTH = 4000
_DEDUP_MAX = 1000

# 扫码（非公开 API，与 hermes-agent 相同来源）
_QR_GENERATE_URL = "https://work.weixin.qq.com/ai/qc/generate?source=soulprout"
_QR_QUERY_URL = "https://work.weixin.qq.com/ai/qc/query_result"
_QR_CODE_PAGE = "https://work.weixin.qq.com/ai/qc/gen?source=soulprout&scode="
_QR_POLL_INTERVAL = 3
_QR_POLL_TIMEOUT = 300
_QR_HTTP_TIMEOUT = 15

_GATEWAY_ROOT = Path(__file__).resolve().parent.parent.parent
WECOM_DATA_DIR = _GATEWAY_ROOT / "gateway_data" / "wecom"
WECOM_CONFIG_PATH = WECOM_DATA_DIR / "config.json"

_MENTION_PREFIX_RE = re.compile(r"^@\S+\s*")


def _json_write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _json_read(path: Path) -> Optional[dict]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def save_wecom_config(*, bot_id: str, secret: str, bot_name: str = "") -> None:
    _json_write(WECOM_CONFIG_PATH, {
        "bot_id": bot_id,
        "secret": secret,
        "bot_name": bot_name,
        "saved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    })
    try:
        WECOM_CONFIG_PATH.chmod(0o600)
    except OSError:
        pass


def load_wecom_config() -> Optional[Dict[str, Any]]:
    return _json_read(WECOM_CONFIG_PATH)


def has_wecom_config() -> bool:
    cfg = load_wecom_config()
    return bool(cfg and cfg.get("bot_id") and cfg.get("secret"))


class _MessageDedup:
    def __init__(self, max_size: int = _DEDUP_MAX):
        self._ids: "OrderedDict[str, float]" = OrderedDict()
        self._max_size = max_size

    def is_duplicate(self, message_id: str) -> bool:
        if not message_id:
            return False
        if message_id in self._ids:
            return True
        self._ids[message_id] = time.time()
        while len(self._ids) > self._max_size:
            self._ids.popitem(last=False)
        return False


def _http_get_json(url: str) -> dict:
    req = Request(url, headers={"User-Agent": "SoulproutGateway/1.0"})
    with urlopen(req, timeout=_QR_HTTP_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _fetch_qr_begin() -> dict:
    raw = _http_get_json(_QR_GENERATE_URL)
    data = raw.get("data") or {}
    scode = str(data.get("scode") or "").strip()
    auth_url = str(data.get("auth_url") or "").strip()
    if not scode or not auth_url:
        raise RuntimeError("企业微信 QR 接口返回格式异常")
    return {
        "scode": scode,
        "auth_url": auth_url,
        "page_url": f"{_QR_CODE_PAGE}{quote(scode)}",
        "qrcode_url": f"https://api.qrserver.com/v1/create-qr-code/?size=192x192&data={quote(auth_url)}",
    }


def _poll_qr_once(scode: str) -> dict:
    url = f"{_QR_QUERY_URL}?scode={quote(scode)}"
    return _http_get_json(url)


# ---------------------------------------------------------------------------
# 扫码 Session（供 web.py 调用）
# ---------------------------------------------------------------------------

class WecomQRSession:
    """企业微信扫码获取 Bot 凭证，接口风格对齐 FeishuQRSession。"""

    def __init__(self) -> None:
        self._scode = ""
        self._expire_at = 0.0
        self._closed = False

    async def start(self) -> Dict[str, Any]:
        try:
            begin = await asyncio.to_thread(_fetch_qr_begin)
        except Exception as exc:
            return {"error": str(exc)}
        self._scode = begin["scode"]
        self._expire_at = time.monotonic() + _QR_POLL_TIMEOUT
        return {
            "qr_url": begin["page_url"],
            "auth_url": begin["auth_url"],
            "qrcode_url": begin["qrcode_url"],
            "expire_in": _QR_POLL_TIMEOUT,
        }

    async def poll(self) -> Dict[str, Any]:
        if self._closed or not self._scode:
            return {"status": "not_started"}
        if time.monotonic() >= self._expire_at:
            return {"status": "error", "error": "二维码已过期，请重新获取"}

        try:
            result = await asyncio.to_thread(_poll_qr_once, self._scode)
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

        result_data = result.get("data") or {}
        status = str(result_data.get("status") or "").lower()
        if status == "success":
            bot_info = result_data.get("bot_info") or {}
            bot_id = str(bot_info.get("botid") or bot_info.get("bot_id") or "").strip()
            secret = str(bot_info.get("secret") or "").strip()
            if bot_id and secret:
                bot_name = str(bot_info.get("name") or bot_info.get("bot_name") or "").strip()
                save_wecom_config(bot_id=bot_id, secret=secret, bot_name=bot_name)
                return {
                    "status": "confirmed",
                    "bot_id": bot_id,
                    "bot_name": bot_name,
                }
            return {"status": "error", "error": "扫码成功但未返回 Bot 凭证"}

        return {"status": "wait"}

    async def close(self) -> None:
        self._closed = True


# ---------------------------------------------------------------------------
# 平台适配器
# ---------------------------------------------------------------------------

class WecomAdapter(BasePlatformAdapter):
    def __init__(self) -> None:
        super().__init__("wecom")
        self._bot_id = os.getenv("WECOM_BOT_ID", "").strip()
        self._secret = os.getenv("WECOM_SECRET", "").strip()
        self._ws_url = os.getenv("WECOM_WEBSOCKET_URL", DEFAULT_WS_URL).strip() or DEFAULT_WS_URL
        self._bot_name = ""

        self._session: Optional[aiohttp.ClientSession] = None
        self._ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self._listen_task: Optional[asyncio.Task] = None
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._pending_responses: Dict[str, asyncio.Future] = {}
        self._dedup = _MessageDedup()
        self._last_chat_req_ids: Dict[str, str] = {}
        self._device_id = uuid.uuid4().hex

        self._reload_from_disk()

    @property
    def is_connected(self) -> bool:
        return self._running and self._ws is not None and not self._ws.closed

    @property
    def bot_id(self) -> str:
        return self._bot_id

    @property
    def bot_name(self) -> str:
        return self._bot_name

    def _reload_from_disk(self) -> None:
        cfg = load_wecom_config()
        if not cfg:
            return
        self._bot_id = str(cfg.get("bot_id") or self._bot_id).strip()
        self._secret = str(cfg.get("secret") or self._secret).strip()
        self._bot_name = str(cfg.get("bot_name") or "").strip()

    def reload_credentials(self) -> bool:
        self._reload_from_disk()
        ok = bool(self._bot_id and self._secret)
        if ok:
            logger.info("[wecom] 凭证已重新加载 bot_id=%s", self._bot_id[:8] + "…")
        return ok

    async def connect(self) -> bool:
        if not AIOHTTP_AVAILABLE:
            logger.error("[wecom] aiohttp 未安装")
            return False
        if not self._bot_id or not self._secret:
            logger.warning("[wecom] 凭证未配置，可通过 Web UI 扫码或手动填写 Bot ID/Secret")
            return False

        try:
            await self._open_connection()
            self._running = True
            self._listen_task = asyncio.create_task(self._listen_loop(), name="wecom-listen")
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop(), name="wecom-heartbeat")
            logger.info("[wecom] WebSocket 已连接 bot_id=%s", self._bot_id[:8] + "…")
            return True
        except Exception as exc:
            logger.error("[wecom] 连接失败: %s", exc, exc_info=True)
            await self._cleanup_ws()
            return False

    async def disconnect(self) -> None:
        self._running = False
        for task in (self._listen_task, self._heartbeat_task):
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        self._listen_task = None
        self._heartbeat_task = None
        self._fail_pending_responses(RuntimeError("WeCom adapter disconnected"))
        await self._cleanup_ws()
        logger.info("[wecom] 已断开连接")

    async def _cleanup_ws(self) -> None:
        if self._ws and not self._ws.closed:
            await self._ws.close()
        self._ws = None
        if self._session and not self._session.closed:
            await self._session.close()
        self._session = None

    async def _open_connection(self) -> None:
        await self._cleanup_ws()
        self._session = aiohttp.ClientSession(trust_env=True)
        self._ws = await self._session.ws_connect(
            self._ws_url,
            heartbeat=HEARTBEAT_INTERVAL_SECONDS * 2,
            timeout=CONNECT_TIMEOUT_SECONDS,
        )
        req_id = self._new_req_id("subscribe")
        await self._send_json({
            "cmd": APP_CMD_SUBSCRIBE,
            "headers": {"req_id": req_id},
            "body": {
                "bot_id": self._bot_id,
                "secret": self._secret,
                "device_id": self._device_id,
            },
        })
        auth_payload = await self._wait_for_handshake(req_id)
        errcode = auth_payload.get("errcode", 0)
        if errcode not in {0, None}:
            errmsg = auth_payload.get("errmsg", "authentication failed")
            raise RuntimeError(f"{errmsg} (errcode={errcode})")

    async def _wait_for_handshake(self, req_id: str) -> Dict[str, Any]:
        if not self._ws:
            raise RuntimeError("WebSocket 未初始化")
        deadline = asyncio.get_running_loop().time() + CONNECT_TIMEOUT_SECONDS
        while True:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise TimeoutError("等待企业微信订阅确认超时")
            msg = await asyncio.wait_for(self._ws.receive(), timeout=remaining)
            if msg.type == aiohttp.WSMsgType.TEXT:
                payload = self._parse_json(msg.data)
                if not payload:
                    continue
                if payload.get("cmd") == APP_CMD_PING:
                    continue
                if self._payload_req_id(payload) == req_id:
                    return payload
            elif msg.type in {aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.ERROR}:
                raise RuntimeError("认证过程中 WebSocket 已关闭")

    async def _listen_loop(self) -> None:
        backoff_idx = 0
        while self._running:
            try:
                await self._read_events()
                backoff_idx = 0
            except asyncio.CancelledError:
                return
            except Exception as exc:
                if not self._running:
                    return
                logger.warning("[wecom] WebSocket 异常: %s", exc)
                self._fail_pending_responses(RuntimeError("WeCom connection interrupted"))
                delay = RECONNECT_BACKOFF[min(backoff_idx, len(RECONNECT_BACKOFF) - 1)]
                backoff_idx += 1
                await asyncio.sleep(delay)
                try:
                    await self._open_connection()
                    backoff_idx = 0
                    logger.info("[wecom] 已重新连接")
                except Exception as reconnect_exc:
                    logger.error("[wecom] 重连失败: %s", reconnect_exc)

    async def _read_events(self) -> None:
        if not self._ws:
            raise RuntimeError("WebSocket 未连接")
        async for msg in self._ws:
            if not self._running:
                break
            if msg.type == aiohttp.WSMsgType.TEXT:
                payload = self._parse_json(msg.data)
                if payload:
                    await self._dispatch_payload(payload)
            elif msg.type in {aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.ERROR}:
                raise RuntimeError("WebSocket 已关闭")

    async def _heartbeat_loop(self) -> None:
        while self._running:
            try:
                await asyncio.sleep(HEARTBEAT_INTERVAL_SECONDS)
                if self._ws and not self._ws.closed:
                    await self._send_json({"cmd": APP_CMD_PING})
            except asyncio.CancelledError:
                return
            except Exception as exc:
                logger.debug("[wecom] heartbeat 失败: %s", exc)

    async def _dispatch_payload(self, payload: Dict[str, Any]) -> None:
        req_id = self._payload_req_id(payload)
        cmd = str(payload.get("cmd") or "")

        if req_id and req_id in self._pending_responses and cmd not in NON_RESPONSE_COMMANDS:
            future = self._pending_responses.get(req_id)
            if future and not future.done():
                future.set_result(payload)
            return

        if cmd in CALLBACK_COMMANDS:
            await self._on_message(payload)

    async def _on_message(self, payload: Dict[str, Any]) -> None:
        body = payload.get("body")
        if not isinstance(body, dict):
            return

        msg_id = str(body.get("msgid") or self._payload_req_id(payload) or uuid.uuid4().hex)
        if self._dedup.is_duplicate(msg_id):
            return

        sender = body.get("from") if isinstance(body.get("from"), dict) else {}
        sender_id = str(sender.get("userid") or "").strip()
        chat_id = str(body.get("chatid") or sender_id).strip()
        if not chat_id:
            return

        req_id = self._payload_req_id(payload)
        if req_id:
            self._last_chat_req_ids[chat_id] = req_id
            while len(self._last_chat_req_ids) > _DEDUP_MAX:
                self._last_chat_req_ids.pop(next(iter(self._last_chat_req_ids)))

        text = _extract_text(body)
        is_group = str(body.get("chattype") or "").lower() == "group"
        if is_group and text:
            text = _MENTION_PREFIX_RE.sub("", text).strip()

        if not text:
            return

        source = self.build_source(
            chat_id=chat_id,
            chat_type="group" if is_group else "dm",
            user_id=sender_id or None,
            user_name=sender_id or None,
        )
        await self.handle_message(MessageEvent(
            text=text,
            message_type=MessageType.TEXT,
            source=source,
            raw_message=payload,
            message_id=msg_id,
            timestamp=datetime.now(),
        ))

    async def send(
        self,
        chat_id: str,
        content: str,
        reply_to: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SendResult:
        if not self._ws or self._ws.closed:
            return SendResult(success=False, error="未连接")
        if not chat_id:
            return SendResult(success=False, error="chat_id 为空")

        text = (content or "").strip()
        if not text:
            return SendResult(success=False, error="消息内容为空")
        if len(text) > MAX_MESSAGE_LENGTH:
            text = text[:MAX_MESSAGE_LENGTH]

        body = {
            "msgtype": "markdown",
            "markdown": {"content": text},
        }

        try:
            reply_req_id = self._last_chat_req_ids.get(chat_id)
            if reply_req_id:
                response = await self._send_reply_request(reply_req_id, body)
            else:
                response = await self._send_request(
                    APP_CMD_SEND,
                    {"chatid": chat_id, **body},
                )
        except asyncio.TimeoutError:
            return SendResult(success=False, error="发送超时")
        except Exception as exc:
            logger.error("[wecom] 发送失败: %s", exc, exc_info=True)
            return SendResult(success=False, error=str(exc))

        error = _response_error(response)
        if error:
            return SendResult(success=False, error=error, raw_response=response)
        return SendResult(
            success=True,
            message_id=self._payload_req_id(response) or msg_id_fallback(),
            raw_response=response,
        )

    async def get_chat_info(self, chat_id: str) -> Dict[str, Any]:
        return {"id": chat_id, "name": chat_id, "type": "unknown"}

    async def _send_json(self, payload: Dict[str, Any]) -> None:
        if not self._ws or self._ws.closed:
            raise RuntimeError("WebSocket 未连接")
        await self._ws.send_json(payload)

    async def _send_request(
        self,
        cmd: str,
        body: Dict[str, Any],
        timeout: float = REQUEST_TIMEOUT_SECONDS,
    ) -> Dict[str, Any]:
        if not self._ws or self._ws.closed:
            raise RuntimeError("WebSocket 未连接")
        req_id = self._new_req_id(cmd)
        future = asyncio.get_running_loop().create_future()
        self._pending_responses[req_id] = future
        try:
            await self._send_json({"cmd": cmd, "headers": {"req_id": req_id}, "body": body})
            return await asyncio.wait_for(future, timeout=timeout)
        finally:
            self._pending_responses.pop(req_id, None)

    async def _send_reply_request(
        self,
        reply_req_id: str,
        body: Dict[str, Any],
        timeout: float = REQUEST_TIMEOUT_SECONDS,
    ) -> Dict[str, Any]:
        if not self._ws or self._ws.closed:
            raise RuntimeError("WebSocket 未连接")
        future = asyncio.get_running_loop().create_future()
        self._pending_responses[reply_req_id] = future
        try:
            await self._send_json({
                "cmd": APP_CMD_RESPONSE,
                "headers": {"req_id": reply_req_id},
                "body": body,
            })
            return await asyncio.wait_for(future, timeout=timeout)
        finally:
            self._pending_responses.pop(reply_req_id, None)

    def _fail_pending_responses(self, exc: Exception) -> None:
        for req_id, future in list(self._pending_responses.items()):
            if not future.done():
                future.set_exception(exc)
            self._pending_responses.pop(req_id, None)

    @staticmethod
    def _new_req_id(prefix: str) -> str:
        return f"{prefix}-{uuid.uuid4().hex}"

    @staticmethod
    def _payload_req_id(payload: Dict[str, Any]) -> str:
        headers = payload.get("headers")
        if isinstance(headers, dict):
            return str(headers.get("req_id") or "")
        return ""

    @staticmethod
    def _parse_json(raw: Any) -> Optional[Dict[str, Any]]:
        try:
            payload = json.loads(raw)
        except Exception:
            return None
        return payload if isinstance(payload, dict) else None


def _extract_text(body: Dict[str, Any]) -> str:
    msgtype = str(body.get("msgtype") or "").lower()
    if msgtype == "text":
        text_block = body.get("text") if isinstance(body.get("text"), dict) else {}
        return str(text_block.get("content") or "").strip()
    if msgtype == "voice":
        voice_block = body.get("voice") if isinstance(body.get("voice"), dict) else {}
        return str(voice_block.get("content") or "").strip()
    if msgtype == "mixed":
        mixed = body.get("mixed") if isinstance(body.get("mixed"), dict) else {}
        parts = []
        for item in mixed.get("msg_item") or []:
            if not isinstance(item, dict):
                continue
            if str(item.get("msgtype") or "").lower() != "text":
                continue
            text_block = item.get("text") if isinstance(item.get("text"), dict) else {}
            content = str(text_block.get("content") or "").strip()
            if content:
                parts.append(content)
        return "\n".join(parts).strip()
    return ""


def _response_error(response: Dict[str, Any]) -> Optional[str]:
    errcode = response.get("errcode", 0)
    if errcode in {0, None}:
        return None
    errmsg = str(response.get("errmsg") or "unknown error")
    return f"WeCom errcode {errcode}: {errmsg}"


def msg_id_fallback() -> str:
    return uuid.uuid4().hex[:12]

"""
飞书 / Lark 平台适配器（WebSocket 长连接）。

实现参考：https://github.com/NousResearch/hermes-agent
（gateway/platforms/feishu.py — WebSocket 连接、扫码注册、消息收发核心流程）

本模块为轻量化移植，仅包含：
- WebSocket 模式收消息（im.message.receive_v1）
- 扫码创建 Bot / 手动 App ID + Secret
- 文本消息收发（私聊全收；群聊需 @ 机器人）
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

try:
    import lark_oapi as lark
    from lark_oapi.api.im.v1 import (
        CreateMessageRequest,
        CreateMessageRequestBody,
        P2ImMessageReceiveV1,
    )
    from lark_oapi.core.const import FEISHU_DOMAIN, LARK_DOMAIN
    from lark_oapi.event.dispatcher_handler import EventDispatcherHandler
    from lark_oapi.ws import Client as FeishuWSClient

    LARK_AVAILABLE = True
except ImportError:
    lark = None  # type: ignore[assignment]
    CreateMessageRequest = None  # type: ignore[assignment]
    CreateMessageRequestBody = None  # type: ignore[assignment]
    P2ImMessageReceiveV1 = None  # type: ignore[assignment]
    FEISHU_DOMAIN = None  # type: ignore[assignment]
    LARK_DOMAIN = None  # type: ignore[assignment]
    EventDispatcherHandler = None  # type: ignore[assignment]
    FeishuWSClient = None  # type: ignore[assignment]
    LARK_AVAILABLE = False

from gateway.base import (
    BasePlatformAdapter,
    MessageEvent,
    MessageType,
    SendResult,
)

# ---------------------------------------------------------------------------
# 数据目录
# ---------------------------------------------------------------------------

_GATEWAY_ROOT = (
    Path(sys.executable).parent
    if getattr(sys, "frozen", False)
    else Path(__file__).resolve().parent.parent.parent
)
FEISHU_DATA_DIR = _GATEWAY_ROOT / "gateway_data" / "feishu"
FEISHU_CONFIG_PATH = FEISHU_DATA_DIR / "config.json"

# 扫码注册（参考 hermes-agent feishu.py QR onboarding）
_ONBOARD_ACCOUNTS_URLS = {
    "feishu": "https://accounts.feishu.cn",
    "lark": "https://accounts.larksuite.com",
}
_REGISTRATION_PATH = "/oauth/v1/app/registration"
_ONBOARD_TIMEOUT_S = 10

_DEDUP_MAX = 2048


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


def save_feishu_config(
    *,
    app_id: str,
    app_secret: str,
    domain: str = "feishu",
    bot_name: str = "",
    bot_open_id: str = "",
    open_id: str = "",
) -> None:
    """持久化飞书 Bot 凭证。"""
    _json_write(FEISHU_CONFIG_PATH, {
        "app_id": app_id,
        "app_secret": app_secret,
        "domain": domain,
        "bot_name": bot_name,
        "bot_open_id": bot_open_id,
        "open_id": open_id,
        "saved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    })
    try:
        FEISHU_CONFIG_PATH.chmod(0o600)
    except OSError:
        pass


def load_feishu_config() -> Optional[Dict[str, Any]]:
    return _json_read(FEISHU_CONFIG_PATH)


def has_feishu_config() -> bool:
    cfg = load_feishu_config()
    return bool(cfg and cfg.get("app_id") and cfg.get("app_secret"))


# ---------------------------------------------------------------------------
# 扫码注册 HTTP（同步，供 QR Session 在线程中调用）
# ---------------------------------------------------------------------------

def _accounts_base_url(domain: str) -> str:
    return _ONBOARD_ACCOUNTS_URLS.get(domain, _ONBOARD_ACCOUNTS_URLS["feishu"])


def _post_registration(base_url: str, body: Dict[str, str]) -> dict:
    url = f"{base_url}{_REGISTRATION_PATH}"
    data = urlencode(body).encode("utf-8")
    req = Request(url, data=data, headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urlopen(req, timeout=_ONBOARD_TIMEOUT_S) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except HTTPError as exc:
        raw = exc.read()
        if raw:
            try:
                return json.loads(raw.decode("utf-8"))
            except (ValueError, json.JSONDecodeError):
                pass
        raise


def _init_registration(domain: str) -> None:
    res = _post_registration(_accounts_base_url(domain), {"action": "init"})
    methods = res.get("supported_auth_methods") or []
    if "client_secret" not in methods:
        raise RuntimeError(f"飞书注册环境不支持 client_secret，支持：{methods}")


def _begin_registration(domain: str) -> dict:
    res = _post_registration(_accounts_base_url(domain), {
        "action": "begin",
        "archetype": "PersonalAgent",
        "auth_method": "client_secret",
        "request_user_info": "open_id",
    })
    device_code = res.get("device_code")
    if not device_code:
        raise RuntimeError("飞书注册未返回 device_code")
    qr_url = res.get("verification_uri_complete", "")
    if qr_url:
        sep = "&" if "?" in qr_url else "?"
        qr_url = f"{qr_url}{sep}from=soulprout&tp=soulprout"
    return {
        "device_code": device_code,
        "qr_url": qr_url,
        "interval": int(res.get("interval") or 5),
        "expire_in": int(res.get("expire_in") or 600),
    }


def _poll_registration_once(*, device_code: str, domain: str) -> dict:
    return _post_registration(_accounts_base_url(domain), {
        "action": "poll",
        "device_code": device_code,
        "tp": "ob_app",
    })


def probe_bot(app_id: str, app_secret: str, domain: str) -> Optional[dict]:
    """验证凭证并获取 Bot 信息。"""
    open_base = "https://open.feishu.cn" if domain != "lark" else "https://open.larksuite.com"
    try:
        token_req = Request(
            f"{open_base}/open-apis/auth/v3/tenant_access_token/internal",
            data=json.dumps({"app_id": app_id, "app_secret": app_secret}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(token_req, timeout=_ONBOARD_TIMEOUT_S) as resp:
            token_res = json.loads(resp.read().decode("utf-8"))
        access_token = token_res.get("tenant_access_token")
        if not access_token:
            return None

        bot_req = Request(
            f"{open_base}/open-apis/bot/v3/info",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        with urlopen(bot_req, timeout=_ONBOARD_TIMEOUT_S) as resp:
            bot_res = json.loads(resp.read().decode("utf-8"))
        bot = (bot_res.get("bot") or {}) if bot_res.get("code") == 0 else {}
        return {
            "bot_name": bot.get("app_name") or bot.get("bot_name") or "",
            "bot_open_id": bot.get("open_id") or "",
        }
    except (URLError, OSError, json.JSONDecodeError, HTTPError) as exc:
        logger.warning("[feishu] probe_bot 失败: %s", exc)
        return None


# ---------------------------------------------------------------------------
# 消息去重
# ---------------------------------------------------------------------------

class _MessageDedup:
    def __init__(self, max_size: int = _DEDUP_MAX):
        self._ids: "OrderedDict[str, float]" = OrderedDict()
        self._max_size = max_size

    def is_duplicate(self, message_id: str) -> bool:
        if not message_id:
            return False
        now = time.time()
        if message_id in self._ids:
            return True
        self._ids[message_id] = now
        while len(self._ids) > self._max_size:
            self._ids.popitem(last=False)
        return False


def _extract_text(message: Any) -> str:
    content = str(getattr(message, "content", "") or "")
    msg_type = str(getattr(message, "message_type", "") or "")
    if not content:
        return ""
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return content.strip()
    if msg_type == "text":
        return str(data.get("text") or "").strip()
    return ""


def _is_bot_mentioned(message: Any, bot_open_id: str) -> bool:
    if not bot_open_id:
        return True
    for mention in getattr(message, "mentions", None) or []:
        ref = getattr(mention, "id", None)
        open_id = getattr(ref, "open_id", None) if ref else None
        if open_id and str(open_id) == bot_open_id:
            return True
    return False


def _run_ws_client(ws_client: Any, adapter: "FeishuAdapter") -> None:
    """在独立线程中运行官方 Lark WebSocket 客户端。"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    adapter._ws_thread_loop = loop
    try:
        import lark_oapi.ws.client as ws_client_module
        ws_client_module.loop = loop
    except Exception:
        pass
    try:
        ws_client.start()
    except Exception as exc:
        logger.error("[feishu] WebSocket 客户端异常退出: %s", exc, exc_info=True)
    finally:
        adapter._ws_thread_loop = None


# ---------------------------------------------------------------------------
# 扫码 Session（供 web.py 调用）
# ---------------------------------------------------------------------------

class FeishuQRSession:
    """飞书扫码创建 Bot 的会话，接口风格对齐 Weixin QRLoginSession。"""

    def __init__(self, domain: str = "feishu"):
        self._domain = domain
        self._device_code = ""
        self._interval = 5
        self._expire_at = 0.0
        self._qr_url = ""
        self._closed = False

    async def start(self) -> Dict[str, Any]:
        try:
            await asyncio.to_thread(_init_registration, self._domain)
            begin = await asyncio.to_thread(_begin_registration, self._domain)
        except Exception as exc:
            return {"error": str(exc)}

        self._device_code = begin["device_code"]
        self._interval = begin["interval"]
        self._expire_at = time.monotonic() + begin["expire_in"]
        self._qr_url = begin["qr_url"]
        qrcode_url = (
            f"https://api.qrserver.com/v1/create-qr-code/?size=192x192&data={quote(self._qr_url)}"
            if self._qr_url
            else ""
        )
        return {
            "qr_url": self._qr_url,
            "qrcode_url": qrcode_url,
            "expire_in": begin["expire_in"],
        }

    async def poll(self) -> Dict[str, Any]:
        if self._closed or not self._device_code:
            return {"status": "not_started"}
        if time.monotonic() >= self._expire_at:
            return {"status": "error", "error": "二维码已过期，请重新获取"}

        current_domain = self._domain
        try:
            res = await asyncio.to_thread(
                _poll_registration_once,
                device_code=self._device_code,
                domain=current_domain,
            )
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

        user_info = res.get("user_info") or {}
        if user_info.get("tenant_brand") == "lark":
            current_domain = "lark"
            self._domain = "lark"

        if res.get("client_id") and res.get("client_secret"):
            app_id = res["client_id"]
            app_secret = res["client_secret"]
            bot_info = await asyncio.to_thread(probe_bot, app_id, app_secret, current_domain) or {}
            save_feishu_config(
                app_id=app_id,
                app_secret=app_secret,
                domain=current_domain,
                bot_name=str(bot_info.get("bot_name") or ""),
                bot_open_id=str(bot_info.get("bot_open_id") or ""),
                open_id=str(user_info.get("open_id") or ""),
            )
            return {
                "status": "confirmed",
                "app_id": app_id,
                "domain": current_domain,
                "bot_name": bot_info.get("bot_name") or "",
            }

        error = res.get("error", "")
        if error in {"access_denied", "expired_token"}:
            return {"status": "error", "error": error}

        return {"status": "wait"}

    async def close(self) -> None:
        self._closed = True


# ---------------------------------------------------------------------------
# 平台适配器
# ---------------------------------------------------------------------------

class FeishuAdapter(BasePlatformAdapter):
    MAX_MESSAGE_LENGTH = 4000

    def __init__(self) -> None:
        super().__init__("feishu")
        self._app_id = os.getenv("FEISHU_APP_ID", "").strip()
        self._app_secret = os.getenv("FEISHU_APP_SECRET", "").strip()
        self._domain_name = os.getenv("FEISHU_DOMAIN", "feishu").strip() or "feishu"
        self._bot_name = ""
        self._bot_open_id = os.getenv("FEISHU_BOT_OPEN_ID", "").strip()

        self._client: Any = None
        self._event_handler: Any = None
        self._ws_client: Any = None
        self._ws_future: Optional[asyncio.Future] = None
        self._ws_thread_loop: Any = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

        self._dedup = _MessageDedup()
        self._reload_from_disk()

    @property
    def is_connected(self) -> bool:
        return self._running and self._ws_client is not None

    @property
    def bot_name(self) -> str:
        return self._bot_name

    @property
    def app_id(self) -> str:
        return self._app_id

    def _reload_from_disk(self) -> None:
        cfg = load_feishu_config()
        if not cfg:
            return
        self._app_id = str(cfg.get("app_id") or self._app_id).strip()
        self._app_secret = str(cfg.get("app_secret") or self._app_secret).strip()
        self._domain_name = str(cfg.get("domain") or self._domain_name).strip() or "feishu"
        self._bot_name = str(cfg.get("bot_name") or "").strip()
        self._bot_open_id = str(cfg.get("bot_open_id") or self._bot_open_id).strip()

    def reload_credentials(self) -> bool:
        self._reload_from_disk()
        ok = bool(self._app_id and self._app_secret)
        if ok:
            logger.info("[feishu] 凭证已重新加载 app_id=%s", self._app_id[:8] + "…")
        return ok

    async def connect(self) -> bool:
        if not LARK_AVAILABLE:
            logger.error("[feishu] lark-oapi 未安装，请执行: pip install lark-oapi websockets")
            return False
        if not self._app_id or not self._app_secret:
            logger.warning("[feishu] 凭证未配置，可通过 Web UI 扫码或手动填写 App ID/Secret")
            return False

        self._loop = asyncio.get_running_loop()
        domain = LARK_DOMAIN if self._domain_name == "lark" else FEISHU_DOMAIN

        self._client = (
            lark.Client.builder()
            .app_id(self._app_id)
            .app_secret(self._app_secret)
            .domain(domain)
            .log_level(lark.LogLevel.WARNING)
            .build()
        )
        self._event_handler = (
            EventDispatcherHandler.builder("", "")
            .register_p2_im_message_receive_v1(self._on_message_event)
            .build()
        )
        await self._hydrate_bot_identity()

        self._ws_client = FeishuWSClient(
            app_id=self._app_id,
            app_secret=self._app_secret,
            log_level=lark.LogLevel.INFO,
            event_handler=self._event_handler,
            domain=domain,
        )
        self._running = True
        self._ws_future = self._loop.run_in_executor(
            None, _run_ws_client, self._ws_client, self,
        )
        logger.info("[feishu] WebSocket 已启动 domain=%s app_id=%s", self._domain_name, self._app_id[:8] + "…")
        return True

    async def disconnect(self) -> None:
        self._running = False
        if self._ws_client is not None:
            try:
                setattr(self._ws_client, "_auto_reconnect", False)
            except Exception:
                pass
        ws_future = self._ws_future
        if ws_future is not None:
            try:
                await asyncio.wait_for(asyncio.shield(ws_future), timeout=10.0)
            except (asyncio.TimeoutError, asyncio.CancelledError, Exception):
                pass
        self._ws_future = None
        self._ws_client = None
        self._client = None
        self._event_handler = None
        self._loop = None
        logger.info("[feishu] 已断开连接")

    async def _hydrate_bot_identity(self) -> None:
        if self._bot_open_id and self._bot_name:
            return
        info = await asyncio.to_thread(probe_bot, self._app_id, self._app_secret, self._domain_name)
        if not info:
            return
        if not self._bot_name:
            self._bot_name = str(info.get("bot_name") or "")
        if not self._bot_open_id:
            self._bot_open_id = str(info.get("bot_open_id") or "")

    def _on_message_event(self, data: P2ImMessageReceiveV1) -> None:
        loop = self._loop
        if loop is None or loop.is_closed() or not self._running:
            return
        asyncio.run_coroutine_threadsafe(self._handle_message_event(data), loop)

    async def _handle_message_event(self, data: P2ImMessageReceiveV1) -> None:
        try:
            event = getattr(data, "event", None)
            message = getattr(event, "message", None)
            sender = getattr(event, "sender", None)
            if not message or not sender:
                return

            message_id = str(getattr(message, "message_id", "") or "")
            if self._dedup.is_duplicate(message_id):
                return

            chat_type = str(getattr(message, "chat_type", "p2p") or "p2p")
            if chat_type == "group" and not _is_bot_mentioned(message, self._bot_open_id):
                return

            text = _extract_text(message)
            if not text:
                return

            chat_id = str(getattr(message, "chat_id", "") or "")
            sender_id_obj = getattr(sender, "sender_id", None)
            user_id = (
                getattr(sender_id_obj, "open_id", None)
                or getattr(sender_id_obj, "user_id", None)
                or getattr(sender_id_obj, "union_id", None)
                or ""
            )
            user_id = str(user_id)

            source = self.build_source(
                chat_id=chat_id,
                chat_type="group" if chat_type == "group" else "dm",
                user_id=user_id,
                user_name=user_id,
            )
            await self.handle_message(MessageEvent(
                text=text,
                message_type=MessageType.TEXT,
                source=source,
                message_id=message_id or None,
                raw_message=data,
                timestamp=datetime.now(),
            ))
        except Exception as exc:
            logger.error("[feishu] 处理消息异常: %s", exc, exc_info=True)

    async def send(
        self,
        chat_id: str,
        content: str,
        reply_to: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SendResult:
        if not self._client:
            return SendResult(success=False, error="未连接")

        text = (content or "").strip()
        if not text:
            return SendResult(success=False, error="消息内容为空")
        if len(text) > self.MAX_MESSAGE_LENGTH:
            text = text[: self.MAX_MESSAGE_LENGTH]

        payload = json.dumps({"text": text}, ensure_ascii=False)
        body = (
            CreateMessageRequestBody.builder()
            .receive_id(chat_id)
            .msg_type("text")
            .content(payload)
            .build()
        )
        request = (
            CreateMessageRequest.builder()
            .receive_id_type("chat_id")
            .request_body(body)
            .build()
        )
        try:
            response = await asyncio.to_thread(self._client.im.v1.message.create, request)
            if response and response.success():
                msg = getattr(response, "data", None)
                message_id = getattr(msg, "message_id", None) if msg else None
                return SendResult(success=True, message_id=message_id, raw_response=response)
            return SendResult(
                success=False,
                error=str(getattr(response, "msg", "") or "发送失败"),
                raw_response=response,
            )
        except Exception as exc:
            logger.error("[feishu] 发送失败: %s", exc, exc_info=True)
            return SendResult(success=False, error=str(exc))

    async def get_chat_info(self, chat_id: str) -> Dict[str, Any]:
        return {"id": chat_id, "name": chat_id, "type": "unknown"}

"""
个人微信（WeChat）平台适配器。

基于腾讯 iLink Bot API 实现，通过长轮询（long-poll getupdates）接收消息，
通过 sendmessage API 发送回复。

实现参考：https://github.com/NousResearch/hermes-agent（gateway/platforms/weixin.py）

主要流程
--------
1. QR 码登录：调用 iLink get_bot_qrcode → 展示二维码 → 轮询 get_qrcode_status → 保存 token
2. 长轮询收消息：getupdates 接口（35s 超时），解析 msgs 数组
3. 发送消息：sendmessage 接口，需携带 context_token
4. 会话 token 持久化：存储到 gateway_data/weixin/ 目录下的 JSON 文件
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import os
import secrets
import struct
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

try:
    import aiohttp
    AIOHTTP_AVAILABLE = True
except ImportError:
    aiohttp = None  # type: ignore[assignment]
    AIOHTTP_AVAILABLE = False

try:
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    CRYPTO_AVAILABLE = True
except ImportError:
    default_backend = None  # type: ignore[assignment]
    Cipher = None           # type: ignore[assignment]
    algorithms = None       # type: ignore[assignment]
    modes = None            # type: ignore[assignment]
    CRYPTO_AVAILABLE = False

from gateway.base import (
    BasePlatformAdapter,
    MessageEvent,
    MessageType,
    SendResult,
    SessionSource,
)

# ---------------------------------------------------------------------------
# iLink API 常量
# ---------------------------------------------------------------------------

ILINK_BASE_URL = "https://ilinkai.weixin.qq.com"
WEIXIN_CDN_BASE_URL = "https://novac2c.cdn.weixin.qq.com/c2c"
ILINK_APP_ID = "bot"
CHANNEL_VERSION = "2.2.0"
ILINK_APP_CLIENT_VERSION = (2 << 16) | (2 << 8) | 0

EP_GET_UPDATES = "ilink/bot/getupdates"
EP_SEND_MESSAGE = "ilink/bot/sendmessage"
EP_SEND_TYPING = "ilink/bot/sendtyping"
EP_GET_CONFIG = "ilink/bot/getconfig"
EP_GET_BOT_QR = "ilink/bot/get_bot_qrcode"
EP_GET_QR_STATUS = "ilink/bot/get_qrcode_status"

LONG_POLL_TIMEOUT_MS = 35_000
API_TIMEOUT_MS = 15_000
CONFIG_TIMEOUT_MS = 10_000
QR_TIMEOUT_MS = 35_000

MAX_CONSECUTIVE_FAILURES = 3
RETRY_DELAY_SECONDS = 2
BACKOFF_DELAY_SECONDS = 30
SESSION_EXPIRED_ERRCODE = -14
RATE_LIMIT_ERRCODE = -2
MESSAGE_DEDUP_TTL_SECONDS = 300

ITEM_TEXT = 1
ITEM_IMAGE = 2
ITEM_VOICE = 3
ITEM_FILE = 4
ITEM_VIDEO = 5

MSG_TYPE_BOT = 2
MSG_STATE_FINISH = 2

TYPING_START = 1
TYPING_STOP = 2

# ---------------------------------------------------------------------------
# 数据目录（gateway_data/weixin/）
# ---------------------------------------------------------------------------

_GATEWAY_ROOT = Path(__file__).resolve().parent.parent.parent
WEIXIN_DATA_DIR = _GATEWAY_ROOT / "gateway_data" / "weixin"


def _account_dir() -> Path:
    WEIXIN_DATA_DIR.mkdir(parents=True, exist_ok=True)
    return WEIXIN_DATA_DIR


def _json_write(path: Path, data: dict) -> None:
    """原子性（先写临时文件再重命名）JSON 写入。"""
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


# ---------------------------------------------------------------------------
# 账号凭证持久化
# ---------------------------------------------------------------------------

def save_weixin_account(
    account_id: str,
    token: str,
    base_url: str,
    user_id: str = "",
) -> None:
    """持久化保存 iLink 账号凭证。"""
    path = _account_dir() / f"{account_id}.json"
    _json_write(path, {
        "token": token,
        "base_url": base_url,
        "user_id": user_id,
        "saved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    })
    try:
        path.chmod(0o600)
    except OSError:
        pass


def load_weixin_account(account_id: str) -> Optional[Dict[str, Any]]:
    """从磁盘加载已保存的账号凭证。"""
    return _json_read(_account_dir() / f"{account_id}.json")


def list_weixin_accounts() -> List[str]:
    """返回所有已保存的 account_id 列表。"""
    d = _account_dir()
    return [
        p.stem for p in d.glob("*.json")
        if not p.name.endswith((".context-tokens.json", ".sync.json"))
    ]


# ---------------------------------------------------------------------------
# context_token 持久化缓存
# ---------------------------------------------------------------------------

class ContextTokenStore:
    """磁盘持久化的 context_token 缓存，按 account_id + peer_user_id 索引。"""

    def __init__(self):
        self._cache: Dict[str, str] = {}

    def _path(self, account_id: str) -> Path:
        return _account_dir() / f"{account_id}.context-tokens.json"

    def _key(self, account_id: str, user_id: str) -> str:
        return f"{account_id}:{user_id}"

    def restore(self, account_id: str) -> None:
        data = _json_read(self._path(account_id)) or {}
        for uid, tok in data.items():
            if isinstance(tok, str) and tok:
                self._cache[self._key(account_id, uid)] = tok

    def get(self, account_id: str, user_id: str) -> Optional[str]:
        return self._cache.get(self._key(account_id, user_id))

    def set(self, account_id: str, user_id: str, token: str) -> None:
        self._cache[self._key(account_id, user_id)] = token
        self._persist(account_id)

    def _persist(self, account_id: str) -> None:
        prefix = f"{account_id}:"
        payload = {k[len(prefix):]: v for k, v in self._cache.items() if k.startswith(prefix)}
        try:
            _json_write(self._path(account_id), payload)
        except Exception as exc:
            logger.warning("weixin: context_token 持久化失败: %s", exc)


# ---------------------------------------------------------------------------
# sync_buf 持久化
# ---------------------------------------------------------------------------

def _sync_buf_path(account_id: str) -> Path:
    return _account_dir() / f"{account_id}.sync.json"


def _load_sync_buf(account_id: str) -> str:
    data = _json_read(_sync_buf_path(account_id))
    return (data or {}).get("get_updates_buf", "")


def _save_sync_buf(account_id: str, sync_buf: str) -> None:
    _json_write(_sync_buf_path(account_id), {"get_updates_buf": sync_buf})


# ---------------------------------------------------------------------------
# 消息去重
# ---------------------------------------------------------------------------

class MessageDeduplicator:
    def __init__(self, ttl_seconds: float = MESSAGE_DEDUP_TTL_SECONDS):
        self._ttl = ttl_seconds
        self._seen: Dict[str, float] = {}

    def is_duplicate(self, key: str) -> bool:
        now = time.monotonic()
        if key in self._seen:
            if now - self._seen[key] < self._ttl:
                return True
        self._seen[key] = now
        # 简单清理过期条目
        if len(self._seen) > 10000:
            self._seen = {k: v for k, v in self._seen.items() if now - v < self._ttl}
        return False


# ---------------------------------------------------------------------------
# iLink HTTP 工具函数
# ---------------------------------------------------------------------------

def _random_wechat_uin() -> str:
    value = struct.unpack(">I", secrets.token_bytes(4))[0]
    return base64.b64encode(str(value).encode("utf-8")).decode("ascii")


def _base_info() -> Dict[str, Any]:
    return {"channel_version": CHANNEL_VERSION}


def _headers(token: Optional[str], body: str) -> Dict[str, str]:
    headers = {
        "Content-Type": "application/json",
        "AuthorizationType": "ilink_bot_token",
        "Content-Length": str(len(body.encode("utf-8"))),
        "X-WECHAT-UIN": _random_wechat_uin(),
        "iLink-App-Id": ILINK_APP_ID,
        "iLink-App-ClientVersion": str(ILINK_APP_CLIENT_VERSION),
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _json_dumps(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _make_ssl_connector() -> Optional["aiohttp.TCPConnector"]:
    """使用 certifi CA bundle 创建 TCPConnector，处理 iLink 服务器证书问题。"""
    if not AIOHTTP_AVAILABLE:
        return None
    try:
        import ssl
        import certifi
        ssl_ctx = ssl.create_default_context(cafile=certifi.where())
        return aiohttp.TCPConnector(ssl=ssl_ctx)
    except Exception:
        return None


def _is_stale_session_ret(ret, errcode, errmsg) -> bool:
    if ret != RATE_LIMIT_ERRCODE and errcode != RATE_LIMIT_ERRCODE:
        return False
    return (errmsg or "").lower() == "unknown error"


async def _api_post(
    session: "aiohttp.ClientSession",
    *,
    base_url: str,
    endpoint: str,
    payload: Dict[str, Any],
    token: Optional[str],
    timeout_ms: int,
) -> Dict[str, Any]:
    body = _json_dumps({**payload, "base_info": _base_info()})
    url = f"{base_url.rstrip('/')}/{endpoint}"
    timeout = aiohttp.ClientTimeout(total=timeout_ms / 1000)
    async with session.post(url, data=body, headers=_headers(token, body), timeout=timeout) as resp:
        raw = await resp.text()
        if not resp.ok:
            raise RuntimeError(f"iLink POST {endpoint} HTTP {resp.status}: {raw[:200]}")
        return json.loads(raw)


async def _api_get(
    session: "aiohttp.ClientSession",
    *,
    base_url: str,
    endpoint: str,
    timeout_ms: int,
) -> Dict[str, Any]:
    url = f"{base_url.rstrip('/')}/{endpoint}"
    hdrs = {
        "iLink-App-Id": ILINK_APP_ID,
        "iLink-App-ClientVersion": str(ILINK_APP_CLIENT_VERSION),
    }
    timeout = aiohttp.ClientTimeout(total=timeout_ms / 1000)
    async with session.get(url, headers=hdrs, timeout=timeout) as resp:
        raw = await resp.text()
        if not resp.ok:
            raise RuntimeError(f"iLink GET {endpoint} HTTP {resp.status}: {raw[:200]}")
        return json.loads(raw)


async def _get_updates(
    session: "aiohttp.ClientSession",
    *,
    base_url: str,
    token: str,
    sync_buf: str,
    timeout_ms: int,
) -> Dict[str, Any]:
    try:
        return await _api_post(
            session,
            base_url=base_url,
            endpoint=EP_GET_UPDATES,
            payload={"get_updates_buf": sync_buf},
            token=token,
            timeout_ms=timeout_ms,
        )
    except asyncio.TimeoutError:
        return {"ret": 0, "msgs": [], "get_updates_buf": sync_buf}


async def _send_message(
    session: "aiohttp.ClientSession",
    *,
    base_url: str,
    token: str,
    to: str,
    text: str,
    context_token: Optional[str],
    client_id: str,
) -> Dict[str, Any]:
    if not text or not text.strip():
        raise ValueError("_send_message: text must not be empty")
    message: Dict[str, Any] = {
        "from_user_id": "",
        "to_user_id": to,
        "client_id": client_id,
        "message_type": MSG_TYPE_BOT,
        "message_state": MSG_STATE_FINISH,
        "item_list": [{"type": ITEM_TEXT, "text_item": {"text": text}}],
    }
    if context_token:
        message["context_token"] = context_token
    return await _api_post(
        session,
        base_url=base_url,
        endpoint=EP_SEND_MESSAGE,
        payload={"msg": message},
        token=token,
        timeout_ms=API_TIMEOUT_MS,
    )


async def _get_config(
    session: "aiohttp.ClientSession",
    *,
    base_url: str,
    token: str,
    user_id: str,
    context_token: Optional[str],
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"ilink_user_id": user_id}
    if context_token:
        payload["context_token"] = context_token
    return await _api_post(
        session,
        base_url=base_url,
        endpoint=EP_GET_CONFIG,
        payload=payload,
        token=token,
        timeout_ms=CONFIG_TIMEOUT_MS,
    )


# ---------------------------------------------------------------------------
# 消息解析辅助函数
# ---------------------------------------------------------------------------

def _extract_text(item_list: List[Dict[str, Any]]) -> str:
    for item in item_list:
        if item.get("type") == ITEM_TEXT:
            text = str((item.get("text_item") or {}).get("text") or "")
            ref = item.get("ref_msg") or {}
            ref_item = ref.get("message_item") or {}
            ref_type = ref_item.get("type")
            if ref_type in {ITEM_IMAGE, ITEM_VIDEO, ITEM_FILE, ITEM_VOICE}:
                title = ref.get("title") or ""
                prefix = f"[引用媒体: {title}]\n" if title else "[引用媒体]\n"
                return f"{prefix}{text}".strip()
            if ref_item:
                parts: List[str] = []
                if ref.get("title"):
                    parts.append(str(ref["title"]))
                ref_text = _extract_text([ref_item])
                if ref_text:
                    parts.append(ref_text)
                if parts:
                    return f"[引用: {' | '.join(parts)}]\n{text}".strip()
            return text
    for item in item_list:
        if item.get("type") == ITEM_VOICE:
            voice_text = str((item.get("voice_item") or {}).get("text") or "")
            if voice_text:
                return voice_text
    return ""


def _message_type_from_items(item_list: List[Dict[str, Any]], text: str) -> MessageType:
    for item in item_list:
        t = item.get("type")
        if t == ITEM_IMAGE:
            return MessageType.PHOTO
        if t == ITEM_VIDEO:
            return MessageType.VIDEO
        if t == ITEM_VOICE:
            return MessageType.VOICE
        if t == ITEM_FILE:
            return MessageType.DOCUMENT
    if text.startswith("/"):
        return MessageType.COMMAND
    return MessageType.TEXT


def _guess_chat_type(message: Dict[str, Any], account_id: str) -> Tuple[str, str]:
    room_id = str(message.get("room_id") or message.get("chat_room_id") or "").strip()
    to_user_id = str(message.get("to_user_id") or "").strip()
    is_group = bool(room_id) or (
        to_user_id and account_id
        and to_user_id != account_id
        and message.get("msg_type") == 1
    )
    if is_group:
        return "group", room_id or to_user_id or str(message.get("from_user_id") or "")
    return "dm", str(message.get("from_user_id") or "")


def _safe_id(value: Optional[str], keep: int = 8) -> str:
    raw = str(value or "").strip()
    if not raw:
        return "?"
    return raw[:keep] if len(raw) > keep else raw


# ---------------------------------------------------------------------------
# QR 登录流程（适配 Web API 使用）
# ---------------------------------------------------------------------------

class QRLoginSession:
    """
    iLink QR 登录会话。

    提供 start() 获取二维码，poll() 轮询状态。
    用于被 gateway/web.py 的 REST API 调用，避免 CLI 式阻塞等待。
    """

    STATUS_WAIT = "wait"
    STATUS_SCANNED = "scaned"
    STATUS_CONFIRMED = "confirmed"
    STATUS_EXPIRED = "expired"
    STATUS_ERROR = "error"

    def __init__(self):
        self.qrcode_value: str = ""
        self.qrcode_url: str = ""
        self.status: str = self.STATUS_WAIT
        self.current_base_url: str = ILINK_BASE_URL
        self.result: Optional[Dict[str, str]] = None
        self.error_msg: str = ""
        self._session: Optional["aiohttp.ClientSession"] = None

    async def start(self, bot_type: str = "3") -> Dict[str, Any]:
        """
        向 iLink 申请二维码，返回包含 qrcode_url 的字典。
        需要在调用 poll() 前先调用此方法。
        """
        if not AIOHTTP_AVAILABLE:
            return {"error": "aiohttp 未安装，无法使用微信登录"}

        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                trust_env=True, connector=_make_ssl_connector()
            )

        try:
            qr_resp = await _api_get(
                self._session,
                base_url=ILINK_BASE_URL,
                endpoint=f"{EP_GET_BOT_QR}?bot_type={bot_type}",
                timeout_ms=QR_TIMEOUT_MS,
            )
        except Exception as exc:
            logger.error("weixin: 获取二维码失败: %s", exc)
            return {"error": f"获取二维码失败: {exc}"}

        self.qrcode_value = str(qr_resp.get("qrcode") or "")
        self.qrcode_url = str(qr_resp.get("qrcode_img_content") or "")

        if not self.qrcode_value:
            return {"error": "iLink 返回的二维码数据为空"}

        self.status = self.STATUS_WAIT
        logger.info("weixin: 二维码已获取，请扫码")
        return {
            "qrcode_url": self.qrcode_url or self.qrcode_value,
            "qrcode_value": self.qrcode_value,
        }

    async def poll(self) -> Dict[str, Any]:
        """
        轮询一次 iLink 的二维码扫描状态。
        返回 {"status": ..., "result": ...（仅 confirmed 时）}
        """
        if not self._session or self._session.closed:
            return {"status": self.STATUS_ERROR, "error": "会话未启动，请先调用 start()"}
        if not self.qrcode_value:
            return {"status": self.STATUS_ERROR, "error": "二维码未获取，请先调用 start()"}

        try:
            resp = await _api_get(
                self._session,
                base_url=self.current_base_url,
                endpoint=f"{EP_GET_QR_STATUS}?qrcode={self.qrcode_value}",
                timeout_ms=QR_TIMEOUT_MS,
            )
        except asyncio.TimeoutError:
            return {"status": self.status}
        except Exception as exc:
            logger.warning("weixin: QR 状态轮询错误: %s", exc)
            return {"status": self.STATUS_ERROR, "error": str(exc)}

        status = str(resp.get("status") or "wait")
        self.status = status

        if status == "scaned_but_redirect":
            redirect_host = str(resp.get("redirect_host") or "")
            if redirect_host:
                self.current_base_url = f"https://{redirect_host}"
            return {"status": "scaned"}

        if status == "expired":
            # 自动刷新一次二维码
            logger.info("weixin: 二维码已过期，自动刷新")
            try:
                qr_resp = await _api_get(
                    self._session,
                    base_url=ILINK_BASE_URL,
                    endpoint=f"{EP_GET_BOT_QR}?bot_type=3",
                    timeout_ms=QR_TIMEOUT_MS,
                )
                self.qrcode_value = str(qr_resp.get("qrcode") or "")
                self.qrcode_url = str(qr_resp.get("qrcode_img_content") or "")
                self.status = self.STATUS_WAIT
                self.current_base_url = ILINK_BASE_URL
                return {
                    "status": "refreshed",
                    "qrcode_url": self.qrcode_url or self.qrcode_value,
                    "qrcode_value": self.qrcode_value,
                }
            except Exception as exc:
                return {"status": self.STATUS_ERROR, "error": f"二维码刷新失败: {exc}"}

        if status == "confirmed":
            account_id = str(resp.get("ilink_bot_id") or "")
            token = str(resp.get("bot_token") or "")
            base_url = str(resp.get("baseurl") or ILINK_BASE_URL)
            user_id = str(resp.get("ilink_user_id") or "")

            if not account_id or not token:
                return {"status": self.STATUS_ERROR, "error": "登录成功但凭证数据不完整"}

            save_weixin_account(
                account_id=account_id,
                token=token,
                base_url=base_url,
                user_id=user_id,
            )
            self.result = {
                "account_id": account_id,
                "token": token,
                "base_url": base_url,
                "user_id": user_id,
            }
            logger.info("weixin: 登录成功，account_id=%s", _safe_id(account_id))
            return {"status": "confirmed", "account_id": account_id, "user_id": user_id}

        return {"status": status}

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
        self._session = None


# ---------------------------------------------------------------------------
# typing ticket 缓存
# ---------------------------------------------------------------------------

class TypingTicketCache:
    def __init__(self, ttl_seconds: float = 600.0):
        self._ttl = ttl_seconds
        self._cache: Dict[str, Tuple[str, float]] = {}

    def get(self, user_id: str) -> Optional[str]:
        entry = self._cache.get(user_id)
        if not entry:
            return None
        if time.time() - entry[1] >= self._ttl:
            self._cache.pop(user_id, None)
            return None
        return entry[0]

    def set(self, user_id: str, ticket: str) -> None:
        self._cache[user_id] = (ticket, time.time())


# ---------------------------------------------------------------------------
# WeixinAdapter
# ---------------------------------------------------------------------------

class WeixinAdapter(BasePlatformAdapter):
    """
    个人微信（iLink Bot）平台适配器。

    通过长轮询 getupdates 接收消息，通过 sendmessage 发送回复。
    参考 hermes-agent (https://github.com/NousResearch/hermes-agent) 的 weixin.py 实现。

    环境变量配置
    ------------
    WEIXIN_ACCOUNT_ID   iLink Bot ID（QR 登录成功后自动保存，此变量可选）
    WEIXIN_TOKEN        iLink Bot Token（QR 登录成功后自动保存，此变量可选）
    WEIXIN_BASE_URL     iLink API 基础地址（默认 https://ilinkai.weixin.qq.com）
    """

    MAX_MESSAGE_LENGTH = 2000

    def __init__(self):
        super().__init__("weixin")
        # 优先从磁盘加载 QR 扫码后保存的凭证（由 Web UI 写入）
        # 环境变量 WEIXIN_ACCOUNT_ID / WEIXIN_TOKEN 仅作为 headless 部署兜底，
        # 普通用户请通过管理界面（http://localhost:8082）扫码登录，无需手动配置
        self._account_id = ""
        self._token = ""
        self._base_url = os.getenv("WEIXIN_BASE_URL", ILINK_BASE_URL).strip().rstrip("/")

        # 尝试从磁盘加载最近保存的账号凭证
        accounts = list_weixin_accounts()
        if accounts:
            persisted = load_weixin_account(accounts[0])
            if persisted:
                self._account_id = str(persisted.get("account_id") or accounts[0]).strip()
                self._token = str(persisted.get("token") or "").strip()
                self._base_url = str(persisted.get("base_url") or self._base_url).strip().rstrip("/")

        # 环境变量兜底（headless 部署场景）
        if not self._account_id:
            self._account_id = os.getenv("WEIXIN_ACCOUNT_ID", "").strip()
        if not self._token:
            self._token = os.getenv("WEIXIN_TOKEN", "").strip()

        self._token_store = ContextTokenStore()
        self._typing_cache = TypingTicketCache()
        self._dedup = MessageDeduplicator()

        self._poll_session: Optional["aiohttp.ClientSession"] = None
        self._send_session: Optional["aiohttp.ClientSession"] = None
        self._poll_task: Optional[asyncio.Task] = None

        self._send_chunk_delay_seconds = float(os.getenv("WEIXIN_SEND_CHUNK_DELAY", "1.5"))
        self._send_chunk_retries = int(os.getenv("WEIXIN_SEND_CHUNK_RETRIES", "4"))
        self._send_chunk_retry_delay_seconds = float(
            os.getenv("WEIXIN_SEND_CHUNK_RETRY_DELAY", "1.0")
        )

    # ------------------------------------------------------------------
    # 外部状态查询（供 web.py 使用）
    # ------------------------------------------------------------------

    @property
    def is_connected(self) -> bool:
        return self._running and bool(self._token)

    def reload_credentials(self) -> bool:
        """
        尝试从磁盘重新加载最新的账号凭证。
        用于 QR 扫码登录成功后，让已运行的 adapter 刷新 token。
        返回 True 表示成功加载。
        """
        accounts = list_weixin_accounts()
        if not accounts:
            return False
        # 默认加载第一个（或已配置的 account_id 对应的）
        target = self._account_id or accounts[0]
        data = load_weixin_account(target)
        if not data:
            return False
        self._account_id = target
        self._token = str(data.get("token") or "").strip()
        self._base_url = str(data.get("base_url") or ILINK_BASE_URL).strip().rstrip("/")
        logger.info("weixin: 凭证已重新加载，account=%s", _safe_id(self._account_id))
        return bool(self._token)

    # ------------------------------------------------------------------
    # connect / disconnect
    # ------------------------------------------------------------------

    async def connect(self) -> bool:
        if not AIOHTTP_AVAILABLE:
            logger.warning("[weixin] aiohttp 未安装，无法连接")
            return False

        if not self._token:
            logger.warning("[weixin] WEIXIN_TOKEN 未配置，跳过连接（可通过 Web UI 扫码登录）")
            return False

        if not self._account_id:
            logger.warning("[weixin] WEIXIN_ACCOUNT_ID 未配置，跳过连接")
            return False

        _no_timeout = aiohttp.ClientTimeout(total=None, connect=None, sock_connect=None, sock_read=None)
        self._poll_session = aiohttp.ClientSession(
            trust_env=True, connector=_make_ssl_connector()
        )
        self._send_session = aiohttp.ClientSession(
            trust_env=True, connector=_make_ssl_connector(), timeout=_no_timeout
        )
        self._token_store.restore(self._account_id)
        self._running = True
        self._poll_task = asyncio.create_task(self._poll_loop(), name="weixin-poll")
        logger.info(
            "[weixin] 已连接，account=%s base=%s",
            _safe_id(self._account_id), self._base_url,
        )
        return True

    async def disconnect(self) -> None:
        self._running = False
        if self._poll_task and not self._poll_task.done():
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
        self._poll_task = None
        for session in (self._poll_session, self._send_session):
            if session and not session.closed:
                await session.close()
        self._poll_session = None
        self._send_session = None
        logger.info("[weixin] 已断开连接")

    # ------------------------------------------------------------------
    # 长轮询主循环
    # ------------------------------------------------------------------

    async def _poll_loop(self) -> None:
        assert self._poll_session is not None
        sync_buf = _load_sync_buf(self._account_id)
        timeout_ms = LONG_POLL_TIMEOUT_MS
        failures = 0

        while self._running:
            try:
                response = await _get_updates(
                    self._poll_session,
                    base_url=self._base_url,
                    token=self._token,
                    sync_buf=sync_buf,
                    timeout_ms=timeout_ms,
                )
                suggested = response.get("longpolling_timeout_ms")
                if isinstance(suggested, int) and suggested > 0:
                    timeout_ms = suggested

                ret = response.get("ret", 0)
                errcode = response.get("errcode", 0)
                if ret not in {0, None} or errcode not in {0, None}:
                    if (ret == SESSION_EXPIRED_ERRCODE or errcode == SESSION_EXPIRED_ERRCODE
                            or _is_stale_session_ret(ret, errcode, response.get("errmsg"))):
                        logger.error("[weixin] 会话已过期，暂停 10 分钟后重试")
                        await asyncio.sleep(600)
                        failures = 0
                        continue
                    failures += 1
                    logger.warning(
                        "[weixin] getupdates 失败 ret=%s errcode=%s (%d/%d)",
                        ret, errcode, failures, MAX_CONSECUTIVE_FAILURES,
                    )
                    await asyncio.sleep(
                        BACKOFF_DELAY_SECONDS if failures >= MAX_CONSECUTIVE_FAILURES
                        else RETRY_DELAY_SECONDS
                    )
                    if failures >= MAX_CONSECUTIVE_FAILURES:
                        failures = 0
                    continue

                failures = 0
                new_buf = str(response.get("get_updates_buf") or "")
                if new_buf:
                    sync_buf = new_buf
                    _save_sync_buf(self._account_id, sync_buf)

                for message in response.get("msgs") or []:
                    asyncio.create_task(self._process_message_safe(message))

            except asyncio.CancelledError:
                break
            except Exception as exc:
                failures += 1
                logger.error("[weixin] 轮询错误 (%d/%d): %s", failures, MAX_CONSECUTIVE_FAILURES, exc)
                await asyncio.sleep(
                    BACKOFF_DELAY_SECONDS if failures >= MAX_CONSECUTIVE_FAILURES
                    else RETRY_DELAY_SECONDS
                )
                if failures >= MAX_CONSECUTIVE_FAILURES:
                    failures = 0

    # ------------------------------------------------------------------
    # 消息处理
    # ------------------------------------------------------------------

    async def _process_message_safe(self, message: Dict[str, Any]) -> None:
        try:
            await self._process_message(message)
        except Exception as exc:
            logger.error(
                "[weixin] 处理消息异常 from=%s: %s",
                _safe_id(message.get("from_user_id")), exc, exc_info=True,
            )

    async def _process_message(self, message: Dict[str, Any]) -> None:
        sender_id = str(message.get("from_user_id") or "").strip()
        if not sender_id or sender_id == self._account_id:
            return

        message_id = str(message.get("message_id") or "").strip()
        if message_id and self._dedup.is_duplicate(message_id):
            return

        item_list = message.get("item_list") or []
        text = _extract_text(item_list)

        if text:
            content_key = f"content:{sender_id}:{hashlib.md5(text.encode()).hexdigest()}"
            if self._dedup.is_duplicate(content_key):
                return

        chat_type, chat_id = _guess_chat_type(message, self._account_id)

        context_token = str(message.get("context_token") or "").strip()
        if context_token:
            self._token_store.set(self._account_id, sender_id, context_token)
            asyncio.create_task(self._maybe_fetch_typing_ticket(sender_id, context_token))

        if not text:
            return

        source = self.build_source(
            chat_id=chat_id,
            chat_type=chat_type,
            user_id=sender_id,
            user_name=sender_id,
        )
        event = MessageEvent(
            text=text,
            message_type=_message_type_from_items(item_list, text),
            source=source,
            raw_message=message,
            message_id=message_id or None,
            timestamp=datetime.now(),
        )
        logger.info("[weixin] 收到消息 from=%s type=%s", _safe_id(sender_id), chat_type)
        await self.handle_message(event)

    async def _maybe_fetch_typing_ticket(self, user_id: str, context_token: Optional[str]) -> None:
        if not self._poll_session or not self._token:
            return
        if self._typing_cache.get(user_id):
            return
        try:
            resp = await _get_config(
                self._poll_session,
                base_url=self._base_url,
                token=self._token,
                user_id=user_id,
                context_token=context_token,
            )
            ticket = str(resp.get("typing_ticket") or "")
            if ticket:
                self._typing_cache.set(user_id, ticket)
        except Exception as exc:
            logger.debug("[weixin] getConfig 失败 for %s: %s", _safe_id(user_id), exc)

    # ------------------------------------------------------------------
    # 发送文本消息（带分块和重试）
    # ------------------------------------------------------------------

    def _split_text(self, content: str) -> List[str]:
        """将超长消息按 MAX_MESSAGE_LENGTH 分块。"""
        if len(content) <= self.MAX_MESSAGE_LENGTH:
            return [content]
        chunks: List[str] = []
        while content:
            chunks.append(content[:self.MAX_MESSAGE_LENGTH])
            content = content[self.MAX_MESSAGE_LENGTH:]
        return chunks

    async def _send_text_chunk(
        self,
        *,
        chat_id: str,
        chunk: str,
        context_token: Optional[str],
        client_id: str,
    ) -> None:
        last_error: Optional[Exception] = None
        retried_without_token = False

        for attempt in range(self._send_chunk_retries + 1):
            try:
                resp = await _send_message(
                    self._send_session,
                    base_url=self._base_url,
                    token=self._token,
                    to=chat_id,
                    text=chunk,
                    context_token=context_token,
                    client_id=client_id,
                )
                if isinstance(resp, dict):
                    ret = resp.get("ret")
                    errcode = resp.get("errcode")
                    if (ret is not None and ret not in {0}) or (errcode is not None and errcode not in {0}):
                        is_expired = (
                            ret == SESSION_EXPIRED_ERRCODE
                            or errcode == SESSION_EXPIRED_ERRCODE
                            or _is_stale_session_ret(ret, errcode, resp.get("errmsg"))
                        )
                        if is_expired and not retried_without_token and context_token:
                            retried_without_token = True
                            context_token = None
                            continue
                        errmsg = resp.get("errmsg") or "unknown error"
                        raise RuntimeError(
                            f"iLink sendmessage error: ret={ret} errcode={errcode} errmsg={errmsg}"
                        )
                return
            except Exception as exc:
                last_error = exc
                if attempt >= self._send_chunk_retries:
                    break
                wait = self._send_chunk_retry_delay_seconds * (attempt + 1)
                logger.warning(
                    "[weixin] 发送失败 to=%s 第%d次重试 %.2fs: %s",
                    _safe_id(chat_id), attempt + 1, wait, exc,
                )
                if wait > 0:
                    await asyncio.sleep(wait)

        if last_error:
            raise last_error

    async def send(
        self,
        chat_id: str,
        content: str,
        reply_to: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SendResult:
        if not self._send_session or not self._token:
            return SendResult(success=False, error="未连接，无法发送消息")

        context_token = self._token_store.get(self._account_id, chat_id)
        last_message_id: Optional[str] = None

        try:
            chunks = [c for c in self._split_text(content) if c and c.strip()]
            for idx, chunk in enumerate(chunks):
                client_id = f"soulprout-weixin-{uuid.uuid4().hex}"
                await self._send_text_chunk(
                    chat_id=chat_id,
                    chunk=chunk,
                    context_token=context_token,
                    client_id=client_id,
                )
                last_message_id = client_id
                if idx < len(chunks) - 1 and self._send_chunk_delay_seconds > 0:
                    await asyncio.sleep(self._send_chunk_delay_seconds)
            return SendResult(success=True, message_id=last_message_id)
        except Exception as exc:
            logger.error("[weixin] 发送失败 to=%s: %s", _safe_id(chat_id), exc)
            return SendResult(success=False, error=str(exc))

    async def get_chat_info(self, chat_id: str) -> Dict[str, Any]:
        chat_type = "group" if chat_id.endswith("@chatroom") else "dm"
        return {"name": chat_id, "type": chat_type, "chat_id": chat_id}

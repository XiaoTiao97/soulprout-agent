"""微信客服（WeCom Customer Service）接入适配器。

工作流程：
  1. 微信客服服务器将 kf_msg_or_event 事件 POST 回调到企业指定 URL
  2. 本适配器验签解密，提取 sync_msg 用的 Token 和 OpenKfId
  3. 调用 sync_msg 接口增量拉取具体消息（游标续拉，has_more 循环）
  4. 将消息封装为 MessageEvent，分发给业务处理器
  5. 业务层通过 send() 调用 kf/send_msg API 回复客户

chat_id 约定：
    {open_kfid}:{external_userid}
    例如：wkAJ2GCAAASSm4_FhToWMFea0xAFfd3Q:wmAJ2GCAAAme1XQRC-NI-q0_ZM9ukoAw

使用示例：
    from gateway.platforms.wecom_kf import WeComKFAdapter, WeComKFConfig

    adapter = WeComKFAdapter(WeComKFConfig.from_env())
    adapter.set_message_handler(my_handler)
    await adapter.connect()   # 启动内置 HTTP 服务器
    ...
    await adapter.disconnect()
"""

from __future__ import annotations

import asyncio
import logging
import socket as _socket
import time
from typing import Any, Dict, List, Optional
from xml.etree import ElementTree as ET

import httpx
from aiohttp import web

from gateway.base import (
    BasePlatformAdapter,
    MessageEvent,
    MessageType,
    SendResult,
)
from gateway.platforms.wecom_crypto import WXBizMsgCrypt, WeComCryptoError

logger = logging.getLogger(__name__)

PLATFORM_NAME = "wecom_kf"
WECOM_API_BASE = "https://qyapi.weixin.qq.com/cgi-bin"
ACCESS_TOKEN_TTL_SECONDS = 7200
SYNC_MSG_LIMIT = 1000
MESSAGE_DEDUP_TTL_SECONDS = 300
DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8091


class WeComKFConfig:
    """微信客服适配器配置，从 .env 或环境变量加载。"""

    def __init__(
        self,
        corp_id: str,
        kf_secret: str,
        callback_token: str,
        encoding_aes_key: str,
        callback_path: str = "/wecom/kf/callback",
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
    ):
        self.corp_id = corp_id
        self.kf_secret = kf_secret
        self.callback_token = callback_token
        self.encoding_aes_key = encoding_aes_key
        self.callback_path = callback_path
        self.host = host
        self.port = port

    @classmethod
    def from_env(cls) -> "WeComKFConfig":
        """从 gateway/.env 或当前环境变量中读取配置。"""
        import os
        from pathlib import Path

        try:
            from dotenv import load_dotenv
            env_file = Path(__file__).resolve().parent.parent / ".env"
            load_dotenv(dotenv_path=env_file, override=False)
        except ImportError:
            pass

        required = {
            "WECOM_CORP_ID": os.getenv("WECOM_CORP_ID", ""),
            "WECOM_KF_SECRET": os.getenv("WECOM_KF_SECRET", ""),
            "WECOM_KF_CALLBACK_TOKEN": os.getenv("WECOM_KF_CALLBACK_TOKEN", ""),
            "WECOM_KF_ENCODING_AES_KEY": os.getenv("WECOM_KF_ENCODING_AES_KEY", ""),
        }
        missing = [k for k, v in required.items() if not v]
        if missing:
            raise ValueError(f"微信客服配置缺少以下环境变量: {', '.join(missing)}")

        return cls(
            corp_id=required["WECOM_CORP_ID"],
            kf_secret=required["WECOM_KF_SECRET"],
            callback_token=required["WECOM_KF_CALLBACK_TOKEN"],
            encoding_aes_key=required["WECOM_KF_ENCODING_AES_KEY"],
            callback_path=os.getenv("WECOM_KF_CALLBACK_PATH", "/wecom/kf/callback"),
            host=os.getenv("WECOM_KF_HOST", DEFAULT_HOST),
            port=int(os.getenv("WECOM_KF_PORT", str(DEFAULT_PORT))),
        )


class WeComKFAdapter(BasePlatformAdapter):
    """
    微信客服适配器，自带 aiohttp HTTP 服务器。

    对外暴露：
    - connect() / disconnect()   启动/停止内置 HTTP 服务器
    - send()                     向客户发送文本消息
    - get_chat_info()            获取会话信息
    - set_message_handler()      注入消息处理回调（继承自基类）
    """

    def __init__(self, config: WeComKFConfig):
        super().__init__(PLATFORM_NAME)
        self._config = config
        self._http_client: Optional[httpx.AsyncClient] = None
        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0.0
        # 每个 open_kfid 独立维护拉取游标
        self._cursors: Dict[str, str] = {}
        # 消息去重缓存 {msgid: timestamp}
        self._seen_messages: Dict[str, float] = {}
        # 待处理事件队列
        self._event_queue: asyncio.Queue[tuple] = asyncio.Queue()
        self._dispatch_task: Optional[asyncio.Task] = None
        # aiohttp 服务器相关
        self._aiohttp_app: Optional[web.Application] = None
        self._runner: Optional[web.AppRunner] = None
        self._site: Optional[web.TCPSite] = None

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    async def connect(self) -> bool:
        """启动内置 HTTP 服务器并初始化 Access Token。"""
        if not self._check_port_free():
            logger.error("[WeComKF] 端口 %d 已被占用", self._config.port)
            return False
        try:
            self._http_client = httpx.AsyncClient(timeout=20.0)
            await self._refresh_access_token()

            # 启动 aiohttp 服务器
            self._aiohttp_app = web.Application()
            self._aiohttp_app.router.add_get("/wecom/kf/health", self._handle_health)
            self._aiohttp_app.router.add_get(self._config.callback_path, self._handle_verify)
            self._aiohttp_app.router.add_post(self._config.callback_path, self._handle_callback)

            self._runner = web.AppRunner(self._aiohttp_app)
            await self._runner.setup()
            self._site = web.TCPSite(self._runner, self._config.host, self._config.port)
            await self._site.start()

            self._dispatch_task = asyncio.create_task(self._dispatch_loop())
            self._running = True
            logger.info(
                "[WeComKF] HTTP 服务已启动 %s:%d%s",
                self._config.host, self._config.port, self._config.callback_path,
            )
            return True
        except Exception:
            await self._cleanup()
            logger.exception("[WeComKF] 连接失败")
            return False

    async def disconnect(self) -> None:
        """停止 HTTP 服务器并释放资源。"""
        self._running = False
        if self._dispatch_task:
            self._dispatch_task.cancel()
            try:
                await self._dispatch_task
            except asyncio.CancelledError:
                pass
            self._dispatch_task = None
        await self._cleanup()
        logger.info("[WeComKF] 已断开连接")

    async def _cleanup(self) -> None:
        self._site = None
        if self._runner:
            await self._runner.cleanup()
            self._runner = None
        self._aiohttp_app = None
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

    def _check_port_free(self) -> bool:
        try:
            with _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM) as s:
                s.settimeout(1)
                s.connect(("127.0.0.1", self._config.port))
            return False
        except (ConnectionRefusedError, OSError):
            return True

    # ------------------------------------------------------------------
    # 主动发送消息
    # ------------------------------------------------------------------

    async def send(
        self,
        chat_id: str,
        content: str,
        reply_to: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SendResult:
        """向客户发送文本消息。

        chat_id 格式：{open_kfid}:{external_userid}
        """
        parts = chat_id.split(":", 1)
        if len(parts) != 2:
            return SendResult(
                success=False,
                error="chat_id 格式错误，应为 open_kfid:external_userid",
            )
        open_kfid, external_userid = parts
        try:
            token = await self._get_access_token()
            payload: Dict[str, Any] = {
                "touser": external_userid,
                "open_kfid": open_kfid,
                "msgtype": "text",
                "text": {"content": content[:2048]},
            }
            resp = await self._http_client.post(
                f"{WECOM_API_BASE}/kf/send_msg?access_token={token}",
                json=payload,
            )
            data = resp.json()
            if data.get("errcode") != 0:
                logger.warning("[WeComKF] send_msg 失败: %s", data)
                return SendResult(success=False, error=str(data), raw_response=data)
            return SendResult(
                success=True,
                message_id=data.get("msgid"),
                raw_response=data,
            )
        except Exception as exc:
            logger.exception("[WeComKF] send 异常")
            return SendResult(success=False, error=str(exc))

    async def get_chat_info(self, chat_id: str) -> Dict[str, Any]:
        """返回会话基本信息。"""
        parts = chat_id.split(":", 1)
        return {
            "chat_id": chat_id,
            "platform": PLATFORM_NAME,
            "open_kfid": parts[0] if len(parts) == 2 else chat_id,
            "external_userid": parts[1] if len(parts) == 2 else "",
            "type": "dm",
        }

    # ------------------------------------------------------------------
    # HTTP 回调处理（aiohttp）
    # ------------------------------------------------------------------

    async def _handle_health(self, request: web.Request) -> web.Response:
        return web.json_response({"status": "ok", "platform": PLATFORM_NAME})

    async def _handle_verify(self, request: web.Request) -> web.Response:
        """GET — 企业微信回调地址验证。"""
        try:
            crypt = self._make_crypt()
            plain = crypt.verify_url(
                request.query.get("msg_signature", ""),
                request.query.get("timestamp", ""),
                request.query.get("nonce", ""),
                request.query.get("echostr", ""),
            )
            return web.Response(text=plain, content_type="text/plain")
        except Exception as exc:
            logger.warning("[WeComKF] URL 验证失败: %s", exc)
            return web.Response(status=403, text="signature verification failed")

    async def _handle_callback(self, request: web.Request) -> web.Response:
        """POST — 接收 kf_msg_or_event 事件通知，必须 5 秒内响应。"""
        body = await request.text()
        try:
            xml_text = self._decrypt_body(
                body,
                request.query.get("msg_signature", ""),
                request.query.get("timestamp", ""),
                request.query.get("nonce", ""),
            )
            token, open_kfid = self._parse_kf_event(xml_text)
            if token and open_kfid:
                await self._event_queue.put((token, open_kfid))
        except WeComCryptoError as exc:
            logger.warning("[WeComKF] 签名/解密失败: %s", exc)
        except Exception:
            logger.exception("[WeComKF] 处理回调时出错")
        return web.Response(text="", content_type="text/plain")

    # ------------------------------------------------------------------
    # 消息分发循环
    # ------------------------------------------------------------------

    async def _dispatch_loop(self) -> None:
        """后台循环：消费事件队列，拉取并分发消息。"""
        while True:
            token, open_kfid = await self._event_queue.get()
            try:
                await self._sync_and_dispatch(token, open_kfid)
            except Exception:
                logger.exception("[WeComKF] sync_and_dispatch 异常 kfid=%s", open_kfid)

    async def _sync_and_dispatch(self, callback_token: str, open_kfid: str) -> None:
        """调用 sync_msg 拉取消息并逐条分发给业务处理器。"""
        access_token = await self._get_access_token()
        cursor = self._cursors.get(open_kfid, "")
        has_more = True

        while has_more:
            payload: Dict[str, Any] = {
                "token": callback_token,
                "limit": SYNC_MSG_LIMIT,
                "open_kfid": open_kfid,
            }
            if cursor:
                payload["cursor"] = cursor

            try:
                resp = await self._http_client.post(
                    f"{WECOM_API_BASE}/kf/sync_msg?access_token={access_token}",
                    json=payload,
                )
                data = resp.json()
            except Exception as exc:
                logger.error("[WeComKF] sync_msg 请求失败: %s", exc)
                break

            if data.get("errcode") != 0:
                logger.warning("[WeComKF] sync_msg 返回错误: %s", data)
                break

            msg_list: List[Dict[str, Any]] = data.get("msg_list") or []
            next_cursor: str = data.get("next_cursor", "")
            has_more = bool(data.get("has_more"))

            for raw_msg in msg_list:
                event = self._build_event(raw_msg)
                if event is None:
                    continue
                if self._is_duplicate(event):
                    logger.debug("[WeComKF] 重复消息跳过 msgid=%s", event.message_id)
                    continue
                self._record_seen(event)
                asyncio.create_task(self.handle_message(event))

            if next_cursor:
                cursor = next_cursor
                self._cursors[open_kfid] = cursor

            # callback_token 只用第一次，后续续拉不传
            callback_token = ""

    # ------------------------------------------------------------------
    # 消息构建
    # ------------------------------------------------------------------

    def _build_event(self, raw: Dict[str, Any]) -> Optional[MessageEvent]:
        """将 sync_msg 返回的单条消息转换为 MessageEvent。

        origin=3 客户消息，origin=4 系统推送事件。
        """
        origin: int = raw.get("origin", 0)
        if origin not in (3, 4):
            return None

        msgtype: str = (raw.get("msgtype") or "").lower()
        open_kfid: str = raw.get("open_kfid", "")
        external_userid: str = raw.get("external_userid", "")
        msgid: str = raw.get("msgid", "")
        chat_id = f"{open_kfid}:{external_userid}"

        source = self.build_source(
            chat_id=chat_id,
            chat_name=external_userid,
            chat_type="dm",
            user_id=external_userid,
            user_name=external_userid,
        )

        # 文本消息
        if msgtype == "text":
            text_obj = raw.get("text") or {}
            content = text_obj.get("content", "").strip()
            return MessageEvent(
                text=content,
                message_type=MessageType.TEXT,
                source=source,
                raw_message=raw,
                message_id=msgid,
            )

        # 图片 / 语音 / 视频 / 文件
        if msgtype in ("image", "voice", "video", "file"):
            media_obj = raw.get(msgtype) or {}
            media_id = media_obj.get("media_id", "")
            type_map = {
                "image": MessageType.IMAGE,
                "voice": MessageType.VOICE,
                "video": MessageType.VIDEO,
                "file": MessageType.FILE,
            }
            return MessageEvent(
                text=f"[{msgtype}:{media_id}]",
                message_type=type_map[msgtype],
                source=source,
                raw_message=raw,
                message_id=msgid,
            )

        # 位置消息
        if msgtype == "location":
            loc = raw.get("location") or {}
            text = (
                f"[位置] {loc.get('name', '')} "
                f"({loc.get('latitude', 0)}, {loc.get('longitude', 0)}) "
                f"{loc.get('address', '')}"
            ).strip()
            return MessageEvent(
                text=text,
                message_type=MessageType.TEXT,
                source=source,
                raw_message=raw,
                message_id=msgid,
            )

        # 事件消息
        if msgtype == "event":
            event_obj = raw.get("event") or {}
            event_type = event_obj.get("event_type", "")
            if event_type == "enter_session":
                return MessageEvent(
                    text="/start",
                    message_type=MessageType.EVENT,
                    source=source,
                    raw_message=raw,
                    message_id=msgid or f"enter_{external_userid}_{int(time.time())}",
                )
            logger.debug("[WeComKF] 系统事件已忽略 event_type=%s", event_type)
            return None

        logger.debug("[WeComKF] 暂不支持的消息类型: %s", msgtype)
        return None

    # ------------------------------------------------------------------
    # XML 解析
    # ------------------------------------------------------------------

    def _decrypt_body(
        self, body: str, msg_signature: str, timestamp: str, nonce: str
    ) -> str:
        root = ET.fromstring(body)
        encrypt = root.findtext("Encrypt", default="")
        crypt = self._make_crypt()
        return crypt.decrypt(msg_signature, timestamp, nonce, encrypt).decode("utf-8")

    @staticmethod
    def _parse_kf_event(xml_text: str) -> tuple:
        """从解密后的 XML 中提取 Token 和 OpenKfId。"""
        root = ET.fromstring(xml_text)
        event = (root.findtext("Event") or "").lower()
        if event != "kf_msg_or_event":
            return "", ""
        token = root.findtext("Token") or ""
        open_kfid = root.findtext("OpenKfId") or ""
        return token, open_kfid

    # ------------------------------------------------------------------
    # 消息去重
    # ------------------------------------------------------------------

    def _is_duplicate(self, event: MessageEvent) -> bool:
        if not event.message_id:
            return False
        now = time.time()
        last = self._seen_messages.get(event.message_id)
        return bool(last and now - last < MESSAGE_DEDUP_TTL_SECONDS)

    def _record_seen(self, event: MessageEvent) -> None:
        if not event.message_id:
            return
        now = time.time()
        self._seen_messages[event.message_id] = now
        if len(self._seen_messages) > 2000:
            cutoff = now - MESSAGE_DEDUP_TTL_SECONDS
            self._seen_messages = {k: v for k, v in self._seen_messages.items() if v > cutoff}

    # ------------------------------------------------------------------
    # Access Token 管理
    # ------------------------------------------------------------------

    async def _get_access_token(self) -> str:
        if self._access_token and time.time() < self._token_expires_at - 60:
            return self._access_token
        return await self._refresh_access_token()

    async def _refresh_access_token(self) -> str:
        resp = await self._http_client.get(
            f"{WECOM_API_BASE}/gettoken",
            params={
                "corpid": self._config.corp_id,
                "corpsecret": self._config.kf_secret,
            },
        )
        data = resp.json()
        if not data.get("access_token"):
            raise RuntimeError(f"微信客服 Access Token 获取失败: {data}")
        self._access_token = data["access_token"]
        expires_in = int(data.get("expires_in", ACCESS_TOKEN_TTL_SECONDS))
        self._token_expires_at = time.time() + expires_in
        logger.info(
            "[WeComKF] Access Token 已刷新，corp=%s，有效期 %ss",
            self._config.corp_id, expires_in,
        )
        return self._access_token

    # ------------------------------------------------------------------
    # 加解密实例
    # ------------------------------------------------------------------

    def _make_crypt(self) -> WXBizMsgCrypt:
        return WXBizMsgCrypt(
            token=self._config.callback_token,
            encoding_aes_key=self._config.encoding_aes_key,
            receive_id=self._config.corp_id,
        )

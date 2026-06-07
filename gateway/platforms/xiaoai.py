"""
小爱音箱平台适配器（免刷机，小米云端 API）。

实现参考 migpt-next 的消息轮询与 TTS 播报逻辑，AI 回复统一走 Gateway call_agent_chat。
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from gateway.base import BasePlatformAdapter, MessageEvent, MessageType, SendResult
from gateway.platforms.xiaoai_miot import (
    ConversationMessage,
    MiNAClient,
    has_xiaoai_config,
    load_xiaoai_config,
    login_mina,
    save_xiaoai_config,
)

logger = logging.getLogger(__name__)


def _timestamp_to_datetime(ts: int) -> Optional[datetime]:
    """小米对话历史的 time 字段为毫秒时间戳，Windows 上不能直接传给 fromtimestamp。"""
    if not ts:
        return None
    try:
        seconds = ts / 1000.0 if ts > 10_000_000_000 else float(ts)
        return datetime.fromtimestamp(seconds)
    except (OSError, OverflowError, ValueError):
        return None


def extract_query_after_keyword(text: str, keywords: List[str]) -> Optional[str]:
    """
    从 ASR 原文中截取触发词之后的内容，再发给 Soulprout。

    例如：「小爱同学，请帮我查天气」+ 触发词「请」→「帮我查天气」
    """
    raw = (text or "").strip()
    if not raw:
        return None
    if not keywords:
        return raw

    best_index = -1
    best_keyword = ""
    for keyword in keywords:
        kw = (keyword or "").strip()
        if not kw:
            continue
        idx = raw.find(kw)
        if idx < 0:
            continue
        if best_index < 0 or idx < best_index or (idx == best_index and len(kw) > len(best_keyword)):
            best_index = idx
            best_keyword = kw

    if best_index < 0:
        return None

    remainder = raw[best_index + len(best_keyword):].strip()
    remainder = remainder.lstrip("，。,.、：:；;！!？? ")
    return remainder or None


class _ConversationPoller:
    """移植 migpt-next apps/next/src/message.ts 的增量拉取逻辑。"""

    def __init__(self, client: MiNAClient):
        self._client = client
        self._last_query_msg: Optional[ConversationMessage] = None
        self._temp_query_msgs: List[ConversationMessage] = []

    async def fetch_next_message(self) -> Optional[ConversationMessage]:
        if self._last_query_msg is None:
            await self._fetch_first_message()
            return None
        return await self._fetch_next_message()

    async def _fetch_first_message(self) -> None:
        msgs = await self._client.get_conversations(limit=1)
        if msgs:
            self._last_query_msg = msgs[0]

    async def _fetch_next_message(self) -> Optional[ConversationMessage]:
        if self._temp_query_msgs:
            return self._pop_temp_message()

        msgs = await self._client.get_conversations(limit=2)
        if not msgs:
            return None

        newest = msgs[0]
        if newest.timestamp <= self._last_query_msg.timestamp:
            return None

        if len(msgs) == 1 or msgs[-1].timestamp <= self._last_query_msg.timestamp:
            self._last_query_msg = newest
            return newest

        for msg in msgs:
            if msg.timestamp > self._last_query_msg.timestamp:
                self._temp_query_msgs.append(msg)
        return await self._fetch_next_remaining_messages()

    async def _fetch_next_remaining_messages(self) -> Optional[ConversationMessage]:
        max_page = 3
        page_size = 10
        current_page = 0
        while current_page < max_page:
            current_page += 1
            if not self._temp_query_msgs:
                return None
            next_timestamp = self._temp_query_msgs[-1].timestamp
            msgs = await self._client.get_conversations(limit=page_size, timestamp=next_timestamp)
            for msg in msgs:
                if msg.timestamp >= next_timestamp:
                    continue
                if msg.timestamp > self._last_query_msg.timestamp:
                    self._temp_query_msgs.append(msg)
                else:
                    return self._pop_temp_message()
        return self._pop_temp_message()

    def _pop_temp_message(self) -> Optional[ConversationMessage]:
        if not self._temp_query_msgs:
            return None
        msg = self._temp_query_msgs.pop()
        self._last_query_msg = msg
        return msg


class XiaoaiAdapter(BasePlatformAdapter):
    def __init__(self) -> None:
        super().__init__("xiaoai")
        self._client: Optional[MiNAClient] = None
        self._poller: Optional[_ConversationPoller] = None
        self._poll_task: Optional[asyncio.Task] = None
        self._chat_id = "default"
        self._device_name = ""
        self._call_ai_keywords: List[str] = ["请", "你"]
        self._heartbeat_ms = 1000
        self._debug = False
        self._last_error = ""
        self._reload_from_disk()

    @property
    def is_connected(self) -> bool:
        return self._running and self._poll_task is not None and not self._poll_task.done()

    @property
    def device_name(self) -> str:
        return self._device_name

    @property
    def last_error(self) -> str:
        return self._last_error

    def _reload_from_disk(self) -> None:
        cfg = load_xiaoai_config() or {}
        self._call_ai_keywords = list(cfg.get("call_ai_keywords") or ["请", "你"])
        self._heartbeat_ms = max(1000, int(cfg.get("heartbeat_ms") or 1000))
        self._debug = bool(cfg.get("debug"))
        self._device_name = str(cfg.get("did") or os.getenv("XIAOMI_DID", "")).strip()

    def reload_credentials(self) -> bool:
        self._reload_from_disk()
        ok = has_xiaoai_config()
        if ok:
            logger.info("[xiaoai] 配置已重新加载 did=%s", self._device_name)
        return ok

    async def connect(self) -> bool:
        if not has_xiaoai_config():
            logger.warning("[xiaoai] 未配置小米账号，可在管理界面 http://localhost:8082/xiaoai 填写")
            return False

        cfg = load_xiaoai_config() or {}
        self._last_error = ""
        try:
            self._client = await login_mina(
                user_id=str(cfg.get("user_id") or ""),
                password=str(cfg.get("password") or ""),
                pass_token=str(cfg.get("pass_token") or ""),
                did=str(cfg.get("did") or ""),
            )
        except Exception as exc:
            self._last_error = str(exc)
            logger.error("[xiaoai] 登录失败: %s", exc, exc_info=True)
            return False

        if self._client is None:
            self._last_error = "小米账号登录失败"
            return False

        self._device_name = self._client.device_name
        self._chat_id = self._client.account.device.device_id if self._client.account.device else cfg.get("did", "default")
        self._poller = _ConversationPoller(self._client)
        self._running = True
        self._poll_task = asyncio.create_task(self._poll_loop(), name="xiaoai-poll")
        logger.info("[xiaoai] 已启动轮询 did=%s device=%s", cfg.get("did"), self._device_name)
        return True

    async def disconnect(self) -> None:
        self._running = False
        task = self._poll_task
        self._poll_task = None
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception:
                pass
        self._client = None
        self._poller = None
        logger.info("[xiaoai] 已断开连接")

    async def send(
        self,
        chat_id: str,
        content: str,
        reply_to: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SendResult:
        if not self._client:
            return SendResult(success=False, error="小爱未连接")
        text = (content or "").strip()
        if not text:
            return SendResult(success=False, error="回复内容为空")
        try:
            ok = await self._client.play_text(text)
            if ok:
                return SendResult(success=True)
            return SendResult(success=False, error="音箱 TTS 播报失败")
        except Exception as exc:
            logger.error("[xiaoai] 播报失败: %s", exc, exc_info=True)
            return SendResult(success=False, error=str(exc))

    async def get_chat_info(self, chat_id: str) -> Dict[str, Any]:
        return {
            "chat_id": chat_id,
            "chat_name": self._device_name or chat_id,
            "chat_type": "dm",
            "platform": self.platform,
        }

    def _prepare_agent_query(self, text: str) -> Optional[str]:
        return extract_query_after_keyword(text, self._call_ai_keywords)

    async def _poll_loop(self) -> None:
        heartbeat = self._heartbeat_ms / 1000.0
        while self._running:
            try:
                if self._poller is None or self._client is None:
                    break
                msg = await self._poller.fetch_next_message()
                if msg and msg.query:
                    agent_query = self._prepare_agent_query(msg.query)
                    if self._debug:
                        logger.info(
                            "[xiaoai] 收到对话 raw=%r agent=%r",
                            msg.query,
                            agent_query,
                        )
                    if agent_query:
                        event = MessageEvent(
                            text=agent_query,
                            source=self.build_source(
                                chat_id=self._chat_id,
                                chat_name=self._device_name,
                                chat_type="dm",
                                user_id=self._chat_id,
                                user_name=self._device_name,
                            ),
                            message_type=MessageType.VOICE,
                            message_id=f"{msg.timestamp}:{msg.query[:32]}",
                            timestamp=_timestamp_to_datetime(msg.timestamp),
                        )
                        await self.handle_message(event)
            except PermissionError:
                self._last_error = "小米登录凭证已过期"
                logger.warning("[xiaoai] 登录凭证过期，尝试重新登录")
                if not await self._relogin():
                    await asyncio.sleep(5)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                self._last_error = str(exc)
                logger.error("[xiaoai] 轮询异常: %s", exc, exc_info=True)
                await asyncio.sleep(3)
            await asyncio.sleep(heartbeat)

    async def _relogin(self) -> bool:
        cfg = load_xiaoai_config() or {}
        try:
            client = await login_mina(
                user_id=str(cfg.get("user_id") or ""),
                password=str(cfg.get("password") or ""),
                pass_token=str(cfg.get("pass_token") or ""),
                did=str(cfg.get("did") or ""),
                relogin=True,
            )
        except Exception as exc:
            self._last_error = str(exc)
            logger.error("[xiaoai] 重新登录失败: %s", exc, exc_info=True)
            return False
        if client is None:
            self._last_error = "重新登录失败"
            return False
        self._client = client
        self._poller = _ConversationPoller(client)
        self._last_error = ""
        logger.info("[xiaoai] 已重新登录")
        return True


def get_public_config() -> Dict[str, Any]:
    cfg = load_xiaoai_config() or {}
    return {
        "user_id": str(cfg.get("user_id") or ""),
        "did": str(cfg.get("did") or ""),
        "has_password": bool(cfg.get("password")),
        "has_pass_token": bool(cfg.get("pass_token")),
        "call_ai_keywords": list(cfg.get("call_ai_keywords") or ["请", "你"]),
        "heartbeat_ms": int(cfg.get("heartbeat_ms") or 1000),
        "debug": bool(cfg.get("debug")),
    }

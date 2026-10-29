"""判断一个会话是不是「本地会话」。

标签在会话创建时由云端写入（桌面端创建 = local，网页端创建 = cloud），之后不变，云端会话库是权威来源。
桌面端这边按这个顺序判断，尽量少打扰云端：

1. 本机记录过的本地会话 ID（覆盖「刚发出第一条消息、云端还没落库」的空档）；
2. 云端会话列表（短时间缓存）里查到的 ``workspace`` 字段；
3. 都查不到 = 全新会话：任务模式下，桌面端新建的会话就是本地会话。
"""

from __future__ import annotations

import logging
import time
from typing import Any, Awaitable, Callable, Dict, List, Optional

from . import settings

logger = logging.getLogger(__name__)

LIST_TTL_S = 20.0

ListFetcher = Callable[[], Awaitable[Optional[List[Dict[str, Any]]]]]


class ConversationRouter:
    def __init__(self, fetch_conversations: ListFetcher):
        self._fetch = fetch_conversations
        self._cloud_known: Dict[str, str] = {}  # conversation_id -> workspace（来自云端列表）
        self._fetched_at = 0.0

    def mark_local(self, conversation_id: str) -> None:
        settings.add_local_conversation(conversation_id)
        self._cloud_known[conversation_id] = "local"

    def forget(self, conversation_id: str) -> None:
        settings.remove_local_conversation(conversation_id)
        self._cloud_known.pop(conversation_id, None)

    def invalidate(self) -> None:
        self._cloud_known.clear()
        self._fetched_at = 0.0

    async def _refresh(self, force: bool = False) -> None:
        if not force and time.monotonic() - self._fetched_at < LIST_TTL_S:
            return
        try:
            items = await self._fetch()
        except Exception as exc:
            logger.warning("获取云端会话列表失败: %s", exc)
            return
        if items is None:
            return
        self._fetched_at = time.monotonic()
        known = {str(it.get("conversation_id")): str(it.get("workspace") or "cloud") for it in items if isinstance(it, dict)}
        # 本机刚创建、云端列表里还没有的本地会话不要被刷新冲掉
        for cid in settings.local_conversations():
            known.setdefault(cid, "local")
        self._cloud_known = known

    async def is_local(self, conversation_id: str, *, creating_ok: bool = False) -> bool:
        """``creating_ok``：会话 ID 在云端查不到时，是否当作「桌面端新建的本地会话」。"""
        cid = (conversation_id or "").strip()
        if not cid:
            return creating_ok
        if cid in settings.local_conversations():
            return True
        if cid in self._cloud_known:
            return self._cloud_known[cid] == "local"
        await self._refresh(force=True)
        if cid in self._cloud_known:
            return self._cloud_known[cid] == "local"
        return creating_ok

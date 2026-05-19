import json
from datetime import datetime

from agent.database.crud.message import (
    save_message,
    get_runtime_history,
)
from agent.database.models.message import AgentMessage
from agent.utils.vdb_client import VDBClient


class Memory:
    """
    记忆模块：负责对话级别的记忆召回与同步。

    - recall: 在用户每一轮输入处理前调用，对 memory_collection 执行 hybrid_search，
      Top-K & score >= 0.4（可通过 MEMORY_RECALL_SCORE 配置）& 排除已在 memory_loaded 中的记忆，
      命中后以 type="memory" / role="user" 的消息写入历史。
    - sync_with_history: compress 之后调用，扫描当前 runtime history 里
      所有 load_memory 工具调用的 name，把 Conversation.memory_loaded 中
      已经被压缩掉、不再出现的记忆移除，便于下一轮重新召回。
    """

    def __init__(self, config, is_sub_agent, session_id, user_id, conversation_id, input_text):
        self.config = config
        self.is_sub_agent = is_sub_agent
        self.session_id = session_id
        self.user_id = user_id
        self.conversation_id = conversation_id
        self.input_text = input_text

        self.vdb_client = VDBClient()
        self.memory_collection = config.memory_collection
        self.top_k = config.memory_recall_top_k
        self.score_threshold = config.memory_recall_score_threshold

    # ─────────────────────────────────────────────────────────────────────────
    # 工具方法
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _escape_filter_value(value: str) -> str:
        """转义 Milvus filter 表达式中的双引号与反斜杠。"""
        return value.replace("\\", "\\\\").replace('"', '\\"')

    async def _get_memory_loaded(self):
        """读取 Conversation.memory_loaded，兼容老数据缺字段的情况。"""
        try:
            conv = await self.config.db_conversation.find_one({"conversation_id": self.conversation_id})
            if not conv:
                return []
            return list(conv.get("memory_loaded") or [])
        except Exception:
            return []

    async def _set_memory_loaded(self, names):
        """写回 Conversation.memory_loaded。"""
        try:
            await self.config.db_conversation.update_one(
                {"conversation_id": self.conversation_id},
                {"$set": {"memory_loaded": list(names), "updated_at": datetime.utcnow()}},
            )
        except Exception as e:
            print(f"Set memory_loaded error: {e}")

    # ─────────────────────────────────────────────────────────────────────────
    # 召回
    # ─────────────────────────────────────────────────────────────────────────

    async def recall(self):
        """
        召回当前 user_id 下与 input_text 相关的记忆。
        命中后写入 message 数据库：type="memory"、role="user"、content="name: ...\\ndescription: ..."。
        """
        if not self.input_text:
            return
        try:
            await self.vdb_client.ensure_collection(self.memory_collection, "memory")
            memory_loaded = await self._get_memory_loaded()
            user_esc = self._escape_filter_value(self.user_id or "")
            results = await self.vdb_client.hybrid_search(
                self.memory_collection,
                query=self.input_text,
                limit=self.top_k,
                filter=f'user_id == "{user_esc}"',
                output_fields=["name", "description"],
            )
            for i, item in enumerate(results[:5], start=1):
                print(
                    f"[Memory recall] top{i}: score={item.get('_score')}, "
                    f"name={item.get('name')}, description={item.get('description') or ''}"
                )
            for item in results:
                name = item.get("name")
                if not name or name in memory_loaded:
                    continue
                score = item.get("_score")
                if score is None or score < self.score_threshold:
                    continue
                description = item.get("description") or ""
                content = f"name: {name}\ndescription: {description}"
                await save_message(
                    AgentMessage(
                        user_id=self.user_id,
                        conversation_id=self.conversation_id,
                        type="memory",
                        role="user",
                        content=content,
                        created_at=datetime.utcnow(),
                    ),
                    self.is_sub_agent,
                    self.session_id,
                )
        except Exception as e:
            print(f"Recall memory error: {e}")

    # ─────────────────────────────────────────────────────────────────────────
    # compress 后的一致性同步
    # ─────────────────────────────────────────────────────────────────────────

    async def sync_with_history(self):
        """
        扫描当前 runtime history 中所有 load_memory 工具调用的 name，
        与 Conversation.memory_loaded 求交集；
        被 compress 折叠/截断掉的记忆从 memory_loaded 中移除。
        """
        try:
            memory_loaded = await self._get_memory_loaded()
            if not memory_loaded:
                return
            history = await get_runtime_history(self.is_sub_agent, self.session_id, self.conversation_id)
            loaded_in_history = set()
            for msg in history:
                tool_calls = getattr(msg, "tool_calls", None) or []
                for tc in tool_calls:
                    fn = None
                    if isinstance(tc, dict):
                        fn = tc.get("function") or {}
                    else:
                        raw_fn = getattr(tc, "function", None)
                        if raw_fn is not None:
                            fn = {
                                "name": getattr(raw_fn, "name", None),
                                "arguments": getattr(raw_fn, "arguments", None),
                            }
                    if not fn or fn.get("name") != "load_memory":
                        continue
                    raw_args = fn.get("arguments")
                    if not raw_args:
                        continue
                    try:
                        args = json.loads(raw_args) if isinstance(raw_args, str) else dict(raw_args)
                    except Exception:
                        continue
                    name = args.get("name")
                    if name:
                        loaded_in_history.add(name)
            kept = [name for name in memory_loaded if name in loaded_in_history]
            if kept != memory_loaded:
                await self._set_memory_loaded(kept)
        except Exception as e:
            print(f"Sync memory_loaded error: {e}")

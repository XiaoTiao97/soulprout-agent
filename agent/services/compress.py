import json
import ast
import logging
import re
from datetime import datetime
from agent.utils.llm import LLM
from agent.api.models.message import ModelConfig
from agent.database.models.message import AgentMessage
from agent.services import prompt
from agent.services.memory import Memory
from agent.database.crud.message import (
    save_message,
    get_runtime_history,
    delete_runtime_messages
)

# 兼容模型返回 ObjectId('xxx') / ObjectId("xxx")，统一成纯 hex 字符串
logger = logging.getLogger(__name__)

_OBJECT_ID_RE = re.compile(
    r"""^\s*ObjectId\s*\(\s*['"]([0-9a-fA-F]{24})['"]\s*\)\s*$"""
)


def _normalize_message_id(value) -> str:
    if value is None:
        return ""
    s = str(value).strip()
    m = _OBJECT_ID_RE.match(s)
    if m:
        return m.group(1)
    return s


class Compress:
    def __init__(self, config, is_sub_agent, session_id, user_id, conversation_id, model):
        self.history = None
        self.context_window = None
        self.config = config
        self.is_sub_agent = is_sub_agent
        self.session_id = session_id
        self.user_id = user_id
        self.conversation_id = conversation_id
        self.model = model

    async def collapse(self):
        logger.info("[compress.collapse] 开始, 历史消息数=%s", len(self.history or []))
        history = []
        for item in self.history:
            if item.role != "agent":
                item_dict = {
                    # 传纯 hex，避免模型照抄 ObjectId('...')
                    'id': _normalize_message_id(item.id),
                    'role': item.role,
                    'content': item.content,
                    **({'tool_calls': item.tool_calls} if hasattr(item, 'tool_calls') and item.tool_calls is not None else {}),
                    **({'tool_call_id': item.tool_call_id} if hasattr(item, 'tool_call_id') and item.tool_call_id is not None else {})
                }
                history.append(item_dict)

        # 限制最大压缩次数
        retries = 3
        collapse_list = []
        last_error = None
        while retries > 0:
            try:
                logger.info("[compress.collapse] 调用 collapse 模型, 剩余重试=%s", retries)
                model_config = ModelConfig(model_source=self.config.collapse_model_source,
                                           model=self.config.collapse_model,
                                           tools=[], stream=False)
                message = [{"role": "system", "content": prompt.COLLAPSE_PROMPT}]
                message.append({"role": "user", "content": f"Complete history：<{history}>. Now start."})
                collapse_list_str = await LLM(self.config).chat_no_stream(message, model_config)
                logger.info("[compress.collapse] 模型原始返回(前500字): %s", str(collapse_list_str)[:500])
                collapse_list = ast.literal_eval(collapse_list_str)
                logger.info(
                    "[compress.collapse] 解析结果条数=%s",
                    len(collapse_list) if isinstance(collapse_list, list) else "非list",
                )
                retries = -1
            except Exception as e:
                last_error = e
                logger.warning("[compress.collapse] 解析失败, 剩余重试=%s, error=%s", retries - 1, e)
                retries -= 1

        if len(collapse_list) == 0:
            logger.error("[compress.collapse] 失败: collapse_list 为空, %s", last_error)
            return False

        try:
            for collapse_dict in collapse_list:
                start_id = _normalize_message_id(collapse_dict.get('start_id'))
                end_id = _normalize_message_id(collapse_dict.get('end_id'))
                collapse_content = collapse_dict.get('collapse_content')
                logger.info(
                    "[compress.collapse] 处理区间 start_id=%s, end_id=%s, summary_len=%s",
                    start_id,
                    end_id,
                    len(str(collapse_content or "")),
                )

                collapse_state = False
                created_at = None
                collapse_id_list = []
                for item in self.history:
                    if item.role != "agent":
                        item_id_str = _normalize_message_id(item.id)
                        if item_id_str == start_id:
                            created_at = item.created_at
                            collapse_state = True
                        if collapse_state:
                            collapse_id_list.append(item.id)
                        if item_id_str == end_id:
                            collapse_state = False

                if not collapse_id_list:
                    logger.error("[compress.collapse] 失败: start_id/end_id 未匹配, start_id=%s, end_id=%s", start_id, end_id)
                    return False

                logger.info("[compress.collapse] 将删除消息数=%s, created_at=%s", len(collapse_id_list), created_at)

                if created_at is None:
                    created_at = datetime.utcnow()

                await delete_runtime_messages(self.is_sub_agent, collapse_id_list)
                await save_message(AgentMessage(user_id=self.user_id, conversation_id=self.conversation_id, type="text", role="assistant",
                                        content=f"The intermediate steps of this conversation have been collapsed, with the collapsed summary being: {collapse_content}", created_at=created_at),
                                       self.is_sub_agent, self.session_id)
                logger.info("[compress.collapse] 成功")
                return True
        except Exception:
            logger.exception("[compress.collapse] 失败")
            return False

    async def compact(self):
        logger.info("[compress.compact] 开始, 历史消息数=%s, context_window=%s", len(self.history or []), self.context_window)
        if not self.context_window:
            logger.info("[compress.compact] 跳过: context_window 未知")
            return False
        tokens = 0
        compact_point = False
        _id_list = []
        history_compact = []
        for item in reversed(self.history):
            if item.role != "agent":
                item_dict = {
                    'role': item.role,
                    'content': item.content,
                    **({'tool_calls': item.tool_calls} if hasattr(item, 'tool_calls') and item.tool_calls is not None else {}),
                    **({'tool_call_id': item.tool_call_id} if hasattr(item, 'tool_call_id') and item.tool_call_id is not None else {})
                }
                tokens += len(str(item_dict)) / 2
                if compact_point:
                    _id_list.append(item.id)
                    history_compact.insert(0, {
                        'role': item.role,
                        'content': item.content,
                        **({'tool_calls': item.tool_calls} if hasattr(item, 'tool_calls') and item.tool_calls is not None else {}),
                        **({'tool_call_id': item.tool_call_id} if hasattr(item, 'tool_call_id') and item.tool_call_id is not None else {})
                    })
                if tokens > 0.5 * self.context_window and item.role == "assistant":
                    logger.info("[compress.compact] 识别到压缩分界点, tokens=%s, 阈值=%s", tokens, 0.5 * self.context_window)
                    compact_point = True

        if not compact_point:
            logger.info("[compress.compact] 未找到分界点, tokens=%s, 阈值=%s", tokens, 0.5 * self.context_window)
        logger.info("[compress.compact] 待压缩消息数=%s, 待摘要消息数=%s", len(_id_list), len(history_compact))

        if not _id_list:
            logger.info("[compress.compact] 跳过: 无消息可删除")
            return False

        create_time = self.history[0].created_at

        # 限制最大压缩次数
        retries = 3
        last_error = None
        while retries > 0:
            try:
                logger.info("[compress.compact] 调用 compact 模型, 剩余重试=%s", retries)
                model_config = ModelConfig(model_source=self.config.compact_model_source, model=self.config.compact_model,
                                           tools=[], stream=False)
                message = [{"role": "system", "content": prompt.COMPACT_PROMPT}]
                message.append({"role": "user", "content": f"Complete Content：<{history_compact}>. Now output the summary content of this conversation"})
                abstract = await LLM(self.config).chat_no_stream(message, model_config)
                logger.info("[compress.compact] 摘要(前300字): %s", str(abstract)[:300])
                await delete_runtime_messages(self.is_sub_agent, _id_list)
                await save_message(AgentMessage(user_id=self.user_id, conversation_id=self.conversation_id, type="text", role="assistant",
                                 content=f"历史消息总结：{abstract}", created_at=create_time), self.is_sub_agent, self.session_id)
                logger.info("[compress.compact] 成功, 已删除消息数=%s", len(_id_list))
                retries = -1
            except Exception as e:
                last_error = e
                logger.warning("[compress.compact] 失败, 剩余重试=%s, error=%s", retries - 1, e)
                retries -= 1
        if retries != -1:
            logger.error("[compress.compact] 最终失败: %s", last_error)
        return True if retries == -1 else False

    async def history_token_check(self):
        self.history = await get_runtime_history(self.is_sub_agent, self.session_id, self.conversation_id)
        history_list = [
            {
                'role': item.role,
                'content': item.content if isinstance(item.content, str) else "",
                **({'tool_calls': item.tool_calls} if hasattr(item,
                                                              'tool_calls') and item.tool_calls is not None else {}),
                **({'tool_call_id': item.tool_call_id} if hasattr(item,
                                                                  'tool_call_id') and item.tool_call_id is not None else {})
            }
            for item in self.history if item.role != "agent"
        ]

        history_token = len(str(history_list)) / 2
        return history_token

    async def _sync_memory_after_compress(self):
        """compress（collapse 或 compact）成功后，同步 Conversation.memory_loaded。"""
        try:
            memory = Memory(
                self.config,
                self.is_sub_agent,
                self.session_id,
                self.user_id,
                self.conversation_id,
                "",
            )
            await memory.sync_with_history()
        except Exception:
            logger.exception("sync memory after compress error")

    def _resolve_context_window(self):
        """
        从 models_info_list 解析当前模型的 context_window。
        支持精确匹配，以及去掉/补上 -thinking 后缀的回退；都找不到则用默认值。
        """
        default_window = 128000
        model_name = (self.model or "").strip()
        if not model_name:
            return default_window

        candidates = [model_name]
        if model_name.endswith("-thinking"):
            candidates.append(model_name[: -len("-thinking")])
        else:
            candidates.append(f"{model_name}-thinking")

        for candidate in candidates:
            for source in self.config.models_info_list or []:
                for model in source.get("models") or []:
                    if model.get("name") != candidate:
                        continue
                    window = model.get("context_window")
                    if isinstance(window, (int, float)) and window > 0:
                        return int(window)
        logger.warning(
            "[compress] 未找到模型 %r 的 context_window，使用默认值 %s",
            model_name,
            default_window,
        )
        return default_window

    async def run(self, force=False):
        logger.info("[compress.run] 开始 force=%s, conversation_id=%s, model=%s", force, self.conversation_id, self.model)
        self.context_window = self._resolve_context_window()
        logger.info("[compress.run] 模型最大长度(context_window)=%s", self.context_window)
        history_token = await self.history_token_check()
        logger.info("[compress.run] token估计=%s, 80%%阈值=%s", history_token, 0.8 * self.context_window)
        if not force and history_token <= 0.8 * self.context_window:
            logger.info("[compress.run] 跳过压缩: 未达 80%% 阈值且 force=False, 直接返回 True")
            return True

        logger.info("[compress.run] 启动压缩, force=%s", force)

        # 优先collapse折叠压缩
        collapse_ok = await self.collapse()
        logger.info("[compress.run] collapse 结果=%s", collapse_ok)

        # 重新检查collapse折叠情况
        history_token = await self.history_token_check()
        logger.info("[compress.run] collapse 后 token估计=%s, 60%%阈值=%s", history_token, 0.6 * self.context_window)

        # collapse 成功且总上下文小于60%：直接结束，并同步 memory_loaded
        if collapse_ok and history_token < 0.6 * self.context_window:
            logger.info("[compress.run] collapse 已足够, 结束")
            await self._sync_memory_after_compress()
            return True

        # 否则启动compact压缩；compact 成功后同步 memory_loaded
        logger.info("[compress.run] collapse 不足或未成功, 进入 compact")
        compact_ok = await self.compact()
        logger.info("[compress.run] compact 结果=%s, 最终返回=%s", compact_ok, compact_ok)
        if compact_ok:
            await self._sync_memory_after_compress()
        return compact_ok

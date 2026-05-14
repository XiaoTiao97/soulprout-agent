import json
import ast
from agent.utils.llm import LLM
from agent.api.models.message import ModelConfig
from agent.database.models.message import AgentMessage
from agent.services import prompt
from agent.database.crud.message import (
    save_message,
    get_runtime_history,
    delete_runtime_messages
)

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
        history = []
        for item in self.history:
            if item.role != "agent":
                item_dict = {
                    'id': item.id,
                    'role': item.role,
                    'content': item.content,
                    **({'tool_calls': item.tool_calls} if hasattr(item, 'tool_calls') and item.tool_calls is not None else {}),
                    **({'tool_call_id': item.tool_call_id} if hasattr(item, 'tool_call_id') and item.tool_call_id is not None else {})
                }
                history.append(item_dict)

        # 限制最大压缩次数
        retries = 3
        collapse_list = []
        collapse_error = None
        while retries > 0:
            try:
                collapse_model_source = self.config.collapse_model_source + "_no_stream"
                model_config = ModelConfig(model_source=collapse_model_source,
                                           model=self.config.collapse_model,
                                           tools=[], stream=False)
                message = [{"role": "system", "content": prompt.COLLAPSE_PROMPT}]
                message.append({"role": "user", "content": f"Complete history：<{history}>. Now start."})
                llm = getattr(LLM(self.config), model_config.model_source)
                collapse_list_str = await llm(message, model_config)
                collapse_list = ast.literal_eval(collapse_list_str)
                retries = -1
            except Exception as collapse_error:
                retries -= 1

        if len(collapse_list) == 0:
            print("collapse error:", collapse_error)
            return False

        try:
            for collapse_dict in collapse_list:
                start_id = collapse_dict.get('start_id')
                end_id = collapse_dict.get('end_id')
                collapse_content = collapse_dict.get('collapse_content')

                collapse_state = False
                created_at = None
                collapse_id_list = []
                for item in self.history:
                    if item.role != "agent":
                        if item.id == start_id:
                            created_at = item.created_at
                            collapse_state = True
                        if collapse_state:
                            collapse_id_list.append(item.id)
                        if item.id == end_id:
                            collapse_state = False

                await delete_runtime_messages(self.is_sub_agent, collapse_id_list)
                await save_message(AgentMessage(user_id=self.user_id, conversation_id=self.conversation_id, type="text", role="assistant",
                                        content=f"The intermediate steps of this conversation have been collapsed, with the collapsed summary being: {collapse_content}", created_at=created_at),
                                       self.is_sub_agent, self.session_id)
                return True
        except Exception as collapse_error:
            print("collapse error:", collapse_error)
            return False

    async def compact(self):
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
                    print("识别到压缩分界点: ", item_dict)
                    compact_point = True

        create_time = self.history[0].created_at

        # 限制最大压缩次数
        retries = 3
        while retries > 0:
            try:
                short_memory_model_source = self.config.short_memory_model_source + "_no_stream"
                model_config = ModelConfig(model_source=short_memory_model_source, model=self.config.short_memory_model,
                                           tools=[], stream=False)
                message = [{"role": "system", "content": prompt.COMPACT_PROMPT}]
                message.append({"role": "user", "content": f"Complete Content：<{history_compact}>. Now output the summary content of this conversation"})
                llm = getattr(LLM(self.config), model_config.model_source)
                abstract = await llm(message, model_config)
                print(abstract)
                await delete_runtime_messages(self.is_sub_agent, _id_list)
                await save_message(AgentMessage(user_id=self.user_id, conversation_id=self.conversation_id, type="text", role="assistant",
                                 content=f"历史消息总结：{abstract}", created_at=create_time), self.is_sub_agent, self.session_id)
                retries = -1
            except Exception as e:
                retries -= 1
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

    async def run(self):
        self.context_window = next(
            (model.get("context_window")
             for source in self.config.models_info_list
             for model in source.get("models", [])
             if model.get("name") == self.model),
             None  # 默认值
        )
        print(f"模型最大长度：{self.context_window}")
        history_token = await self.history_token_check()
        print("token估计: ", history_token)
        if history_token > 0.8 * self.context_window:
            print(f"{history_token}大于预设值{0.8 * self.context_window}，启动压缩")

            # 优先collapse折叠压缩
            result = await self.collapse()

            # 重新检查collapse折叠情况
            history_token = await self.history_token_check()
            print("token估计: ", history_token)

            # 如果collapse成功且总上下文小于60%，则返回，否则启动compact压缩
            return True if result and history_token < 0.6 * self.context_window else await self.compact()
        else:
            return True
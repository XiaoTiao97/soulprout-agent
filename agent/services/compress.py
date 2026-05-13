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
    def __init__(self, history, context_window, config, is_sub_agent, session_id, user_id, conversation_id):
        self.history = history
        self.context_window = context_window
        self.config = config
        self.is_sub_agent = is_sub_agent
        self.session_id = session_id
        self.user_id = user_id
        self.conversation_id = conversation_id

    async def collapse(self):
        return False

    async def compact(self):
        tokens = 0
        compact_point = False
        _id_list = []
        history_memory = []
        for item in reversed(self.history):
            if item.role != "agent":
                item_dict = {
                    'role': item.role,
                    'content': item.content,
                    **({'tool_calls': item.tool_calls} if hasattr(item,
                                                                  'tool_calls') and item.tool_calls is not None else {}),
                    **({'tool_call_id': item.tool_call_id} if hasattr(item,
                                                                      'tool_call_id') and item.tool_call_id is not None else {})
                }
                tokens += len(str(item_dict)) / 2
                if compact_point:
                    _id_list.append(item.id)
                    history_memory.insert(0, {
                        'role': item.role,
                        'content': item.content,
                        **({'tool_calls': item.tool_calls} if hasattr(item,
                                                                      'tool_calls') and item.tool_calls is not None else {}),
                        **({'tool_call_id': item.tool_call_id} if hasattr(item,
                                                                          'tool_call_id') and item.tool_call_id is not None else {})
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
                message = [{"role": "system", "content": prompt.COMPRESS_PROMPT}]
                message.append({"role": "user",
                                "content": f"Complete Content：<{history_memory}>. Now output the summary content of this conversation"})
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

    async def run(self):
        result = await self.collapse()
        if result:
            return True
        else:
            return await self.compact()
import shutil
from aiofiles import os
from agent.database.models.message import AgentMessage, COTMessage, SubAgentMessage
from agent.core.config import Config
config = Config()

async def create_message(data: AgentMessage):
    return await data.insert()

async def create_sub_agent_message(data: SubAgentMessage):
    return await data.insert()

async def get_message_by_conv_id(conversation_id: str):
    return await AgentMessage.find(AgentMessage.conversation_id == conversation_id).sort("created_at").to_list()

async def get_sub_agent_message_by_conv_id(conversation_id: str):
    return await SubAgentMessage.find(SubAgentMessage.conversation_id == conversation_id).sort("created_at").to_list()

async def get_sub_agent_message_by_conv_id_name(conversation_id: str, session_id: str):
    return await SubAgentMessage.find(
        {"$and": [
            {"conversation_id": conversation_id},
            {"session_id": session_id},
        ]}
    ).sort("created_at").to_list()

async def update_tool_message_by_tool_call_id(
        conversation_id: str,
        tool_call_id: str,
        new_content: str
):
    """
    根据 conversation_id 和 tool_call_id更新 role=tool 的消息内容

    Args:
        conversation_id: 会话ID
        tool_call_id: 工具调用ID
        new_content: 新的内容
    """
    # 1. 找到匹配条件的消息
    message = await AgentMessage.find_one(
        AgentMessage.conversation_id == conversation_id,
        AgentMessage.tool_call_id == tool_call_id,
        AgentMessage.role == "tool"
    )

    # 2. 如果找到了消息，更新内容
    if message:
        message.content = new_content
        await message.save()
        return message
    else:
        # 如果没有找到，可以返回None或者抛出异常
        return None


def _extract_tool_call_function_name(tool_call) -> str | None:
    """从 tool_call 项（dict 或 pydantic）中提取 function.name。"""
    if isinstance(tool_call, dict):
        fn = tool_call.get("function") or {}
        if isinstance(fn, dict):
            return fn.get("name")
        return getattr(fn, "name", None)
    fn = getattr(tool_call, "function", None)
    if fn is None:
        return None
    if isinstance(fn, dict):
        return fn.get("name")
    return getattr(fn, "name", None)


def _extract_tool_call_id(tool_call) -> str | None:
    if isinstance(tool_call, dict):
        return tool_call.get("id")
    return getattr(tool_call, "id", None)


async def replace_tool_results_by_function_name(
        conversation_id: str,
        function_name: str,
        new_content: str,
) -> int:
    """
    将历史中所有由 `function_name` 工具产生的 role=tool 消息内容替换为 new_content。

    实现：
        1. 在 agent_messages 与 sub_agent_messages 两个集合中查找该 conversation_id 下
           assistant 消息里 tool_calls.function.name == function_name 的所有 tool_call.id；
        2. 把对应集合中 role=tool 且 tool_call_id 命中的消息 content 替换为 new_content。

    Returns:
        被更新的工具结果消息数量（两个集合之和）。
    """
    updated = 0
    for model in (AgentMessage, SubAgentMessage):
        history = await model.find(model.conversation_id == conversation_id).to_list()
        target_ids: set[str] = set()
        for msg in history:
            if not getattr(msg, "tool_calls", None):
                continue
            for tc in msg.tool_calls:
                if _extract_tool_call_function_name(tc) == function_name:
                    tc_id = _extract_tool_call_id(tc)
                    if tc_id:
                        target_ids.add(tc_id)
        if not target_ids:
            continue
        for msg in history:
            if msg.role != "tool":
                continue
            if not getattr(msg, "tool_call_id", None):
                continue
            if msg.tool_call_id in target_ids and msg.content != new_content:
                msg.content = new_content
                await msg.save()
                updated += 1
    return updated

async def delete_message_by_conv_id(conversation_id: str):
    return await AgentMessage.find(AgentMessage.conversation_id == conversation_id).delete()

async def delete_sub_agent_message_by_conv_id(conversation_id: str):
    return await SubAgentMessage.find(SubAgentMessage.conversation_id == conversation_id).delete()

async def delete_messages_by_ids(message_ids: list[str]):
    """
    根据_id列表删除消息
    :param message_ids: 消息_id的列表
    :return: 删除结果
    """
    # 方法1: 使用in_操作符批量删除
    # return await AgentMessage.find(AgentMessage._id.in_(message_ids)).delete()

    # 或者方法2: 如果in_操作符不支持，可以循环删除
    for message_id in message_ids:
        await AgentMessage.find(AgentMessage.id == message_id).delete()

async def delete_sub_agent_messages_by_ids(message_ids: list[str]):
    for message_id in message_ids:
        await SubAgentMessage.find(SubAgentMessage.id == message_id).delete()

async def create_cot_message(data: COTMessage):
    return await data.insert()

async def get_cot_message_by_conv_id(conversation_id: str):
    return await COTMessage.find(COTMessage.conversation_id == conversation_id).sort("created_at").to_list()

async def delete_cot_message_by_conv_id(conversation_id: str):
    return await COTMessage.find(COTMessage.conversation_id == conversation_id).delete()

async def delete_local_files(conversation_id: str):
    local_file_path = config.local_file_path + conversation_id
    if await os.path.exists(local_file_path):
        shutil.rmtree(local_file_path)
    return None

async def save_message(data, is_sub_agent, session_id):
    if is_sub_agent:
        payload = data.model_dump(exclude={"id"}, exclude_none=True)
        payload["session_id"] = session_id
        return await create_sub_agent_message(SubAgentMessage(**payload))
    else:
        return await create_message(data)

async def get_runtime_history(is_sub_agent, session_id, conversation_id):
    if is_sub_agent:
        return await get_sub_agent_message_by_conv_id_name(conversation_id, session_id)
    return await get_message_by_conv_id(conversation_id)

async def delete_runtime_messages(is_sub_agent, message_ids):
    if is_sub_agent:
        return await delete_sub_agent_messages_by_ids(message_ids)
    return await delete_messages_by_ids(message_ids)
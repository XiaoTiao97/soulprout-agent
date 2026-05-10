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
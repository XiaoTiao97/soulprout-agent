from datetime import datetime
from typing import Union, List

from agent.database.models.conversation import Conversation, COTConversation, SubAgentConversation

async def create_conversation(data: Conversation):
    return await data.insert()

async def get_conversations_by_user(user_id: str):
    return await Conversation.find(Conversation.user_id == user_id).sort("-updated_at").to_list()

async def get_conversation_by_id(conversation_id: str):
    return await Conversation.find_one(Conversation.conversation_id == conversation_id)

async def delete_conversation_by_conv(conversation_id: str):
    conversation = await Conversation.find_one(Conversation.conversation_id == conversation_id)
    if conversation:
        return await conversation.delete()
    return None

async def create_sub_agent_conversation(data: SubAgentConversation):
    return await data.insert()

async def get_sub_agent_conversation(conversation_id: str, session_id: str):
    return await SubAgentConversation.find_one(
        SubAgentConversation.conversation_id == conversation_id,
        SubAgentConversation.session_id == session_id,
    )

async def delete_sub_agent_conversation_by_conv(conversation_id: str):
    return await SubAgentConversation.find(SubAgentConversation.conversation_id == conversation_id).delete()

async def update_sub_agent_conversation(
        conversation_id: str,
        session_id: str,
        tools_use: bool,
        kb_use: list,
        model_source: str,
        model: str,
        update_at: datetime,
):
    conversation = await get_sub_agent_conversation(conversation_id, session_id)
    if conversation:
        conversation.tools_use = tools_use
        conversation.kb_use = kb_use
        conversation.model_source = model_source
        conversation.model = model
        conversation.updated_at = update_at
        await conversation.save()
        return conversation
    return None

async def update_conversation_by_conv_for_abstract(conversation_id: str, abstract: str):
    conversation = await Conversation.find_one(Conversation.conversation_id == conversation_id)
    if conversation:
        conversation.abstract = abstract
        await conversation.save()
        return conversation
    return None

async def update_conversation_by_conv_for_tools_and_kb(conversation_id: str, tools_use: bool, skills_use:bool, kb_use: list, agent_use: Union[None, str], agent_id: Union[None, str, List], agent_name: Union[None, str, List], model_source: str, model: str, update_at: datetime):
    conversation = await Conversation.find_one(Conversation.conversation_id == conversation_id)
    if conversation:
        conversation.tools_use = tools_use
        conversation.skills_use = skills_use
        conversation.kb_use = kb_use
        conversation.agent_use = agent_use
        conversation.agent_id = agent_id
        conversation.agent_name = agent_name
        conversation.model_source = model_source
        conversation.model = model
        conversation.updated_at = update_at
        await conversation.save()
        return conversation
    return None

async def create_cot_conversation(data: COTConversation):
    return await data.insert()

async def get_cot_conversations_by_user(user_id: str):
    return await COTConversation.find(COTConversation.user_id == user_id).sort("-updated_at").to_list()

async def delete_cot_conversation_by_conv(cot_conversation_id: str):
    return await COTConversation.find_one(COTConversation.cot_conversation_id == cot_conversation_id).delete()

async def get_cot_conversation_latest_by_conv_id(conversation_id: str):
    results = await COTConversation.find(
        COTConversation.conversation_id == conversation_id
    ).sort("-updated_at").limit(1).to_list()

    return results[0] if results else None
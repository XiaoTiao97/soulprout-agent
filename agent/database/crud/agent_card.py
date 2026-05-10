from datetime import datetime

from agent.database.crud.agent_subscription import create_agent_subscription
from agent.database.models.agent_card import AgentCard
from agent.database.models.agent_subscription import AgentSub


async def create_agent_card(data: AgentCard):
    return await data.insert()


async def get_agent_cards_by_user_agent_description(user_id: str):
    agent_subscription = await AgentSub.find_one(AgentSub.user_id == user_id)
    if not agent_subscription:
        await create_agent_subscription(user_id)
        agent_subscription = await AgentSub.find_one(AgentSub.user_id == user_id)
    agent_card_list = []
    for agent_id_dict in agent_subscription.subscription:
        agent_card = await AgentCard.find_one(AgentCard.agent_id == agent_id_dict.agent_id)
        if agent_card:
            agent_card_list.append(agent_card)
    return agent_card_list


async def get_agent_cards_by_user(user_id: str):
    agent_cards = await AgentCard.find(AgentCard.user_id == user_id).sort("-updated_at").to_list()
    agent_description_cards = await get_agent_cards_by_user_agent_description(user_id)
    default_agent_cards = await AgentCard.find(AgentCard.user_id == "soulprout").to_list()
    agent_cards.extend(agent_description_cards)
    agent_cards.extend(default_agent_cards)
    return agent_cards


async def get_agent_cards_market():
    return await AgentCard.find(AgentCard.public == True).sort("-updated_at").to_list()


async def get_agent_card_by_agent_id(agent_id: str):
    return await AgentCard.find_one(AgentCard.agent_id == agent_id)


async def delete_agent_card_by_agent_id(agent_id: str):
    agent_card = await AgentCard.find_one(AgentCard.agent_id == agent_id)
    if agent_card:
        return await agent_card.delete()
    return None


async def update_agent_card_by_agent_id(agent_id: str, data: AgentCard):
    agent_card = await AgentCard.find_one(AgentCard.agent_id == agent_id)
    if agent_card:
        update_data = data.model_dump(exclude_unset=True)
        update_data["updated_at"] = datetime.utcnow()
        return await agent_card.update({"$set": update_data})
    return None


async def cleanup_agent_subscriptions(agent_id: str):
    return await AgentSub.find(
        {"subscription.agent_id": agent_id}
    ).update_many({
        "$pull": {
            "subscription": {"agent_id": agent_id}
        }
    })


async def correct_agent_public_by_agent_id(agent_id: str, public: bool):
    agent_card = await AgentCard.find_one(AgentCard.agent_id == agent_id)
    if agent_card:
        await cleanup_agent_subscriptions(agent_id)
        await agent_card.set({AgentCard.public: public})
        return agent_card
    return None


async def update_or_create_agent_card_by_agent_id(data: AgentCard):
    agent_card = await AgentCard.find_one(AgentCard.agent_id == data.agent_id)
    if agent_card:
        update_data = data.model_dump(exclude_unset=True)
        update_data["updated_at"] = datetime.utcnow()
        return await agent_card.update({"$set": update_data})
    return await data.insert()

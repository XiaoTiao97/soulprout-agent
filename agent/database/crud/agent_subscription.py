from agent.database.models.agent_card import AgentCard
from agent.database.models.agent_subscription import AgentId, AgentSub


async def create_agent_subscription(user_id):
    data = AgentSub(user_id=user_id, subscription=[])
    return await data.insert()


async def get_agent_subscription_by_user(user_id: str):
    agent_subscription = await AgentSub.find(AgentSub.user_id == user_id).to_list()
    if not agent_subscription:
        await create_agent_subscription(user_id)
        agent_subscription = await AgentSub.find(AgentSub.user_id == user_id).to_list()
    return agent_subscription


async def update_agent_subscription_by_user(user_id, agent_id):
    agent_subscription = await AgentSub.find(AgentSub.user_id == user_id).first_or_none()
    if not agent_subscription:
        agent_subscription = await create_agent_subscription(user_id)
    if not any(sub.agent_id == agent_id for sub in agent_subscription.subscription):
        update_agent_subscription = AgentId(agent_id=agent_id)
        result = await agent_subscription.update({
            "$push": {
                "subscription": update_agent_subscription.model_dump()
            }
        })
        agent_card = await AgentCard.find_one(AgentCard.agent_id == agent_id)
        if agent_card and agent_card.agents:
            for sub_agent_id in agent_card.agents:
                update_agent_subscription = AgentId(agent_id=sub_agent_id)
                await agent_subscription.update({
                    "$push": {
                        "subscription": update_agent_subscription.model_dump()
                    }
                })
        return result
    return None


async def remove_agent_subscription_by_user(user_id, agent_id):
    agent_subscription = await AgentSub.find(AgentSub.user_id == user_id).first_or_none()
    if not agent_subscription:
        return None
    delete_agent_subscription = AgentId(agent_id=agent_id)
    return await agent_subscription.update({
        "$pull": {
            "subscription": delete_agent_subscription.model_dump()
        }
    })

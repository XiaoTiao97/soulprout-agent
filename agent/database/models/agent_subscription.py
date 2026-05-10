from typing import List

from beanie import Document
from pydantic import BaseModel, Field


class AgentId(BaseModel):
    agent_id: str


class AgentSub(Document):
    user_id: str
    subscription: List[AgentId] = Field(default_factory=list)

    class Settings:
        name = "agent_subscription"

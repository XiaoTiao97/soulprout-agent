"""Rokid / 灵珠个人智能体凭证（按用户持久化在主站）。"""

from datetime import datetime

from beanie import Document, Indexed
from pydantic import Field


class RokidCredential(Document):
    """用户在灵珠侧使用的智能体 ID + API Key。"""

    user_id: Indexed(str, unique=True)
    agent_id: Indexed(str, unique=True)
    api_key: Indexed(str, unique=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "rokid_credential"

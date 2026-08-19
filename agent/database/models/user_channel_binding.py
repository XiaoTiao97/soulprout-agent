from datetime import datetime

from beanie import Document
from pydantic import Field
from pymongo import ASCENDING, IndexModel


class UserChannelBinding(Document):
    """用户在各 Gateway 渠道上最后一次会话，供跨渠道定时投递使用。"""

    user_id: str
    channel: str
    chat_id: str
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "user_channel_bindings"
        indexes = [
            IndexModel(
                [("user_id", ASCENDING), ("channel", ASCENDING)],
                name="user_channel_unique",
                unique=True,
            ),
        ]

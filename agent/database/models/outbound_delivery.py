from datetime import datetime
from typing import Optional

from beanie import Document, Indexed
from pydantic import Field
from pymongo import ASCENDING, IndexModel


class OutboundDelivery(Document):
    """待 Gateway 投递的消息。Gateway 离线时入队，上线后经 WebSocket 下发。"""

    delivery_id: Indexed(str, unique=True)
    user_id: str
    task_id: Optional[str] = None
    channel: str
    chat_id: Optional[str] = None
    content: str
    status: str = "pending"
    create_at: datetime = Field(default_factory=datetime.utcnow)
    sent_at: Optional[datetime] = None

    class Settings:
        name = "outbound_deliveries"
        indexes = [
            IndexModel(
                [("user_id", ASCENDING), ("status", ASCENDING), ("create_at", ASCENDING)],
                name="user_status_create_at",
            ),
        ]

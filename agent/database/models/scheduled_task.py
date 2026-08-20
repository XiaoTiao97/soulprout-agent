from datetime import datetime
from typing import List, Optional

from beanie import Document, Indexed
from pydantic import Field
from pymongo import ASCENDING, IndexModel


class ScheduledTask(Document):
    """用户定时任务。调度器只扫 enabled=True 且 next_run_at <= now 的 pending 记录。"""

    task_id: Indexed(str, unique=True)
    user_id: str
    title: str
    instruction: str = ""
    notify_text: str = ""
    kind: str = ""
    timezone: str = "Asia/Shanghai"
    schedule_type: str = "once"
    weekdays: List[int] = Field(default_factory=list)
    run_at_local: str
    next_run_at: datetime
    channel: str = "web"
    chat_id: Optional[str] = None
    conversation_id: Optional[str] = None
    enabled: bool = True
    status: str = "pending"
    last_run_at: Optional[datetime] = None
    last_error: Optional[str] = None
    create_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "scheduled_tasks"
        indexes = [
            IndexModel(
                [("status", ASCENDING), ("next_run_at", ASCENDING)],
                name="status_next_run_at",
            ),
            IndexModel(
                [("user_id", ASCENDING), ("status", ASCENDING), ("next_run_at", ASCENDING)],
                name="user_status_next_run_at",
            ),
        ]

from beanie import Document
from typing import Optional, Union
from datetime import datetime

class AgentMessage(Document):
    user_id: str
    conversation_id: str
    type: str
    role: str = Union["user", "assistant", "tool", "agent"]
    content: Optional[Union[str, list]] = None
    reasoning_content: Optional[Union[str, None]] = None
    created_at: datetime
    tool_call_id: Optional[str] = None
    tool_calls: Optional[list] = None
    table: Optional[dict] = None
    image: Optional[str] = None

    class Settings:
        name = "agent_messages"

class SubAgentMessage(Document):
    user_id: str
    conversation_id: str
    session_id: str = ""
    type: str
    role: str
    content: Optional[Union[str, list]] = None
    reasoning_content: Optional[Union[str, None]] = None
    created_at: datetime
    tool_call_id: Optional[str] = None
    tool_calls: Optional[list] = None
    table: Optional[dict] = None
    image: Optional[str] = None

    class Settings:
        name = "sub_agent_messages"

class COTMessage(Document):
    user_id: str
    conversation_id: str
    type: str
    role: str
    content: Optional[str] = None
    created_at: datetime
    tool_call_id: Optional[str] = None
    tool_calls: Optional[list] = None
    table: Optional[dict] = None
    image: Optional[str] = None

    class Settings:
        name = "cot_messages"

class FeedbackMessage(Document):
    feedback: Optional[str] = None

    class Settings:
        name = "feedback_messages"

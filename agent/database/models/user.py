from beanie import Document
from pydantic import Field

class UserInfo(Document):
    username: str = Field(..., max_length=64)
    user_id: str
    userpwd: str = Field(..., max_length=512)
    agentname: str = Field(default="萌芽", max_length=64)
    agentinfo: str = Field(default="一个真正懂你的智能助手", max_length=512)

    class Settings:
        name = "user_info"


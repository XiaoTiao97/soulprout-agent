from beanie import Document
from pydantic import Field

class UserInfo(Document):
    username: str = Field(..., max_length=64)
    user_id: str
    userpwd: str = Field(..., max_length=512)
    userinfo: str = Field(default="", max_length=1024)
    agentinfo: str = Field(default="", max_length=1024)

    class Settings:
        name = "user_info"

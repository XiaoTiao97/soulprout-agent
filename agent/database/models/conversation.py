from beanie import Document
from pydantic import Field, ConfigDict
from datetime import datetime
from typing import Union, List


class Conversation(Document):
    model_config = ConfigDict(extra="ignore")

    user_id: str = Field(..., description="用户ID")
    conversation_id: str = Field(..., description="会话ID", unique=True)
    abstract: str = Field(..., description="摘要")
    action_blueprint: str = Field(default="", description="最近一次行动蓝图全文，供前端刷新/切换会话时与消息流对齐展示")
    model_source: str = Field(default="deepseek", description="使用的模型来源")
    model: str = Field(default="deepseek-chat", description="使用的模型型号")
    tools_use: bool = Field(..., description="是否使用工具")
    skills_use: bool = Field(default=True, description="是否使用技能")
    kb_use: Union[bool, list] = Field(default_factory=list, description="是否使用知识库")
    agent_use: Union[None, str] = Field(default=None, description="是否使用智能体及类型")
    agent_id: Union[None, str, List] = Field(default=None, description="智能体id")
    agent_name: Union[None, str, List] = Field(default=None, description="智能体名称")
    create_at: datetime = Field(default_factory=datetime.utcnow, description="创建时间")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="更新时间")

    class Settings:
        name = "conversations"  # 对应 MongoDB 集合名，可自定义

class SubAgentConversation(Document):
    user_id: str = Field(..., description="用户ID")
    conversation_id: str = Field(..., description="主会话ID")
    session_id: str = Field(..., description="子智能体会话ID")
    agent_id: str = Field(..., description="子智能体ID")
    agent_name: str = Field(default="", description="子智能体名称")
    abstract: str = Field(default="", description="摘要")
    model_source: str = Field(default="deepseek", description="使用的模型来源")
    model: str = Field(default="deepseek-chat", description="使用的模型型号")
    tools_use: bool = Field(default=True, description="是否使用工具")
    kb_use: Union[bool, list] = Field(default_factory=list, description="是否使用知识库")
    create_at: datetime = Field(default_factory=datetime.utcnow, description="创建时间")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="更新时间")

    class Settings:
        name = "sub_agent_conversations"

class COTConversation(Document):
    user_id: str = Field(..., description="用户ID")
    conversation_id: str = Field(..., description="会话ID", unique=True)
    abstract: str = Field(..., description="摘要")
    create_at: datetime = Field(default_factory=datetime.utcnow, description="创建时间")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="更新时间")

    class Settings:
        name = "cot_conversations"  # 对应 MongoDB 集合名，可自定义
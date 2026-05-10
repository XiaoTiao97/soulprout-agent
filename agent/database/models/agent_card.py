from datetime import datetime
from typing import Any, Dict, List, Literal, Optional, Union

from beanie import Document
from pydantic import Field


class AgentCard(Document):
    user_id: str
    user_name: str = Field(default="")
    agent_id: str
    name: str
    name_zh: Optional[str] = None
    public: bool = Field(default=False)
    description: str
    model_source: str = Field(default="ark", description="模型来源")
    model: str = Field(default="deepseek-v3-1-terminus", description="模型名称")
    system_prompt: str
    supervisor_history: bool = Field(default=True, description="是否继承主智能体历史")
    files: Optional[List[Any]] = Field(default_factory=list)
    tools: Optional[List[str]] = Field(default_factory=list)
    skills: Optional[Dict[Literal["system", "user"], list]] = None
    kbs: Optional[List[str]] = Field(default_factory=list)
    agents: Union[None, List[str]] = None
    announcement: Optional[str] = None
    create_at: datetime = Field(default_factory=datetime.utcnow, description="创建时间")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="更新时间")

    class Settings:
        name = "agent_card"

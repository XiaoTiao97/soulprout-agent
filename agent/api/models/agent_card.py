from pydantic import BaseModel, Field
from typing import Optional, Literal, Dict, List, Any, Union
from datetime import datetime

class AgentCard(BaseModel):
    user_id: str
    user_name: str = ""
    agent_id: str
    name: str
    name_zh: Optional[str] = None
    public: Optional[bool] = False
    description: str
    model_source: str
    model: str
    system_prompt: str
    supervisor_history: bool = True
    files: Optional[List[Any]] = []
    tools: Optional[List[str]] = []
    skills: Optional[Dict[Literal["system", "user"], list]] = None
    kbs: Optional[List[str]] = []
    agents: Union[None, List] = None
    announcement: Optional[str] = None
    create_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
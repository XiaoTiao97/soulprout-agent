from pydantic import BaseModel
from typing import Optional, Literal, Dict, List, Any, Union
from datetime import datetime

class TempSubAgent(BaseModel):
    user_id: str
    agent_id: str
    description: str
    model_source: str
    model: str
    name: str
    system_prompt: Optional[str] = ""
    skills: Optional[Dict[Literal["system", "user"], list]] = None
    tools: Optional[List[str]] = []
    kbs: Optional[List[str]] = []
    files: Optional[List[str]] = []

class ChatRequest(BaseModel):
    model_source: Optional[str] = "deepseek"
    model: Optional[str] = "deepseek-chat"
    message: str
    input_message_id: Optional[str] = None
    user_id: Optional[str] = ""
    conversation_id: Optional[str] = ""
    session_id: Optional[str] = None
    runtime_mode: Optional[str] = "main"
    tools_use: Optional[bool] = True
    kb_use: Optional[List] = []
    agent_use: Union[None, str] = None
    agent_id: Union[None, str, List] = None
    temp_file_path: Union[None, str] = None
    file_name_list: Union[None, List] = None
    user_feedback: Optional[bool] = False
    temp_sub_agent: Optional[TempSubAgent] = None
    class Config:
        extra = "allow"

class ChatResponse(BaseModel):
    conversation_id: str
    user_id: str
    type: str
    role: str = "assistant"
    content: str = ""
    tool_call_id: Optional[str] = ""
    tool_calls: Optional[list] = None
    json_table: Optional[Dict] = None
    image: Optional[str] = None

# 符合数据库的Message类型
class MessageBase(BaseModel):
    user_id: str
    conversation_id: str
    role: str
    content: Optional[str]
    table: Optional[dict] = None
    image: Optional[str] = None
    created_at: datetime
    tool_call_id: Optional[str] = None
    tool_calls: Optional[dict] = None

class MessageCreate(MessageBase):
    pass

class ModelConfig(BaseModel):
    model_source: str
    model: str
    tools: Optional[List] = []
    stream: bool = True

    class Config:
        extra = "allow"

# 符合openai的Message类型
class Message(BaseModel):
    role: str
    content: str = None
    reasoning_content: Optional[Union[str, list]] = None
    id: str = None
    tool_calls: Optional[Any] = None
    tool_call_id: Optional[str] = None

class FileMessage(BaseModel):
    role: str
    type: str = None
    json_table: Optional[Dict] = None

class ReasonMessage(BaseModel):
    role: str
    reasoning_content: Optional[str] = None
    content: Optional[str] = None
    id: str = None
    tool_calls: Optional[Any] = None
    tool_call_id: Optional[str] = None

class CompressTool(BaseModel):
    compress_type: str
    content: str
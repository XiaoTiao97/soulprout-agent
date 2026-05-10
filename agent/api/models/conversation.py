from pydantic import BaseModel, Field
from typing import List, Literal, Optional
from datetime import datetime

class ConversationBase(BaseModel):
    user_id: str
    conversation_id: str
    abstract: str
    create_at: str
    updated_at: str

class ConversationCreate(ConversationBase):
    user_id: str
    conversation_id: str
    abstract: str
    create_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

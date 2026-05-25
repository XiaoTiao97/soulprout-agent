from pydantic import BaseModel
from typing import Optional, List


class ModelConfig(BaseModel):
    model_source: str
    model: str
    tools: Optional[List] = []
    stream: bool = True


class UploadFileResponse(BaseModel):
    success: bool
    message: Optional[str] = ""
    doc_id: Optional[str] = ""

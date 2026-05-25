from pydantic import BaseModel, Field
from typing import List, Any


class ChunkContent(BaseModel):
    chunk_id: str
    content: str


class ChunkModel(BaseModel):
    kb_id: str = Field(..., description="知识库唯一标识符")
    doc_id: str = Field(..., description="文件唯一id")
    chunk_id: str = Field(..., description="chunk的短id")
    content: str


class ChunkItem(BaseModel):
    chunk_id: str = Field(..., description="chunk的短id")
    abstract: str


class DocumentModel(BaseModel):
    kb_id: str = Field(..., description="知识库唯一标识符")
    doc_id: str = Field(..., description="文件唯一id")
    name: str
    description: str
    chunks: List[ChunkItem]


class LibraryModel(BaseModel):
    user_id: str
    kb_id: str = Field(..., description="知识库唯一标识符")
    kb_name_zh: str
    kb_name: str
    kb_description: str
    kb_file_count: int = Field(..., description="文件数")


class FileInfo(BaseModel):
    file_name: str
    file_extension: str
    file_bytes: Any

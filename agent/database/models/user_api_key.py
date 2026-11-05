"""用户自定义大模型 API Key 存储表（信封加密）。"""

from datetime import datetime
from typing import Optional

import pymongo
from beanie import Document
from pydantic import Field
from pymongo import IndexModel


class UserApiKey(Document):
    """
    存储用户按平台（model_source）上传的加密 API Key。

    - (user_id, model_source) 联合唯一索引；
    - 仅保存 AES-256-GCM 信封加密后的 DEK 与密文，以及用于前端回显的脱敏前缀掩码 key_hint；
    - 绝不存储或返回明文 Key。
    """

    user_id: str = Field(..., max_length=64)
    model_source: str = Field(..., max_length=64)
    key_hint: str = Field(..., max_length=32)
    kek_version: int = Field(default=1)
    dek_iv: bytes
    dek_wrapped: bytes
    key_iv: bytes
    key_cipher: bytes
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    last_used_at: Optional[datetime] = None

    class Settings:
        name = "user_api_keys"
        indexes = [
            IndexModel(
                [("user_id", pymongo.ASCENDING), ("model_source", pymongo.ASCENDING)],
                name="user_model_source_unique",
                unique=True,
            ),
        ]

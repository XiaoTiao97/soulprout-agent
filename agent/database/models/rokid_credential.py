"""Rokid / 灵珠个人智能体凭证（按用户持久化在主站，支持信封加密）。"""

from datetime import datetime
from typing import Optional

from beanie import Document, Indexed
from pydantic import Field


class RokidCredential(Document):
    """用户在灵珠侧使用的智能体 ID + API Key（信封加密存储 + SHA-256 哈希索引）。"""

    user_id: Indexed(str, unique=True)
    agent_id: Indexed(str, unique=True)
    # 兼容旧数据：新数据不再存明文 api_key，改用 api_key_hash 做唯一检索 + 信封加密字段存密文
    api_key: Optional[str] = Field(default=None)
    api_key_hash: Optional[Indexed(str)] = Field(default=None)
    kek_version: Optional[int] = Field(default=1)
    dek_iv: Optional[bytes] = Field(default=None)
    dek_wrapped: Optional[bytes] = Field(default=None)
    key_iv: Optional[bytes] = Field(default=None)
    key_cipher: Optional[bytes] = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "rokid_credential"

from typing import Optional

from pydantic import BaseModel, Field


class EmailCodeRequest(BaseModel):
    """请求向指定邮箱发送验证码。"""

    email: str = Field(..., max_length=320)


class EmailLoginRequest(BaseModel):
    """邮箱 + 验证码 一体化登录/注册。

    - ``email``：登录邮箱
    - ``code``：6 位验证码
    - ``username``：可选昵称，仅在该邮箱首次登录（自动注册）时使用
    """

    email: str = Field(..., max_length=320)
    code: str = Field(..., min_length=4, max_length=12)
    username: Optional[str] = Field(default=None, max_length=64)


class SsoTokenRequest(BaseModel):
    """企业 SSO 通过 user_id 免密换取 JWT。"""

    user_id: str = Field(..., max_length=64)
    username: Optional[str] = Field(default=None, max_length=64)

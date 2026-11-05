from typing import Optional

from pydantic import BaseModel, Field


class EmailCodeRequest(BaseModel):
    """请求向指定邮箱发送验证码。"""

    email: str = Field(..., max_length=320)


class EmailLoginRequest(BaseModel):
    """邮箱 + 验证码 一体化登录/注册。

    - ``email``：登录邮箱
    - ``code``：6 位验证码

    用户名不在登录/注册时填写：新用户默认「未命名用户{user_id}」，之后通过对话或「个性化」修改。
    """

    email: str = Field(..., max_length=320)
    code: str = Field(..., min_length=4, max_length=12)


class ProfileUpdateRequest(BaseModel):
    """个性化设置：用户 / 智能体的名字与具体信息。未提供的字段保持不变。"""

    username: Optional[str] = Field(default=None, max_length=64)
    userinfo: Optional[str] = Field(default=None, max_length=1024)
    agentname: Optional[str] = Field(default=None, max_length=64)
    agentinfo: Optional[str] = Field(default=None, max_length=1024)


class SsoTokenRequest(BaseModel):
    """企业 SSO 通过 user_id 免密换取 JWT。"""

    user_id: str = Field(..., max_length=64)


class SaveUserApiKeyRequest(BaseModel):
    """保存单个模型平台的 API Key。"""

    model_source: str = Field(..., max_length=64)
    api_key: str = Field(..., min_length=1, max_length=512)


class UpdateApiKeyPreferencesRequest(BaseModel):
    """更新是否启用自定义 API Key 及指定模型配置。"""

    use_custom_key: bool = False
    custom_soulprout_source: Optional[str] = Field(default=None, max_length=64)
    custom_soulprout_model: Optional[str] = Field(default=None, max_length=128)
    custom_pro_source: Optional[str] = Field(default=None, max_length=64)
    custom_pro_model: Optional[str] = Field(default=None, max_length=128)
    custom_flash_source: Optional[str] = Field(default=None, max_length=64)
    custom_flash_model: Optional[str] = Field(default=None, max_length=128)


from typing import Optional

import pymongo
from beanie import Document, Indexed
from pydantic import Field
from pymongo import IndexModel

from agent.services.prompt import DEFAULT_AGENT_INFO, DEFAULT_AGENT_NAME, DEFAULT_USER_INFO


class UserInfo(Document):
    """
    用户基本信息。

    认证策略调整为「邮箱 + 验证码」一体化登录/注册：

    - ``user_id``：系统内部唯一 ID（注册时自动生成的 7 位数字，可读性较好）。
    - ``email``：用户邮箱，作为登录入口（首次出现的邮箱会自动注册并分配 user_id）。
      旧用户（无邮箱）依旧保留 ``user_id`` 字段，可通过 SSO 入口免密登录。
      该字段使用 ``partialFilterExpression`` 形式的唯一索引：
      允许多条邮箱为 ``null`` 的旧记录共存，仅在邮箱为字符串时强制唯一。
    - ``username``：用户名（智能体对用户的称呼），注册时若未提供则为「未命名用户{user_id}」。
    - ``userinfo``：用户的具体信息（职业、偏好等），不含名字；默认写明用户名为「未命名用户…」时要引导用户提供昵称和信息。
    - ``agentname``：智能体的名字，默认「小芽」。
    - ``agentinfo``：智能体的具体设定（说话方式、定位等），不含名字；默认写明「小芽」只是默认名字。
    """

    user_id: Indexed(str, unique=True)
    username: str = Field(..., max_length=64)
    email: Optional[str] = None
    userinfo: str = Field(default=DEFAULT_USER_INFO, max_length=1024)
    agentname: str = Field(default=DEFAULT_AGENT_NAME, max_length=64)
    agentinfo: str = Field(default=DEFAULT_AGENT_INFO, max_length=1024)

    class Settings:
        name = "user_info"
        indexes = [
            IndexModel(
                [("email", pymongo.ASCENDING)],
                name="email_unique_partial",
                unique=True,
                partialFilterExpression={"email": {"$type": "string"}},
            ),
        ]

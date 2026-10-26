"""
用户认证服务。

认证模型：
1. **邮箱验证码登录/注册一体化**：前端先调用 ``/user/email/send-code`` 获取验证码，
   再调用 ``/user/email/login`` 提交邮箱 + 验证码：
   - 邮箱已注册：直接返回原有用户信息；
   - 邮箱未注册：自动分配一个 7 位数字 ``user_id`` 并创建账号后返回。
2. **企业 SSO 免密登录**：保留 ``/sso-entrance`` 与 ``/user/sso-token`` 两条入口，
   通过 ``user_id`` 直接登录，无需邮箱或密码。
"""

from __future__ import annotations

import random
from typing import Optional, Tuple

from beanie.operators import Eq
from fastapi import HTTPException, Request

from agent.database.crud.conversation import get_conversation_by_id
from agent.database.models.user import UserInfo
from agent.services.email_service import verify_email_code
from agent.services.prompt import default_username
from agent.utils.jwt_utils import verify_token


# ---------------------------------------------------------------------------
# 公共辅助
# ---------------------------------------------------------------------------

async def get_current_user(token: str) -> UserInfo:
    payload = verify_token(token)
    if not payload or "user_id" not in payload:
        raise HTTPException(status_code=401, detail="无效或过期的 token")
    user = await UserInfo.find_one(Eq(UserInfo.user_id, str(payload["user_id"])))
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    return user


async def require_user(request: Request) -> UserInfo:
    """
    从请求中取出当前登录用户，可直接作为 ``Depends(require_user)`` 使用。

    token 来源：Cookie ``token``（网页端）优先，其次 ``Authorization: Bearer``
    （网关、手机 App 等无法依赖 Cookie 的客户端）。
    """
    token = request.cookies.get("token")
    if not token:
        auth = request.headers.get("authorization") or ""
        if auth.lower().startswith("bearer "):
            token = auth[7:].strip()
    if not token:
        raise HTTPException(status_code=401, detail="未登录")
    return await get_current_user(token)


async def ensure_conversation_owner(conversation_id: str, user_id: str) -> None:
    """
    校验会话属于该用户，否则抛 404（不区分“不存在”和“不是你的”，避免被探测）。

    - Soulprout 模式的会话 id 就是 user_id，直接放行（此时库里可能还没有记录）；
    - 其余会话以库中记录的 user_id 为准。
    """
    if conversation_id == user_id:
        return
    conversation = await get_conversation_by_id(conversation_id)
    if conversation is None or conversation.user_id != user_id:
        raise HTTPException(status_code=404, detail="会话不存在")


async def _allocate_user_id() -> str:
    """生成一个未被使用的 7 位数字 user_id。"""
    for _ in range(50):
        candidate = str(random.randint(1000000, 9999999))
        exists = await UserInfo.find_one(Eq(UserInfo.user_id, candidate))
        if not exists:
            return candidate
    raise RuntimeError("无法分配新的 user_id，请稍后再试")


# ---------------------------------------------------------------------------
# 邮箱登录/注册
# ---------------------------------------------------------------------------

async def login_or_register_by_email(
    email: str,
    code: str,
) -> Tuple[Optional[UserInfo], bool, Optional[str]]:
    """
    邮箱验证码一体化登录/注册。

    Returns:
        (user, is_new_user, error_msg)
        - 校验失败：返回 (None, False, "错误描述")
        - 已存在邮箱：返回 (user, False, None)
        - 新邮箱：自动创建后返回 (user, True, None)
    """
    if not email or not code:
        return None, False, "邮箱或验证码不能为空"

    if not verify_email_code(email, code):
        return None, False, "验证码错误或已过期"

    norm_email = email.strip().lower()

    user = await UserInfo.find_one(Eq(UserInfo.email, norm_email))
    if user:
        return user, False, None

    new_user_id = await _allocate_user_id()
    user = UserInfo(
        user_id=new_user_id,
        username=default_username(new_user_id),
        email=norm_email,
    )
    await user.insert()
    return user, True, None


# ---------------------------------------------------------------------------
# SSO 免密登录
# ---------------------------------------------------------------------------

async def login_or_register_by_user_id(
    user_id: str,
) -> Optional[Tuple[UserInfo, bool]]:
    """
    企业 SSO 免密登录/注册：

    - 用户存在 → 直接登录；
    - 用户不存在 → 用传入的 user_id 注册一个新账号（无邮箱）。
    """
    if not user_id:
        return None

    user = await UserInfo.find_one(Eq(UserInfo.user_id, str(user_id)))
    if user:
        return user, False

    user = UserInfo(
        user_id=str(user_id),
        username=default_username(user_id),
    )
    await user.insert()
    return user, True


# ---------------------------------------------------------------------------
# 游客登录
# ---------------------------------------------------------------------------

async def create_guest_user() -> UserInfo:
    """生成一个随机 user_id 的游客账号，用户名为「未命名用户{user_id}」。"""
    guest_id = await _allocate_user_id()
    user = UserInfo(
        user_id=guest_id,
        username=default_username(guest_id),
    )
    await user.insert()
    return user

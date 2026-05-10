# services/auth.py
from agent.database.models.user import UserInfo
from agent.utils.jwt_utils import verify_token
from beanie.operators import Eq
from fastapi import HTTPException
from passlib.hash import bcrypt
import secrets

async def authenticate_user(user_id: str, password: str):
    user = await UserInfo.find_one(Eq(UserInfo.user_id, user_id))
    if not user or not bcrypt.verify(password, user.userpwd):
        return None
    return user

async def register_user(username: str, user_id: str, password: str):
    existing = await UserInfo.find_one(Eq(UserInfo.user_id, user_id))
    if existing:
        return None
    hashed_pwd = bcrypt.hash(password)
    user = UserInfo(username=username, user_id=user_id, userpwd=hashed_pwd)
    await user.insert()
    return user

async def get_current_user(token: str):
    payload = verify_token(token)
    if not payload or "user_id" not in payload:
        raise HTTPException(status_code=401, detail="无效或过期的 token")
    user = await UserInfo.find_one(Eq(UserInfo.user_id, str(payload["user_id"])))
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    return user

async def login_or_register_by_user_id(user_id: str, username: str = None):
    """
    企业SSO免密登录/注册（无密码）
    返回: (user, is_new_user) 或 None
    """
    # 1. 查询用户是否存在
    user = await UserInfo.find_one(Eq(UserInfo.user_id, user_id))

    # 2. 用户存在，直接登录
    if user:
        return user, False

    # 3. 用户不存在，自动注册（生成随机密码，不影响使用）
    random_password = secrets.token_urlsafe(32)
    hashed_pwd = bcrypt.hash(random_password)

    user = UserInfo(
        username=username or user_id,
        user_id=user_id,
        userpwd=hashed_pwd
    )
    await user.insert()

    return user, True
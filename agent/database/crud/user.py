from typing import Optional

from beanie.operators import Eq

from agent.database.models.user import UserInfo


async def get_user_by_user_id(user_id: str) -> Optional[UserInfo]:
    return await UserInfo.find_one(Eq(UserInfo.user_id, str(user_id)))


async def get_user_by_email(email: str) -> Optional[UserInfo]:
    if not email:
        return None
    return await UserInfo.find_one(Eq(UserInfo.email, email.strip().lower()))


async def create_user_in_db(
    username: str,
    user_id: str,
    email: Optional[str] = None,
) -> UserInfo:
    user = UserInfo(
        username=username,
        user_id=str(user_id),
        email=email.strip().lower() if email else None,
    )
    await user.insert()
    return user

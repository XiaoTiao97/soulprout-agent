from agent.database.models.user import UserInfo

async def get_user_by_user_id(user_id: int):
    return await UserInfo.find_one(UserInfo.user_id == user_id)

async def create_user_in_db(username: str, user_id: int, hashed_pwd: str):
    user = UserInfo(
        username=username,
        user_id=user_id,
        userpwd=hashed_pwd,
    )
    await user.insert()
    return user

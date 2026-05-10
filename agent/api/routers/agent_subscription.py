from fastapi import APIRouter
from fastapi.responses import JSONResponse

from agent.database.crud.agent_subscription import (
    remove_agent_subscription_by_user,
    update_agent_subscription_by_user,
)


router = APIRouter()


@router.post("/agent_subscription/{user_id}/update")
async def update_agent_subscription(user_id: str, agent_id: str):
    try:
        await update_agent_subscription_by_user(user_id, agent_id)
        return JSONResponse(status_code=200, content={
            "success": True,
            "message": "订阅成功"
        })
    except Exception as e:
        return JSONResponse(status_code=200, content={
            "success": False,
            "message": f"订阅失败，失败原因：{e}",
            "code": 1004
        })


@router.delete("/agent_subscription/{user_id}/delete")
async def remove_agent_subscription(user_id: str, agent_id: str):
    try:
        await remove_agent_subscription_by_user(user_id, agent_id)
        return JSONResponse(status_code=200, content={
            "success": True,
            "message": "取消订阅成功"
        })
    except Exception as e:
        return JSONResponse(status_code=200, content={
            "success": False,
            "message": f"取消订阅失败，失败原因：{e}",
            "code": 1004
        })

# api/routers/auth.py
import os
from fastapi import APIRouter, Request, Response, Depends, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse
from agent.services.auth import authenticate_user, register_user, get_current_user, login_or_register_by_user_id
from agent.utils.jwt_utils import create_access_token
from agent.api.models.user import LoginInput, RegisterInput

import random

router = APIRouter()

@router.post("/user/login")
async def login(data: LoginInput):
    user = await authenticate_user(data.user_id, data.userpwd)
    if not user:
        return JSONResponse(status_code=200, content={
            "success": False,
            "message": "账号或密码错误",
            "code": 1002
        })
    token = create_access_token({"user_id": user.user_id})
    response = JSONResponse(status_code=200, content={
        "success": True,
        "message": "登录成功",
        "user_id": user.user_id,
        "token": token
    })
    response.set_cookie(key="token", value=token, httponly=True)
    return response

@router.post("/user/register")
async def register(data: RegisterInput):
    user = await register_user(data.username, data.user_id, data.userpwd)
    if not user:
        return JSONResponse(status_code=200, content={
            "success": False,
            "message": "用户已存在",
            "code": 1001
        })
    token = create_access_token({"user_id": user.user_id})
    response = JSONResponse(status_code=200, content={
        "success": True,
        "message": "注册成功",
        "user_id": user.user_id,
        "token": token
    })
    response.set_cookie(key="token", value=token, httponly=True)
    return response

@router.get("/user/me")
async def get_me(request: Request):
    token = request.cookies.get("token")
    if token:
        user = await get_current_user(token)
        response = JSONResponse(status_code=200, content={
            "success": True,
            "message": "登录成功",
            "user_id": user.user_id,
            "username": user.username
        })
        return response
    else:
        return JSONResponse(status_code=200, content={
            "success": False,
            "message": "未登录",
            "code": 1003
        })

@router.post("/user/guest")
async def guest_login():
    username = "不知姓名的远方朋友"
    response = None
    while True:
        guest_id = str(random.randint(1000000, 9999999))
        user = await register_user(username=username, user_id=guest_id, password=str(guest_id))
        if user:
            token = create_access_token({"user_id": guest_id})
            response = JSONResponse(status_code=200, content={
                "success": True,
                "message": "游客登陆成功",
                "user_id": user.user_id,
                "token": token
            })
            response.set_cookie(key="token", value=token, httponly=True)
            break
        else:
            continue
    return response

@router.post("/user/logout")
async def logout(response: Response):
    response.delete_cookie(key="token")  # 直接删除 cookie（FastAPI 会处理为 Set-Cookie 头，设置 expires 为过去）
    return {"message": "logged out"}

@router.get("/sso-entrance")
async def sso_entrance(
        request: Request,
        user_id: str,
        username: str = None
):
    """
    企业门户 SSO 入口（简化版，无签名验证）

    企业门户只需要跳转到：
    https://your-system.com/sso-entrance?user_id=xxx&username=xxx

    参数：
      - user_id: 用户ID（必填）
      - username: 用户名（可选，不填则使用 user_id）
    """
    # 1. 检查功能开关
    if not os.getenv("ENABLE_SSO_LOGIN") == "true":
        raise HTTPException(
            status_code=403,
            detail="SSO功能未开启，请联系管理员配置"
        )

    # # 2. IP 白名单验证（如果配置了）
    # if settings.SSO_ALLOWED_IPS:
    #     client_ip = request.client.host
    #     if client_ip not in settings.SSO_ALLOWED_IPS:
    #         logger.warning(f"非法IP尝试SSO登录: {client_ip}")
    #         raise HTTPException(status_code=403, detail="无权限访问")

    # 3. 免密登录/注册
    result = await login_or_register_by_user_id(user_id, username)

    if not result:
        raise HTTPException(status_code=500, detail="登录失败")

    user, is_new_user = result

    # 4. 生成 token
    token = create_access_token({"user_id": user.user_id})

    # # 5. 记录日志
    # action = "新用户注册并登录" if is_new_user else "用户登录"

    # 6. 设置 Cookie 并跳转到 /chat
    response = RedirectResponse(url=f"{os.getenv('FRONTEND_URL')}/chat", status_code=302)
    response.set_cookie(
        key="token",
        value=token,
        httponly=True,
        max_age=60 * 60 * 24 * 30  # 30天
    )

    return response
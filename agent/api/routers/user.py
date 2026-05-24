# api/routers/user.py
import os

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse

from agent.api.models.user import EmailCodeRequest, EmailLoginRequest, SsoTokenRequest
from agent.services.auth import (
    create_guest_user,
    get_current_user,
    login_or_register_by_email,
    login_or_register_by_user_id,
)
from agent.services.email_service import EmailSendError, is_valid_email, request_email_code
from agent.utils.jwt_utils import create_access_token

router = APIRouter()


# ---------------------------------------------------------------------------
# 邮箱验证码登录 / 注册
# ---------------------------------------------------------------------------

@router.post("/user/email/send-code")
async def send_email_code(data: EmailCodeRequest):
    """向指定邮箱发送一次性验证码。"""
    email = (data.email or "").strip()
    if not is_valid_email(email):
        return JSONResponse(status_code=200, content={
            "success": False,
            "message": "邮箱格式不合法",
            "code": 2001,
        })

    try:
        request_email_code(email)
    except EmailSendError as exc:
        return JSONResponse(status_code=200, content={
            "success": False,
            "message": str(exc),
            "code": 2002,
        })

    return JSONResponse(status_code=200, content={
        "success": True,
        "message": "验证码已发送，请查看邮箱（含垃圾邮件箱）",
    })


@router.post("/user/email/login")
async def email_login(data: EmailLoginRequest):
    """邮箱 + 验证码 一体化登录/注册。

    - 若邮箱已存在 → 直接登录原账号；
    - 若邮箱不存在 → 自动注册并分配 user_id 后登录。
    """
    user, is_new_user, err = await login_or_register_by_email(
        email=data.email,
        code=data.code,
        username=data.username,
    )
    if not user:
        return JSONResponse(status_code=200, content={
            "success": False,
            "message": err or "登录失败",
            "code": 2003,
        })

    token = create_access_token({"user_id": user.user_id})
    response = JSONResponse(status_code=200, content={
        "success": True,
        "message": "注册并登录成功" if is_new_user else "登录成功",
        "is_new_user": is_new_user,
        "user_id": user.user_id,
        "username": user.username,
        "email": user.email,
        "token": token,
    })
    response.set_cookie(
        key="token",
        value=token,
        httponly=True,
        max_age=60 * 60 * 24 * 30,
    )
    return response


# ---------------------------------------------------------------------------
# 当前用户 / 登出 / 游客
# ---------------------------------------------------------------------------

@router.get("/user/me")
async def get_me(request: Request):
    token = request.cookies.get("token")
    if not token:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:].strip()

    if not token:
        return JSONResponse(status_code=200, content={
            "success": False,
            "message": "未登录",
            "code": 1003,
        })

    try:
        user = await get_current_user(token)
    except HTTPException as exc:
        return JSONResponse(status_code=200, content={
            "success": False,
            "message": exc.detail,
            "code": 1003,
        })

    return JSONResponse(status_code=200, content={
        "success": True,
        "message": "已登录",
        "user_id": user.user_id,
        "username": user.username,
        "email": user.email,
    })


@router.post("/user/guest")
async def guest_login():
    """生成一个临时游客账号（自动分配 user_id）。"""
    user = await create_guest_user()
    token = create_access_token({"user_id": user.user_id})
    response = JSONResponse(status_code=200, content={
        "success": True,
        "message": "游客登陆成功",
        "user_id": user.user_id,
        "token": token,
    })
    response.set_cookie(
        key="token",
        value=token,
        httponly=True,
        max_age=60 * 60 * 24 * 30,
    )
    return response


@router.post("/user/logout")
async def logout(response: Response):
    response.delete_cookie(key="token")
    return {"message": "logged out"}


# ---------------------------------------------------------------------------
# 企业 SSO 入口
# ---------------------------------------------------------------------------

def _is_sso_enabled() -> bool:
    return (os.getenv("ENABLE_SSO_LOGIN", "") or "").strip().lower() == "true"


@router.get("/sso-entrance")
async def sso_entrance(request: Request, user_id: str, username: str = None):
    """
    企业门户 SSO 入口（浏览器跳转版本）。

    URL 形如：``https://your-system.com/sso-entrance?user_id=xxx&username=xxx``
    成功后写入 cookie 并 302 跳转到前端 ``/chat``。
    """
    if not _is_sso_enabled():
        raise HTTPException(status_code=403, detail="SSO功能未开启，请联系管理员配置")

    result = await login_or_register_by_user_id(user_id, username)
    if not result:
        raise HTTPException(status_code=500, detail="登录失败")

    user, _is_new_user = result
    token = create_access_token({"user_id": user.user_id})

    frontend_url = os.getenv("FRONTEND_URL", "").rstrip("/")
    redirect_url = f"{frontend_url}/chat" if frontend_url else "/chat"

    response = RedirectResponse(url=redirect_url, status_code=302)
    response.set_cookie(
        key="token",
        value=token,
        httponly=True,
        max_age=60 * 60 * 24 * 30,
    )
    return response


@router.post("/user/sso-token")
async def sso_token(data: SsoTokenRequest):
    """
    企业 SSO 的 JSON 入口（供 Gateway 等服务端调用）。

    与 ``/sso-entrance`` 不同，本接口直接返回 JWT，便于网关侧持久化使用。
    """
    if not _is_sso_enabled():
        return JSONResponse(status_code=200, content={
            "success": False,
            "message": "SSO 功能未开启",
            "code": 2010,
        })

    result = await login_or_register_by_user_id(data.user_id, data.username)
    if not result:
        return JSONResponse(status_code=200, content={
            "success": False,
            "message": "SSO 登录失败",
            "code": 2011,
        })

    user, is_new_user = result
    token = create_access_token({"user_id": user.user_id})

    return JSONResponse(status_code=200, content={
        "success": True,
        "message": "SSO 登录成功",
        "is_new_user": is_new_user,
        "user_id": user.user_id,
        "username": user.username,
        "token": token,
    })

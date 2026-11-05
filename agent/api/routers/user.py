# api/routers/user.py
import os

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse

from agent.api.models.user import (
    EmailCodeRequest,
    EmailLoginRequest,
    ProfileUpdateRequest,
    SaveUserApiKeyRequest,
    SsoTokenRequest,
    UpdateApiKeyPreferencesRequest,
)
from agent.services.api_key_service import (
    delete_user_api_key,
    get_user_api_key_settings,
    save_user_api_key,
    update_user_model_preferences,
)
from agent.services.auth import (
    get_current_user,
    login_or_register_by_email,
    login_or_register_by_user_id,
    require_user,
)
from agent.services.prompt import DEFAULT_AGENT_NAME
from agent.services.email_service import EmailSendError, is_valid_email, request_email_code
from agent.utils.jwt_utils import create_access_token
from agent.database.models.user import UserInfo

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


def _profile_payload(user: UserInfo) -> dict:
    return {
        "success": True,
        "username": user.username,
        "userinfo": user.userinfo or "",
        "agentname": (user.agentname or "").strip() or DEFAULT_AGENT_NAME,
        "agentinfo": user.agentinfo or "",
    }


@router.get("/user/profile")
async def get_profile(user: UserInfo = Depends(require_user)):
    """读取个性化设置：用户名 / 用户信息 / 智能体名字 / 智能体信息。"""
    return JSONResponse(status_code=200, content=_profile_payload(user))


@router.put("/user/profile")
async def update_profile(data: ProfileUpdateRequest, user: UserInfo = Depends(require_user)):
    """更新个性化设置，仅修改请求中提供的字段；用户名、智能体名字不允许为空。"""
    updates = data.model_dump(exclude_none=True)
    for key in ("username", "agentname"):
        if key in updates:
            updates[key] = updates[key].strip()
            if not updates[key]:
                return JSONResponse(status_code=200, content={
                    "success": False,
                    "message": "名字不能为空",
                    "code": 2020,
                })
    for key, value in updates.items():
        setattr(user, key, value)
    if updates:
        await user.save()
    return JSONResponse(status_code=200, content=_profile_payload(user))


@router.post("/user/guest")
async def guest_login():
    """游客登录已禁用，请使用邮箱登录。"""
    return JSONResponse(
        status_code=403,
        content={
            "success": False,
            "message": "游客登录已关闭，请使用邮箱验证登录",
            "code": 2030,
        },
    )


# ---------------------------------------------------------------------------
# 用户自定义 API Key 与指定模型设置（信封加密，永不返回明文 Key）
# ---------------------------------------------------------------------------

@router.get("/user/api-keys")
async def list_api_key_settings(user: UserInfo = Depends(require_user)):
    """获取当前用户的 API Key 脱敏配置状态、支持平台列表与指定模型偏好。"""
    payload = await get_user_api_key_settings(user)
    return JSONResponse(status_code=200, content=payload)


@router.post("/user/api-keys/key")
async def upsert_single_api_key(
    data: SaveUserApiKeyRequest,
    user: UserInfo = Depends(require_user),
):
    """加密保存单个平台的 API Key，仅返回已保存状态与掩码前缀。"""
    try:
        saved = await save_user_api_key(
            user_id=user.user_id,
            model_source=data.model_source,
            raw_api_key=data.api_key,
        )
    except ValueError as exc:
        return JSONResponse(
            status_code=200,
            content={"success": False, "message": str(exc), "code": 2041},
        )
    except Exception:
        return JSONResponse(
            status_code=200,
            content={"success": False, "message": "保存 API Key 失败，请稍后重试", "code": 2042},
        )

    full_state = await get_user_api_key_settings(user)
    full_state["saved_key"] = saved
    full_state["message"] = "API Key 已加密保存"
    return JSONResponse(status_code=200, content=full_state)


@router.delete("/user/api-keys/key/{model_source}")
async def remove_single_api_key(
    model_source: str,
    user: UserInfo = Depends(require_user),
):
    """删除单个平台的 API Key（立即清除数据库记录与内存缓存）。"""
    del_info = await delete_user_api_key(user, model_source)
    full_state = await get_user_api_key_settings(user)
    full_state["delete_info"] = del_info
    full_state["message"] = (
        "已删除该 API Key，因必选模型缺少可用 Key 已自动切回官方默认模式"
        if del_info.get("auto_disabled")
        else "已删除该 API Key"
    )
    return JSONResponse(status_code=200, content=full_state)


@router.put("/user/api-keys/preferences")
async def save_api_key_preferences(
    data: UpdateApiKeyPreferencesRequest,
    user: UserInfo = Depends(require_user),
):
    """更新是否启用自定义 API Key 及 soulprout / pro / flash 指定模型配置。"""
    try:
        payload = await update_user_model_preferences(
            user,
            use_custom_key=data.use_custom_key,
            custom_soulprout_source=data.custom_soulprout_source,
            custom_soulprout_model=data.custom_soulprout_model,
            custom_pro_source=data.custom_pro_source,
            custom_pro_model=data.custom_pro_model,
            custom_flash_source=data.custom_flash_source,
            custom_flash_model=data.custom_flash_model,
        )
        payload["message"] = "配置已保存"
        return JSONResponse(status_code=200, content=payload)
    except ValueError as exc:
        return JSONResponse(
            status_code=200,
            content={"success": False, "message": str(exc), "code": 2043},
        )
    except Exception:
        return JSONResponse(
            status_code=200,
            content={"success": False, "message": "保存配置失败，请稍后重试", "code": 2044},
        )


@router.post("/user/logout")
async def logout(response: Response):
    response.delete_cookie(key="token")
    return {"message": "logged out"}


# ---------------------------------------------------------------------------
# 应用配置（供前端读取部署模式）
# ---------------------------------------------------------------------------

@router.get("/app-config")
async def app_config():
    """返回当前部署模式，前端据此决定走邮箱登录还是私有本地账号流程。"""
    mode = os.getenv("DEPLOYMENT_MODE", "saas").strip().lower()
    return JSONResponse({"deployment_mode": mode})


# ---------------------------------------------------------------------------
# 企业 SSO 入口
# ---------------------------------------------------------------------------

def _is_sso_enabled() -> bool:
    if os.getenv("DEPLOYMENT_MODE", "saas").strip().lower() == "private":
        return True
    return (os.getenv("ENABLE_SSO_LOGIN", "") or "").strip().lower() == "true"


@router.get("/sso-entrance")
async def sso_entrance(request: Request, user_id: str):
    """
    企业门户 SSO 入口（浏览器跳转版本）。

    URL 形如：``https://your-system.com/sso-entrance?user_id=xxx``
    成功后写入 cookie 并 302 跳转到前端 ``/chat``。
    """
    if not _is_sso_enabled():
        raise HTTPException(status_code=403, detail="SSO功能未开启，请联系管理员配置")

    result = await login_or_register_by_user_id(user_id)
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

    result = await login_or_register_by_user_id(data.user_id)
    if not result:
        return JSONResponse(status_code=200, content={
            "success": False,
            "message": "SSO 登录失败",
            "code": 2011,
        })

    user, is_new_user = result
    token = create_access_token({"user_id": user.user_id})

    response = JSONResponse(status_code=200, content={
        "success": True,
        "message": "SSO 登录成功",
        "is_new_user": is_new_user,
        "user_id": user.user_id,
        "username": user.username,
        "token": token,
    })
    response.set_cookie(
        key="token",
        value=token,
        httponly=True,
        max_age=60 * 60 * 24 * 30,
    )
    return response

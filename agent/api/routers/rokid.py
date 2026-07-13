"""Rokid / 灵珠接入：凭证 API + 第三方智能体 SSE。"""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from agent.services.auth import get_current_user
from agent.services.rokid import (
    ROKID_PUBLIC_SSE_URL,
    ensure_credential,
    get_credential_by_api_key,
    get_credential_by_user_id,
    parse_bearer_api_key,
    stream_soul_as_rokid,
    upload_credential,
)

router = APIRouter()


def _token_from_request(request: Request) -> Optional[str]:
    token = request.cookies.get("token")
    if token:
        return token
    auth = request.headers.get("Authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return None


def _cred_payload(cred) -> Dict[str, Any]:
    return {
        "success": True,
        "api_key": cred.api_key,
        "agent_id": cred.agent_id,
        "user_id": cred.user_id,
        "sse_url": ROKID_PUBLIC_SSE_URL,
        "sse_path": "/metis/agent/api/sse",
    }


class RokidUploadRequest(BaseModel):
    api_key: str = Field(..., min_length=8)
    agent_id: str = Field(..., min_length=8)
    force_new_key: bool = False


# ---------------------------------------------------------------------------
# 凭证（需登录）
# ---------------------------------------------------------------------------

@router.get("/rokid/credentials")
async def get_rokid_credentials(request: Request):
    token = _token_from_request(request)
    if not token:
        return JSONResponse({"success": False, "message": "未登录"}, status_code=401)
    user = await get_current_user(token)
    cred = await get_credential_by_user_id(user.user_id)
    if not cred:
        return JSONResponse({
            "success": True,
            "configured": False,
            "api_key": "",
            "agent_id": "",
            "user_id": user.user_id,
            "sse_url": ROKID_PUBLIC_SSE_URL,
        })
    payload = _cred_payload(cred)
    payload["configured"] = True
    return JSONResponse(payload)


@router.post("/rokid/credentials")
async def upload_rokid_credentials(request: Request, body: RokidUploadRequest):
    """Gateway 生成 AK 后上传到主站保存。"""
    token = _token_from_request(request)
    if not token:
        return JSONResponse({"success": False, "message": "未登录"}, status_code=401)
    user = await get_current_user(token)
    try:
        cred = await upload_credential(
            user.user_id,
            api_key=body.api_key,
            agent_id=body.agent_id,
            force_new_key=body.force_new_key,
        )
    except ValueError as exc:
        return JSONResponse({"success": False, "message": str(exc)}, status_code=400)

    payload = _cred_payload(cred)
    payload["configured"] = True
    payload["message"] = (
        "已更新 API Key，请同步修改灵珠三方智能体配置"
        if body.force_new_key
        else "凭证已保存到主站"
    )
    return JSONResponse(payload)


@router.post("/rokid/credentials/ensure")
async def ensure_rokid_credentials(request: Request):
    """主站侧确保凭证存在（无则生成）；不刷新已有 AK。"""
    token = _token_from_request(request)
    if not token:
        return JSONResponse({"success": False, "message": "未登录"}, status_code=401)
    user = await get_current_user(token)
    cred = await ensure_credential(user.user_id, force_new_key=False)
    payload = _cred_payload(cred)
    payload["configured"] = True
    payload["message"] = "API Key 已就绪"
    return JSONResponse(payload)


# ---------------------------------------------------------------------------
# 灵珠 SSE（Bearer = 用户 API Key）
# ---------------------------------------------------------------------------

@router.post("/metis/agent/api/sse")
async def rokid_agent_sse(request: Request):
    api_key = parse_bearer_api_key(request.headers.get("Authorization"))
    cred = await get_credential_by_api_key(api_key)
    if not cred:
        return JSONResponse({"code": -1, "msg": "sk不存在"}, status_code=401)

    try:
        body: Dict[str, Any] = await request.json()
    except Exception:
        return JSONResponse({"code": -1, "msg": "请求体不是合法 JSON"}, status_code=400)

    async def event_gen():
        async for chunk in stream_soul_as_rokid(
            body=body,
            user_id=cred.user_id,
            agent_id=cred.agent_id,
        ):
            yield chunk

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

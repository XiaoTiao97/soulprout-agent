"""
Gateway 管理 Web 服务。

提供一个轻量 FastAPI HTTP 服务（默认端口 8082），包含：

- 微信连接与扫码登录
- Agent 服务地址 / 登录状态 管理
- 邮箱验证码登录（代理到 Agent ``/user/email/*``）
- 企业 SSO 登录（代理到 Agent ``/user/sso-token``）
- 测试连接（校验 Agent 可达性与 token 有效性）
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Optional

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

if TYPE_CHECKING:
    from gateway.platforms.weixin import QRLoginSession, WeixinAdapter

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# FastAPI 应用
# ---------------------------------------------------------------------------

app = FastAPI(title="Soulprout Gateway", docs_url=None, redoc_url=None)

_static_dir = Path(__file__).parent / "static"
if _static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")

# ---------------------------------------------------------------------------
# 运行时状态（由 main.py 注入）
# ---------------------------------------------------------------------------

_weixin_adapter: Optional["WeixinAdapter"] = None
_qr_session: Optional["QRLoginSession"] = None


def set_weixin_adapter(adapter: "WeixinAdapter") -> None:
    global _weixin_adapter
    _weixin_adapter = adapter


# ---------------------------------------------------------------------------
# 页面路由
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def index():
    html_path = _static_dir / "index.html"
    if html_path.exists():
        return HTMLResponse(content=html_path.read_text(encoding="utf-8"))
    return HTMLResponse(
        content="<h1>Soulprout Gateway</h1><p>static/index.html not found</p>"
    )


@app.get("/weixin", response_class=HTMLResponse)
async def weixin_page():
    html_path = _static_dir / "weixin.html"
    if html_path.exists():
        return HTMLResponse(content=html_path.read_text(encoding="utf-8"))
    return HTMLResponse(
        content="<h1>Soulprout Gateway</h1><p>static/weixin.html not found</p>"
    )


# ---------------------------------------------------------------------------
# 微信状态 & 登录
# ---------------------------------------------------------------------------

@app.get("/api/status")
async def api_status():
    connected = _weixin_adapter is not None and _weixin_adapter.is_connected
    accounts: list = []
    try:
        from gateway.platforms.weixin import list_weixin_accounts
        accounts = list_weixin_accounts()
    except Exception:
        pass

    return JSONResponse({
        "connected": connected,
        "platform": "weixin",
        "saved_accounts": accounts,
        "account_id": (_weixin_adapter._account_id if _weixin_adapter else "") or "",
    })


@app.post("/api/weixin/login/start")
async def api_weixin_login_start():
    global _qr_session
    try:
        from gateway.platforms.weixin import QRLoginSession
        if _qr_session:
            await _qr_session.close()
        _qr_session = QRLoginSession()
        result = await _qr_session.start()
        if "error" in result:
            return JSONResponse({"success": False, "error": result["error"]}, status_code=500)
        return JSONResponse({"success": True, **result})
    except Exception as exc:
        logger.error("weixin login start error: %s", exc, exc_info=True)
        return JSONResponse({"success": False, "error": str(exc)}, status_code=500)


@app.get("/api/weixin/login/poll")
async def api_weixin_login_poll():
    global _qr_session
    if _qr_session is None:
        return JSONResponse({"status": "not_started"})
    try:
        result = await _qr_session.poll()
        if result.get("status") == "confirmed" and _weixin_adapter is not None:
            asyncio.create_task(_reconnect_weixin())
        return JSONResponse(result)
    except Exception as exc:
        logger.error("weixin login poll error: %s", exc)
        return JSONResponse({"status": "error", "error": str(exc)})


@app.post("/api/weixin/reload")
async def api_weixin_reload():
    if _weixin_adapter is None:
        return JSONResponse({"success": False, "error": "adapter 未初始化"}, status_code=400)
    try:
        asyncio.create_task(_reconnect_weixin())
        return JSONResponse({"success": True, "message": "正在重新连接…"})
    except Exception as exc:
        return JSONResponse({"success": False, "error": str(exc)}, status_code=500)


# ---------------------------------------------------------------------------
# 设置 API（Agent URL / Token / User ID）
# ---------------------------------------------------------------------------

@app.get("/api/settings")
async def api_get_settings():
    """返回当前网关配置（敏感字段会做脱敏处理）。"""
    from gateway.config_store import is_local_agent, load_settings
    cfg = load_settings()
    return JSONResponse({
        "agent_url": cfg.get("agent_url", ""),
        "agent_user_id": cfg.get("agent_user_id", ""),
        "agent_email": cfg.get("agent_email", ""),
        "agent_login_mode": cfg.get("agent_login_mode", "email"),
        "has_token": bool(cfg.get("agent_token")),
        "token_preview": _mask_token(cfg.get("agent_token", "")),
        "is_local": is_local_agent(cfg.get("agent_url", "")),
    })


@app.post("/api/settings")
async def api_save_settings(request: Request):
    """保存网关基础配置（仅 ``agent_url``）。

    其余字段（``agent_token`` / ``agent_user_id`` / ``agent_email``）通过登录流程自动写入，
    若用户传入这些字段，仍然予以保存（用于「手动粘贴 token」场景）。
    """
    from gateway.config_store import is_local_agent, update_settings
    try:
        body: Dict[str, Any] = await request.json()
    except Exception:
        return JSONResponse({"success": False, "error": "请求体不是合法 JSON"}, status_code=400)

    allowed = {"agent_url", "agent_token", "agent_user_id", "agent_email", "agent_login_mode"}
    partial = {k: v for k, v in body.items() if k in allowed}
    if "agent_url" in partial and partial["agent_url"]:
        partial["agent_url"] = str(partial["agent_url"]).strip().rstrip("/")

    cfg = update_settings(**partial)

    return JSONResponse({
        "success": True,
        "agent_url": cfg.get("agent_url", ""),
        "agent_user_id": cfg.get("agent_user_id", ""),
        "agent_email": cfg.get("agent_email", ""),
        "agent_login_mode": cfg.get("agent_login_mode", "email"),
        "has_token": bool(cfg.get("agent_token")),
        "token_preview": _mask_token(cfg.get("agent_token", "")),
        "is_local": is_local_agent(cfg.get("agent_url", "")),
    })


@app.post("/api/settings/logout")
async def api_logout():
    """清空本地缓存的 token、user_id、email，恢复未登录状态。"""
    from gateway.config_store import update_settings
    update_settings(agent_token="", agent_user_id="", agent_email="")
    return JSONResponse({"success": True, "message": "已清除登录状态"})


@app.post("/api/settings/test")
async def api_test_connection():
    """测试当前配置的 Agent 是否可达，并校验 token 是否有效。"""
    from gateway.config_store import (
        get_agent_token,
        get_agent_url,
        is_local_agent,
    )

    agent_url = get_agent_url()
    mode = "local" if is_local_agent(agent_url) else "remote"

    try:
        import aiohttp
    except ImportError:
        return JSONResponse({"success": False, "mode": mode, "message": "aiohttp 未安装"})

    # Step 1: HTTP 健康检查（/health 不存在也视为可达）
    health_url = f"{agent_url}/health"
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(health_url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                if resp.status >= 500:
                    return JSONResponse({
                        "success": False, "mode": mode,
                        "message": f"Agent 服务异常 HTTP {resp.status}",
                        "agent_url": agent_url,
                    })
        except Exception as exc:
            return JSONResponse({
                "success": False, "mode": mode,
                "message": f"无法连接到 Agent：{exc}",
                "agent_url": agent_url,
            })

    # Step 2: 验证已保存的 token
    token = get_agent_token()
    if not token:
        return JSONResponse({
            "success": True, "mode": mode,
            "message": "Agent 服务可达，但当前未登录。请先通过下方按钮完成登录。",
            "agent_url": agent_url,
        })

    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"{agent_url}/user/me",
            cookies={"token": token},
            headers={"Authorization": f"Bearer {token}"},
            timeout=aiohttp.ClientTimeout(total=8),
        ) as resp:
            try:
                data = await resp.json()
            except Exception:
                data = {}

    if data.get("success"):
        return JSONResponse({
            "success": True, "mode": mode,
            "message": f"连接并认证成功，登录用户：{data.get('user_id', '未知')}",
            "agent_url": agent_url,
        })

    return JSONResponse({
        "success": False, "mode": mode,
        "message": "Token 已失效，请重新登录",
        "agent_url": agent_url,
    })


# ---------------------------------------------------------------------------
# Agent 邮箱验证码登录（代理）
# ---------------------------------------------------------------------------

@app.post("/api/auth/email/send-code")
async def api_email_send_code(request: Request):
    from gateway.config_store import get_agent_url
    try:
        body: Dict[str, Any] = await request.json()
    except Exception:
        return JSONResponse({"success": False, "message": "请求体不是合法 JSON"}, status_code=400)

    email = (body.get("email") or "").strip()
    if not email:
        return JSONResponse({"success": False, "message": "请填写邮箱"})

    agent_url = get_agent_url()
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{agent_url}/user/email/send-code",
                json={"email": email},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                data = await resp.json()
                return JSONResponse(data)
    except Exception as exc:
        return JSONResponse({"success": False, "message": f"调用 Agent 失败：{exc}"})


@app.post("/api/auth/email/login")
async def api_email_login(request: Request):
    """提交邮箱+验证码到 Agent，登录成功后将 token / user_id / email 写入本地配置。"""
    from gateway.config_store import get_agent_url, update_settings
    try:
        body: Dict[str, Any] = await request.json()
    except Exception:
        return JSONResponse({"success": False, "message": "请求体不是合法 JSON"}, status_code=400)

    email = (body.get("email") or "").strip()
    code = (body.get("code") or "").strip()
    username = (body.get("username") or "").strip() or None
    if not email or not code:
        return JSONResponse({"success": False, "message": "邮箱与验证码不能为空"})

    agent_url = get_agent_url()
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{agent_url}/user/email/login",
                json={"email": email, "code": code, "username": username},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                data = await resp.json()
    except Exception as exc:
        return JSONResponse({"success": False, "message": f"调用 Agent 失败：{exc}"})

    if data.get("success") and data.get("token"):
        update_settings(
            agent_token=data["token"],
            agent_user_id=str(data.get("user_id", "")),
            agent_email=email,
            agent_login_mode="email",
        )

    return JSONResponse(data)


# ---------------------------------------------------------------------------
# Agent SSO 登录（代理）
# ---------------------------------------------------------------------------

@app.post("/api/auth/sso/login")
async def api_sso_login(request: Request):
    """通过 ``user_id`` 走企业 SSO 登录。

    需要 Agent 端开启 ``ENABLE_SSO_LOGIN=true``，否则返回错误。
    """
    from gateway.config_store import get_agent_url, update_settings
    try:
        body: Dict[str, Any] = await request.json()
    except Exception:
        return JSONResponse({"success": False, "message": "请求体不是合法 JSON"}, status_code=400)

    user_id = (body.get("user_id") or "").strip()
    username = (body.get("username") or "").strip() or None
    if not user_id:
        return JSONResponse({"success": False, "message": "请填写 user_id"})

    agent_url = get_agent_url()
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{agent_url}/user/sso-token",
                json={"user_id": user_id, "username": username},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                data = await resp.json()
    except Exception as exc:
        return JSONResponse({"success": False, "message": f"调用 Agent 失败：{exc}"})

    if data.get("success") and data.get("token"):
        update_settings(
            agent_token=data["token"],
            agent_user_id=str(data.get("user_id", user_id)),
            agent_email="",
            agent_login_mode="sso",
        )

    return JSONResponse(data)


# ---------------------------------------------------------------------------
# 内部辅助
# ---------------------------------------------------------------------------

def _mask_token(token: str) -> str:
    if not token:
        return ""
    if len(token) <= 12:
        return "****"
    return f"{token[:6]}…{token[-4:]}"


async def _reconnect_weixin() -> None:
    if _weixin_adapter is None:
        return
    try:
        if _weixin_adapter.is_connected:
            await _weixin_adapter.disconnect()
        loaded = _weixin_adapter.reload_credentials()
        if not loaded:
            logger.warning("[web] 重新加载凭证失败，无法重连")
            return
        ok = await _weixin_adapter.connect()
        if ok:
            logger.info("[web] 微信 adapter 已重新连接")
        else:
            logger.warning("[web] 微信 adapter 重连失败")
    except Exception as exc:
        logger.error("[web] 重连异常: %s", exc, exc_info=True)


# ---------------------------------------------------------------------------
# 启动函数（由 main.py 调用）
# ---------------------------------------------------------------------------

async def start_web_server(host: str = "0.0.0.0", port: int = 8082) -> None:
    import uvicorn
    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level="warning",
        access_log=False,
    )
    server = uvicorn.Server(config)
    logger.info("[Web] 管理界面已启动 http://%s:%d", host, port)
    await server.serve()

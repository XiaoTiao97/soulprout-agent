"""
Gateway 管理 Web 服务。

提供一个轻量 FastAPI HTTP 服务（默认端口 8082），包含：

- 微信连接与扫码登录
- 飞书 WebSocket 连接（扫码创建 Bot / 手动 App ID 配置）
- 企业微信 AI Bot WebSocket 连接（扫码 / 手动 Bot ID 配置）
- Agent 服务地址 / 登录状态 管理
- 邮箱验证码登录（代理到 Agent ``/user/email/*``）
- 企业 SSO 登录（代理到 Agent ``/user/sso-token``）
- 测试连接（校验 Agent 可达性与 token 有效性）

飞书 / 企业微信 WebSocket 实现参考：https://github.com/NousResearch/hermes-agent
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
    from gateway.platforms.feishu import FeishuAdapter, FeishuQRSession
    from gateway.platforms.wecom import WecomAdapter, WecomQRSession
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
_feishu_adapter: Optional["FeishuAdapter"] = None
_wecom_adapter: Optional["WecomAdapter"] = None
_qr_session: Optional["QRLoginSession"] = None
_feishu_qr_session: Optional["FeishuQRSession"] = None
_wecom_qr_session: Optional["WecomQRSession"] = None


def set_weixin_adapter(adapter: "WeixinAdapter") -> None:
    global _weixin_adapter
    _weixin_adapter = adapter


def set_feishu_adapter(adapter: "FeishuAdapter") -> None:
    global _feishu_adapter
    _feishu_adapter = adapter


def set_wecom_adapter(adapter: "WecomAdapter") -> None:
    global _wecom_adapter
    _wecom_adapter = adapter


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


@app.get("/feishu", response_class=HTMLResponse)
async def feishu_page():
    html_path = _static_dir / "feishu.html"
    if html_path.exists():
        return HTMLResponse(content=html_path.read_text(encoding="utf-8"))
    return HTMLResponse(
        content="<h1>Soulprout Gateway</h1><p>static/feishu.html not found</p>"
    )


@app.get("/wecom", response_class=HTMLResponse)
async def wecom_page():
    html_path = _static_dir / "wecom.html"
    if html_path.exists():
        return HTMLResponse(content=html_path.read_text(encoding="utf-8"))
    return HTMLResponse(
        content="<h1>Soulprout Gateway</h1><p>static/wecom.html not found</p>"
    )


# ---------------------------------------------------------------------------
# 微信状态 & 登录
# ---------------------------------------------------------------------------

@app.get("/api/status")
async def api_status():
    """兼容旧前端：返回微信状态摘要。"""
    return JSONResponse(await _weixin_status_payload())


@app.get("/api/weixin/status")
async def api_weixin_status():
    return JSONResponse(await _weixin_status_payload())


@app.get("/api/feishu/status")
async def api_feishu_status():
    return JSONResponse(await _feishu_status_payload())


@app.get("/api/wecom/status")
async def api_wecom_status():
    return JSONResponse(await _wecom_status_payload())


async def _weixin_status_payload() -> Dict[str, Any]:
    connected = _weixin_adapter is not None and _weixin_adapter.is_connected
    accounts: list = []
    try:
        from gateway.platforms.weixin import list_weixin_accounts
        accounts = list_weixin_accounts()
    except Exception:
        pass
    return {
        "connected": connected,
        "platform": "weixin",
        "saved_accounts": accounts,
        "account_id": (_weixin_adapter._account_id if _weixin_adapter else "") or "",
    }


async def _feishu_status_payload() -> Dict[str, Any]:
    connected = _feishu_adapter is not None and _feishu_adapter.is_connected
    cfg: Dict[str, Any] = {}
    try:
        from gateway.platforms.feishu import load_feishu_config, has_feishu_config
        configured = has_feishu_config()
        raw = load_feishu_config() or {}
        cfg = {
            "configured": configured,
            "app_id": raw.get("app_id", ""),
            "domain": raw.get("domain", "feishu"),
            "bot_name": raw.get("bot_name", ""),
        }
    except Exception:
        cfg = {"configured": False}

    return {
        "connected": connected,
        "platform": "feishu",
        "configured": cfg.get("configured", False),
        "app_id": cfg.get("app_id", ""),
        "domain": cfg.get("domain", "feishu"),
        "bot_name": (_feishu_adapter.bot_name if _feishu_adapter else "") or cfg.get("bot_name", ""),
    }


async def _wecom_status_payload() -> Dict[str, Any]:
    connected = _wecom_adapter is not None and _wecom_adapter.is_connected
    cfg: Dict[str, Any] = {}
    try:
        from gateway.platforms.wecom import has_wecom_config, load_wecom_config
        configured = has_wecom_config()
        raw = load_wecom_config() or {}
        cfg = {
            "configured": configured,
            "bot_id": raw.get("bot_id", ""),
            "bot_name": raw.get("bot_name", ""),
        }
    except Exception:
        cfg = {"configured": False}

    return {
        "connected": connected,
        "platform": "wecom",
        "configured": cfg.get("configured", False),
        "bot_id": cfg.get("bot_id", ""),
        "bot_name": (_wecom_adapter.bot_name if _wecom_adapter else "") or cfg.get("bot_name", ""),
    }


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
# 飞书状态 & 配置
# ---------------------------------------------------------------------------

@app.post("/api/feishu/login/start")
async def api_feishu_login_start(request: Request):
    global _feishu_qr_session
    domain = "feishu"
    try:
        body = await request.json()
        domain = str(body.get("domain") or "feishu").strip() or "feishu"
    except Exception:
        pass
    try:
        from gateway.platforms.feishu import FeishuQRSession
        if _feishu_qr_session:
            await _feishu_qr_session.close()
        _feishu_qr_session = FeishuQRSession(domain=domain)
        result = await _feishu_qr_session.start()
        if "error" in result:
            return JSONResponse({"success": False, "error": result["error"]}, status_code=500)
        return JSONResponse({"success": True, **result})
    except Exception as exc:
        logger.error("feishu login start error: %s", exc, exc_info=True)
        return JSONResponse({"success": False, "error": str(exc)}, status_code=500)


@app.get("/api/feishu/login/poll")
async def api_feishu_login_poll():
    global _feishu_qr_session
    if _feishu_qr_session is None:
        return JSONResponse({"status": "not_started"})
    try:
        result = await _feishu_qr_session.poll()
        if result.get("status") == "confirmed" and _feishu_adapter is not None:
            asyncio.create_task(_reconnect_feishu())
        return JSONResponse(result)
    except Exception as exc:
        logger.error("feishu login poll error: %s", exc)
        return JSONResponse({"status": "error", "error": str(exc)})


@app.post("/api/feishu/settings")
async def api_feishu_settings(request: Request):
    """手动保存 App ID / App Secret。"""
    from gateway.platforms.feishu import probe_bot, save_feishu_config
    try:
        body: Dict[str, Any] = await request.json()
    except Exception:
        return JSONResponse({"success": False, "error": "请求体不是合法 JSON"}, status_code=400)

    app_id = str(body.get("app_id") or "").strip()
    app_secret = str(body.get("app_secret") or "").strip()
    domain = str(body.get("domain") or "feishu").strip() or "feishu"
    if domain not in {"feishu", "lark"}:
        return JSONResponse({"success": False, "error": "domain 必须为 feishu 或 lark"}, status_code=400)
    if not app_id or not app_secret:
        return JSONResponse({"success": False, "error": "App ID 与 App Secret 不能为空"}, status_code=400)

    bot_info = await asyncio.to_thread(probe_bot, app_id, app_secret, domain) or {}
    save_feishu_config(
        app_id=app_id,
        app_secret=app_secret,
        domain=domain,
        bot_name=str(bot_info.get("bot_name") or ""),
        bot_open_id=str(bot_info.get("bot_open_id") or ""),
    )

    if _feishu_adapter is not None:
        asyncio.create_task(_reconnect_feishu())

    return JSONResponse({
        "success": True,
        "app_id": app_id,
        "domain": domain,
        "bot_name": bot_info.get("bot_name") or "",
        "message": "凭证已保存，正在连接…",
    })


@app.post("/api/feishu/reload")
async def api_feishu_reload():
    if _feishu_adapter is None:
        return JSONResponse({"success": False, "error": "adapter 未初始化"}, status_code=400)
    try:
        asyncio.create_task(_reconnect_feishu())
        return JSONResponse({"success": True, "message": "正在重新连接…"})
    except Exception as exc:
        return JSONResponse({"success": False, "error": str(exc)}, status_code=500)


# ---------------------------------------------------------------------------
# 企业微信状态 & 配置
# ---------------------------------------------------------------------------

@app.post("/api/wecom/login/start")
async def api_wecom_login_start():
    global _wecom_qr_session
    try:
        from gateway.platforms.wecom import WecomQRSession
        if _wecom_qr_session:
            await _wecom_qr_session.close()
        _wecom_qr_session = WecomQRSession()
        result = await _wecom_qr_session.start()
        if "error" in result:
            return JSONResponse({"success": False, "error": result["error"]}, status_code=500)
        return JSONResponse({"success": True, **result})
    except Exception as exc:
        logger.error("wecom login start error: %s", exc, exc_info=True)
        return JSONResponse({"success": False, "error": str(exc)}, status_code=500)


@app.get("/api/wecom/login/poll")
async def api_wecom_login_poll():
    global _wecom_qr_session
    if _wecom_qr_session is None:
        return JSONResponse({"status": "not_started"})
    try:
        result = await _wecom_qr_session.poll()
        if result.get("status") == "confirmed" and _wecom_adapter is not None:
            asyncio.create_task(_reconnect_wecom())
        return JSONResponse(result)
    except Exception as exc:
        logger.error("wecom login poll error: %s", exc)
        return JSONResponse({"status": "error", "error": str(exc)})


@app.post("/api/wecom/settings")
async def api_wecom_settings(request: Request):
    from gateway.platforms.wecom import save_wecom_config
    try:
        body: Dict[str, Any] = await request.json()
    except Exception:
        return JSONResponse({"success": False, "error": "请求体不是合法 JSON"}, status_code=400)

    bot_id = str(body.get("bot_id") or "").strip()
    secret = str(body.get("secret") or "").strip()
    if not bot_id or not secret:
        return JSONResponse({"success": False, "error": "Bot ID 与 Secret 不能为空"}, status_code=400)

    save_wecom_config(bot_id=bot_id, secret=secret)

    if _wecom_adapter is not None:
        asyncio.create_task(_reconnect_wecom())

    return JSONResponse({
        "success": True,
        "bot_id": bot_id,
        "message": "凭证已保存，正在连接…",
    })


@app.post("/api/wecom/reload")
async def api_wecom_reload():
    if _wecom_adapter is None:
        return JSONResponse({"success": False, "error": "adapter 未初始化"}, status_code=400)
    try:
        asyncio.create_task(_reconnect_wecom())
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
            logger.warning("[web] 重新加载微信凭证失败，无法重连")
            return
        ok = await _weixin_adapter.connect()
        if ok:
            logger.info("[web] 微信 adapter 已重新连接")
        else:
            logger.warning("[web] 微信 adapter 重连失败")
    except Exception as exc:
        logger.error("[web] 微信重连异常: %s", exc, exc_info=True)


async def _reconnect_feishu() -> None:
    if _feishu_adapter is None:
        return
    try:
        if _feishu_adapter.is_connected:
            await _feishu_adapter.disconnect()
        loaded = _feishu_adapter.reload_credentials()
        if not loaded:
            logger.warning("[web] 重新加载飞书凭证失败，无法重连")
            return
        ok = await _feishu_adapter.connect()
        if ok:
            logger.info("[web] 飞书 adapter 已重新连接")
        else:
            logger.warning("[web] 飞书 adapter 重连失败")
    except Exception as exc:
        logger.error("[web] 飞书重连异常: %s", exc, exc_info=True)


async def _reconnect_wecom() -> None:
    if _wecom_adapter is None:
        return
    try:
        if _wecom_adapter.is_connected:
            await _wecom_adapter.disconnect()
        loaded = _wecom_adapter.reload_credentials()
        if not loaded:
            logger.warning("[web] 重新加载企业微信凭证失败，无法重连")
            return
        ok = await _wecom_adapter.connect()
        if ok:
            logger.info("[web] 企业微信 adapter 已重新连接")
        else:
            logger.warning("[web] 企业微信 adapter 重连失败")
    except Exception as exc:
        logger.error("[web] 企业微信重连异常: %s", exc, exc_info=True)


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

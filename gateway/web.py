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
- Rokid 灵珠：本地生成 API Key 并上传主站；SSE 由主站提供

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
    from gateway.platforms.xiaoai import XiaoaiAdapter

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
_xiaoai_adapter: Optional["XiaoaiAdapter"] = None
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


def set_xiaoai_adapter(adapter: "XiaoaiAdapter") -> None:
    global _xiaoai_adapter
    _xiaoai_adapter = adapter


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


@app.get("/xiaoai", response_class=HTMLResponse)
async def xiaoai_page():
    html_path = _static_dir / "xiaoai.html"
    if html_path.exists():
        return HTMLResponse(content=html_path.read_text(encoding="utf-8"))
    return HTMLResponse(
        content="<h1>Soulprout Gateway</h1><p>static/xiaoai.html not found</p>"
    )


@app.get("/rokid", response_class=HTMLResponse)
async def rokid_page():
    html_path = _static_dir / "rokid.html"
    if html_path.exists():
        return HTMLResponse(content=html_path.read_text(encoding="utf-8"))
    return HTMLResponse(
        content="<h1>Soulprout Gateway</h1><p>static/rokid.html not found</p>"
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


@app.get("/api/xiaoai/status")
async def api_xiaoai_status():
    return JSONResponse(await _xiaoai_status_payload())


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


async def _xiaoai_status_payload() -> Dict[str, Any]:
    connected = _xiaoai_adapter is not None and _xiaoai_adapter.is_connected
    cfg: Dict[str, Any] = {}
    try:
        from gateway.platforms.xiaoai import get_public_config
        from gateway.platforms.xiaoai_miot import has_xiaoai_config
        configured = has_xiaoai_config()
        cfg = get_public_config()
    except Exception:
        configured = False
    return {
        "platform": "xiaoai",
        "connected": connected,
        "configured": configured,
        "device_name": (_xiaoai_adapter.device_name if _xiaoai_adapter else "") or cfg.get("did", ""),
        "last_error": (_xiaoai_adapter.last_error if _xiaoai_adapter else "") or "",
        "config": cfg,
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


@app.get("/api/xiaoai/config")
async def api_xiaoai_get_config():
    from gateway.platforms.xiaoai import get_public_config
    from gateway.platforms.xiaoai_miot import has_xiaoai_config
    return JSONResponse({
        "configured": has_xiaoai_config(),
        "config": get_public_config(),
    })


@app.post("/api/xiaoai/settings")
async def api_xiaoai_settings(request: Request):
    from gateway.platforms.xiaoai_miot import save_xiaoai_config

    try:
        body: Dict[str, Any] = await request.json()
    except Exception:
        return JSONResponse({"success": False, "error": "请求体不是合法 JSON"}, status_code=400)

    user_id = str(body.get("user_id") or "").strip()
    did = str(body.get("did") or "").strip()
    password = str(body.get("password") or "")
    pass_token = str(body.get("pass_token") or "")
    keywords_raw = body.get("call_ai_keywords")
    heartbeat_ms = int(body.get("heartbeat_ms") or 1000)
    debug = bool(body.get("debug"))

    if not user_id or not did:
        return JSONResponse({"success": False, "error": "请填写小米 ID 和设备名称"}, status_code=400)

    keywords: Optional[list] = None
    if isinstance(keywords_raw, list):
        keywords = [str(k).strip() for k in keywords_raw if str(k).strip()]
    elif isinstance(keywords_raw, str):
        keywords = [k.strip() for k in keywords_raw.replace("，", ",").split(",") if k.strip()]

    save_xiaoai_config(
        user_id=user_id,
        did=did,
        password=password,
        pass_token=pass_token,
        call_ai_keywords=keywords,
        heartbeat_ms=heartbeat_ms,
        debug=debug,
    )

    if _xiaoai_adapter is not None:
        asyncio.create_task(_reconnect_xiaoai())

    return JSONResponse({"success": True, "message": "配置已保存，正在重新连接…"})


@app.post("/api/xiaoai/test")
async def api_xiaoai_test(request: Request):
    from gateway.platforms.xiaoai_miot import load_xiaoai_config, test_mina_login

    try:
        body: Dict[str, Any] = await request.json()
    except Exception:
        body = {}

    cfg = load_xiaoai_config() or {}
    user_id = str(body.get("user_id") or cfg.get("user_id") or "").strip()
    did = str(body.get("did") or cfg.get("did") or "").strip()
    password = str(body.get("password") or cfg.get("password") or "")
    pass_token = str(body.get("pass_token") or cfg.get("pass_token") or "")

    if not user_id or not did:
        return JSONResponse({"success": False, "message": "请填写小米 ID 和设备名称"}, status_code=400)
    if not password and not pass_token:
        return JSONResponse({"success": False, "message": "请填写密码或 passToken"}, status_code=400)

    result = await test_mina_login(
        user_id=user_id,
        password=password,
        pass_token=pass_token,
        did=did,
    )
    return JSONResponse(result)


@app.post("/api/xiaoai/reload")
async def api_xiaoai_reload():
    if _xiaoai_adapter is None:
        return JSONResponse({"success": False, "error": "adapter 未初始化"}, status_code=400)
    try:
        asyncio.create_task(_reconnect_xiaoai())
        return JSONResponse({"success": True, "message": "正在重新连接…"})
    except Exception as exc:
        return JSONResponse({"success": False, "error": str(exc)}, status_code=500)


# ---------------------------------------------------------------------------
# Rokid / 灵珠（凭证在主站；Gateway 负责生成并上传）
# ---------------------------------------------------------------------------

async def _rokid_agent_request(
    method: str,
    path: str,
    *,
    token: str,
    json_body: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """带登录态调用主站 Rokid 凭证 API。"""
    import aiohttp
    from gateway.config_store import api_path, get_agent_url

    url = api_path(get_agent_url(), path)
    headers = {"Authorization": f"Bearer {token}"}
    cookies = {"token": token}
    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.request(
            method,
            url,
            json=json_body,
            headers=headers,
            cookies=cookies,
        ) as resp:
            data = await resp.json(content_type=None)
            if resp.status >= 400:
                msg = (
                    (data or {}).get("message")
                    or (data or {}).get("detail")
                    or (data or {}).get("msg")
                    or f"HTTP {resp.status}"
                )
                raise RuntimeError(str(msg))
            if not isinstance(data, dict):
                raise RuntimeError("主站返回格式异常")
            return data


@app.get("/api/rokid/status")
async def api_rokid_status():
    """优先从主站拉取凭证；失败时回退本地缓存。"""
    from gateway.config_store import (
        cache_rokid_credentials,
        get_agent_token,
        get_agent_url,
        get_agent_user_id,
        get_rokid_agent_id,
        get_rokid_api_key,
        get_rokid_bound_user_id,
    )
    from gateway.platforms.rokid import ROKID_HOME_URL, ROKID_PUBLIC_SSE_URL, ROKID_SSE_PATH

    token = get_agent_token()
    user_id = get_agent_user_id()
    agent_url = get_agent_url()
    remote: Dict[str, Any] | None = None
    remote_error = ""
    if token:
        try:
            remote = await _rokid_agent_request("GET", "/rokid/credentials", token=token)
            if remote.get("configured") and remote.get("api_key"):
                cache_rokid_credentials(
                    api_key=remote.get("api_key", ""),
                    agent_id=remote.get("agent_id", ""),
                    user_id=remote.get("user_id") or user_id,
                )
        except Exception as exc:
            remote_error = str(exc)

    api_key = (remote or {}).get("api_key") or get_rokid_api_key()
    agent_id = (remote or {}).get("agent_id") or get_rokid_agent_id()
    bound_user = (remote or {}).get("user_id") or get_rokid_bound_user_id() or user_id

    return JSONResponse({
        "configured": bool(api_key and agent_id),
        "logged_in": bool(token and user_id),
        "api_key": api_key,
        "agent_id": agent_id,
        "bound_user_id": bound_user,
        "sse_url": ROKID_PUBLIC_SSE_URL,
        "sse_path": ROKID_SSE_PATH,
        "rokid_home_url": ROKID_HOME_URL,
        "current_user_id": user_id,
        "remote_error": remote_error,
        "agent_url": agent_url,
        "sse_host_mismatch": "soulprout.com" not in (agent_url or "").lower(),
    })


@app.post("/api/rokid/ensure-key")
async def api_rokid_ensure_key():
    """本地生成（若主站尚无）并上传到主站；已有则直接返回主站凭证。

    若主站已有但 agent_id 超过 20 字符，会强制换发合规 ID + 新 AK。
    """
    from gateway.config_store import (
        cache_rokid_credentials,
        generate_local_rokid_pair,
        get_agent_token,
        get_agent_user_id,
        get_rokid_agent_id,
    )

    user_id = get_agent_user_id()
    token = get_agent_token()
    if not user_id or not token:
        return JSONResponse(
            {"success": False, "error": "请先在 Gateway 首页登录 Soulprout 账号"},
            status_code=401,
        )

    try:
        remote = await _rokid_agent_request("GET", "/rokid/credentials", token=token)
        remote_agent_id = (remote.get("agent_id") or "").strip()
        need_fix_id = bool(remote.get("configured") and remote_agent_id and len(remote_agent_id) > 20)

        if remote.get("configured") and remote.get("api_key") and not need_fix_id:
            cache_rokid_credentials(
                api_key=remote["api_key"],
                agent_id=remote_agent_id,
                user_id=remote.get("user_id") or user_id,
            )
            return JSONResponse({
                "success": True,
                "api_key": remote["api_key"],
                "agent_id": remote_agent_id,
                "bound_user_id": remote.get("user_id") or user_id,
                "sse_url": remote.get("sse_url"),
                "message": "已从主站同步 API Key（不会重复生成）",
            })

        # 新建，或修复超长 agent_id：一律发新的合规 ID
        pair = generate_local_rokid_pair(
            user_id=user_id,
            reuse_agent_id="" if need_fix_id else (get_rokid_agent_id() or remote_agent_id),
            force_new_agent_id=need_fix_id,
        )
        uploaded = await _rokid_agent_request(
            "POST",
            "/rokid/credentials",
            token=token,
            json_body={
                "api_key": pair["api_key"],
                "agent_id": pair["agent_id"],
                "force_new_key": need_fix_id,
            },
        )
        final_agent_id = (uploaded.get("agent_id") or pair["agent_id"] or "").strip()
        if len(final_agent_id) > 20:
            return JSONResponse({
                "success": False,
                "error": (
                    "主站仍返回超过 20 字符的智能体 ID。"
                    "请确认 www.soulprout.com 上的 Agent 已部署最新代码并重启后再试。"
                ),
            }, status_code=500)
        cache_rokid_credentials(
            api_key=uploaded.get("api_key") or pair["api_key"],
            agent_id=final_agent_id,
            user_id=uploaded.get("user_id") or user_id,
        )
        return JSONResponse({
            "success": True,
            "api_key": uploaded.get("api_key") or pair["api_key"],
            "agent_id": final_agent_id,
            "bound_user_id": uploaded.get("user_id") or user_id,
            "sse_url": uploaded.get("sse_url"),
            "message": (
                "已将超长智能体 ID 替换为不超过 20 字符的新 ID，并更新 AK；请同步修改灵珠配置"
                if need_fix_id
                else "API Key 已生成并上传到主站"
            ),
        })
    except Exception as exc:
        return JSONResponse({"success": False, "error": str(exc)}, status_code=500)


@app.post("/api/rokid/regenerate-key")
async def api_rokid_regenerate_key():
    """重新生成 AK；若智能体 ID 超长则一并强制换新。"""
    from gateway.config_store import (
        cache_rokid_credentials,
        generate_local_rokid_pair,
        get_agent_token,
        get_agent_user_id,
        get_rokid_agent_id,
    )

    user_id = get_agent_user_id()
    token = get_agent_token()
    if not user_id or not token:
        return JSONResponse(
            {"success": False, "error": "请先在 Gateway 首页登录 Soulprout 账号"},
            status_code=401,
        )

    try:
        old_agent_id = get_rokid_agent_id()
        try:
            remote = await _rokid_agent_request("GET", "/rokid/credentials", token=token)
            # GET 若已自动 heal，这里会拿到新短 ID
            old_agent_id = (remote.get("agent_id") or old_agent_id or "").strip()
        except Exception:
            pass

        need_fix_id = (not old_agent_id) or len(old_agent_id) > 20
        pair = generate_local_rokid_pair(
            user_id=user_id,
            reuse_agent_id="" if need_fix_id else old_agent_id,
            force_new_agent_id=need_fix_id,
        )
        uploaded = await _rokid_agent_request(
            "POST",
            "/rokid/credentials",
            token=token,
            json_body={
                "api_key": pair["api_key"],
                "agent_id": pair["agent_id"],
                "force_new_key": True,
            },
        )
        final_agent_id = (uploaded.get("agent_id") or pair["agent_id"] or "").strip()
        if len(final_agent_id) > 20:
            return JSONResponse({
                "success": False,
                "error": (
                    "主站仍返回超过 20 字符的智能体 ID。"
                    "请确认 www.soulprout.com 上的 Agent 已部署最新代码并重启后再试。"
                ),
            }, status_code=500)

        cache_rokid_credentials(
            api_key=uploaded.get("api_key") or pair["api_key"],
            agent_id=final_agent_id,
            user_id=uploaded.get("user_id") or user_id,
        )
        return JSONResponse({
            "success": True,
            "api_key": uploaded.get("api_key") or pair["api_key"],
            "agent_id": final_agent_id,
            "bound_user_id": uploaded.get("user_id") or user_id,
            "sse_url": uploaded.get("sse_url"),
            "message": (
                "已覆盖超长智能体 ID 为新 ID，并更新 AK。请到灵珠平台重新配置第三方智能体的 ID 与 AK。"
                if need_fix_id or (old_agent_id and old_agent_id != final_agent_id)
                else "已生成新的 API Key 并上传主站。请到灵珠平台重新配置第三方智能体的 AK。"
            ),
        })
    except Exception as exc:
        return JSONResponse({"success": False, "error": str(exc)}, status_code=500)



# ---------------------------------------------------------------------------
# 设置 API（Agent URL / Token / User ID）
# ---------------------------------------------------------------------------

@app.get("/api/settings")
async def api_get_settings():
    """返回当前网关配置（敏感字段会做脱敏处理）。"""
    from gateway.config_store import (
        get_cloud_agent_urls,
        get_default_agent_url,
        is_local_agent,
        load_settings,
    )
    cfg = load_settings()
    return JSONResponse({
        "agent_url": cfg.get("agent_url", ""),
        "default_agent_url": get_default_agent_url(),
        "cloud_urls": get_cloud_agent_urls(),
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
    """清空本地缓存的登录态；Rokid 凭证缓存保留（权威数据在主站）。"""
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

    from gateway.config_store import api_path

    # Step 1: HTTP 健康检查（/health 不存在也视为可达）
    health_url = api_path(agent_url, "/health")
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
            api_path(agent_url, "/user/me"),
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

def _resolve_agent_url(body: Dict[str, Any]) -> str:
    """从请求体读取 agent_url 并持久化；未传则使用已保存或默认地址。"""
    from gateway.config_store import get_agent_url, normalize_agent_url, update_settings

    raw = (body.get("agent_url") or "").strip()
    if raw:
        url = normalize_agent_url(raw)
        update_settings(agent_url=url)
        return url
    return get_agent_url()


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

    agent_url = _resolve_agent_url(body)
    from gateway.config_store import api_path, get_auth_url
    auth_url = get_auth_url(agent_url)
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.post(
                api_path(auth_url, "/user/email/send-code"),
                json={"email": email},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                data = await resp.json()
                data["agent_url"] = agent_url
                return JSONResponse(data)
    except Exception as exc:
        return JSONResponse({
            "success": False,
            "message": f"发送验证码失败：{exc}",
            "agent_url": agent_url,
        })


@app.post("/api/auth/email/login")
async def api_email_login(request: Request):
    """提交邮箱+验证码到 Agent，登录成功后将 token / user_id / email 写入本地配置。"""
    from gateway.config_store import update_settings
    try:
        body: Dict[str, Any] = await request.json()
    except Exception:
        return JSONResponse({"success": False, "message": "请求体不是合法 JSON"}, status_code=400)

    email = (body.get("email") or "").strip()
    code = (body.get("code") or "").strip()
    username = (body.get("username") or "").strip() or None
    if not email or not code:
        return JSONResponse({"success": False, "message": "邮箱与验证码不能为空"})

    agent_url = _resolve_agent_url(body)
    from gateway.config_store import api_path, get_auth_url
    auth_url = get_auth_url(agent_url)
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.post(
                api_path(auth_url, "/user/email/login"),
                json={"email": email, "code": code, "username": username},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                data = await resp.json()
    except Exception as exc:
        return JSONResponse({
            "success": False,
            "message": f"登录失败：{exc}",
            "agent_url": agent_url,
        })

    if data.get("success") and data.get("token"):
        update_settings(
            agent_url=agent_url,
            agent_token=data["token"],
            agent_user_id=str(data.get("user_id", "")),
            agent_email=email,
            agent_login_mode="email",
        )

    data["agent_url"] = agent_url
    return JSONResponse(data)


# ---------------------------------------------------------------------------
# Agent SSO 登录（代理）
# ---------------------------------------------------------------------------

@app.post("/api/auth/sso/login")
async def api_sso_login(request: Request):
    """通过 ``user_id`` 走企业 SSO 登录。

    需要 Agent 端开启 ``ENABLE_SSO_LOGIN=true``，否则返回错误。
    """
    from gateway.config_store import update_settings
    try:
        body: Dict[str, Any] = await request.json()
    except Exception:
        return JSONResponse({"success": False, "message": "请求体不是合法 JSON"}, status_code=400)

    user_id = (body.get("user_id") or "").strip()
    username = (body.get("username") or "").strip() or None
    if not user_id:
        return JSONResponse({"success": False, "message": "请填写 user_id"})

    agent_url = _resolve_agent_url(body)
    from gateway.config_store import api_path
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.post(
                api_path(agent_url, "/user/sso-token"),
                json={"user_id": user_id, "username": username},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                data = await resp.json()
    except Exception as exc:
        return JSONResponse({
            "success": False,
            "message": f"调用 Agent 失败：{exc}",
            "agent_url": agent_url,
        })

    if data.get("success") and data.get("token"):
        update_settings(
            agent_url=agent_url,
            agent_token=data["token"],
            agent_user_id=str(data.get("user_id", user_id)),
            agent_email="",
            agent_login_mode="sso",
        )

    data["agent_url"] = agent_url
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


async def _reconnect_xiaoai() -> None:
    if _xiaoai_adapter is None:
        return
    try:
        if _xiaoai_adapter.is_connected:
            await _xiaoai_adapter.disconnect()
        loaded = _xiaoai_adapter.reload_credentials()
        if not loaded:
            logger.warning("[web] 重新加载小爱配置失败，无法重连")
            return
        ok = await _xiaoai_adapter.connect()
        if ok:
            logger.info("[web] 小爱音箱 adapter 已重新连接")
        else:
            logger.warning("[web] 小爱音箱 adapter 重连失败")
    except Exception as exc:
        logger.error("[web] 小爱音箱重连异常: %s", exc, exc_info=True)


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

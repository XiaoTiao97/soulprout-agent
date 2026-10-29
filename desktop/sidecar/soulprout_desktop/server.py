"""桌面端本地 HTTP 服务（只监听 127.0.0.1）。

桌面窗口加载的就是这个服务的页面。它做三件事：

1. 提供桌面界面的静态文件；
2. ``/api/*`` 反向代理到云端：注入登录凭证（界面代码不用碰 token）、桌面端创建的任务会话打上本地标签；
3. 本地会话的文件接口（文件列表 / 下载 / 预览 / 保存 / 上传）直接读写用户电脑上的工作区。

另外 ``/__desktop/*`` 是桌面端自己的控制接口（状态、权限预设、审批）。

安全：本服务能驱动本机文件和命令的审批，不能被别的网页或进程随便调用。
- 每次启动生成随机密钥，Tauri 用 ``/__boot?s=<密钥>`` 打开页面，服务端种下 HttpOnly + SameSite=Strict 的 cookie，
  之后所有请求必须带这个 cookie；
- 校验 Host（防 DNS 重绑定）和 Origin（防跨站请求）；
- 云端返回的 Set-Cookie 一律丢弃，登录凭证只存在本机状态目录里。
"""

from __future__ import annotations

import asyncio
import hmac
import json
import locale
import logging
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import uuid
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import quote, unquote, urlsplit

import aiohttp
from aiohttp import web

from . import __version__, auth_store, device, paths, policy, settings
from .approvals import ApprovalBroker
from .cloud_client import CloudClient
from .conversations import ConversationRouter

logger = logging.getLogger(__name__)

COOKIE_NAME = "soulprout_desktop"

mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("application/javascript", ".mjs")
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("image/svg+xml", ".svg")
mimetypes.add_type("application/wasm", ".wasm")

_HOP_BY_HOP = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailers",
    "transfer-encoding", "upgrade", "host", "content-length",
}
_DROP_REQUEST_HEADERS = _HOP_BY_HOP | {"cookie", "authorization", "origin", "referer", "accept-encoding"}
_DROP_RESPONSE_HEADERS = _HOP_BY_HOP - {"content-length"} | {"set-cookie"}

_LOGIN_PATHS = {"user/email/login", "user/sso-token", "user/guest"}

_CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".pdf": "application/pdf",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".ppt": "application/vnd.ms-powerpoint",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".xls": "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".jpg": "image/jpeg",
    ".png": "image/png",
    ".txt": "text/plain; charset=utf-8",
    ".md": "text/markdown; charset=utf-8",
    ".json": "application/json; charset=utf-8",
}


@dataclass
class AppContext:
    secret: str
    port: int
    broker: ApprovalBroker
    cloud: CloudClient
    gateway_info: Callable[[], Dict[str, Any]]
    ui_dir: Optional[Path] = None


def _decode_upload_filename(name: str) -> str:
    """把 multipart 文件名还原成原始 Unicode。

    aiohttp 默认会把非 ASCII 文件名百分号编码进 ``filename=``；浏览器发来的、或我们自己
    转发时若没关掉这段编码，云端 FastAPI 会把 ``%E4%B8%B4....txt`` 原样当文件名存下来。
    """
    text = (name or "").strip()
    if not text:
        return text
    # 只在整段都像百分号编码时才解码，避免误伤本身就含 % 的文件名
    if "%" in text:
        try:
            decoded = unquote(text, encoding="utf-8", errors="strict")
            if decoded != text:
                return decoded
        except Exception:
            pass
    return text


def _multipart_chat(payload: Dict[str, Any], files: List[Dict[str, Any]]) -> aiohttp.MultipartWriter:
    """始终按 multipart/form-data 组装（没有附件时 FormData 会退化成 urlencoded，与网页端发出的格式不一致）。

    文件名用 ``quote_fields=False``：按 UTF-8 原样写入 Content-Disposition，避免 aiohttp 默认
    把中文编成 ``%E4%B8%B4...``，而云端 FastAPI 又不会做反解。
    """
    writer = aiohttp.MultipartWriter("form-data")
    part = writer.append(json.dumps(payload, ensure_ascii=False), {"Content-Type": "text/plain; charset=utf-8"})
    part.set_content_disposition("form-data", name="chat_request")
    for item in files:
        part = writer.append(item["data"], {"Content-Type": item["content_type"]})
        part.set_content_disposition(
            "form-data", quote_fields=False, name="files", filename=item["filename"],
        )
    return writer


def json_error(status: int, message: str) -> web.Response:
    return web.json_response({"detail": message, "message": message, "success": False}, status=status)


# ---------------------------------------------------------------------------
# 中间件：Host / Origin / 启动密钥
# ---------------------------------------------------------------------------

def make_security_middleware(ctx: AppContext):
    allowed_hosts = {f"127.0.0.1:{ctx.port}", f"localhost:{ctx.port}"}
    allowed_origins = {f"http://{h}" for h in allowed_hosts}

    @web.middleware
    async def security(request: web.Request, handler):
        if request.headers.get("Host", "") not in allowed_hosts:
            return web.Response(status=403, text="forbidden host")
        origin = request.headers.get("Origin")
        if origin and origin not in allowed_origins:
            return web.Response(status=403, text="forbidden origin")
        if request.path == "/__boot":
            return await handler(request)
        cookie = request.cookies.get(COOKIE_NAME, "")
        if not cookie or not hmac.compare_digest(cookie, ctx.secret):
            return web.Response(status=401, text="unauthorized")
        return await handler(request)

    return security


# ---------------------------------------------------------------------------
# 云端请求
# ---------------------------------------------------------------------------

def upstream_headers(request: web.Request) -> Dict[str, str]:
    headers = {k: v for k, v in request.headers.items() if k.lower() not in _DROP_REQUEST_HEADERS}
    headers["Accept-Encoding"] = "identity"
    token = auth_store.get_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
        headers["Cookie"] = f"token={token}"
    return headers


def response_headers(upstream: aiohttp.ClientResponse) -> Dict[str, str]:
    return {k: v for k, v in upstream.headers.items() if k.lower() not in _DROP_RESPONSE_HEADERS}


class DesktopServer:
    def __init__(self, ctx: AppContext, conversations: Optional[ConversationRouter] = None):
        self.ctx = ctx
        self.convs = conversations or ConversationRouter(self._fetch_cloud_conversations)
        self.http: Optional[aiohttp.ClientSession] = None
        self.local_http: Optional[aiohttp.ClientSession] = None  # 访问本机 gateway：不走系统代理

    # ------------------------------------------------------------------ 装配

    def build_app(self) -> web.Application:
        app = web.Application(
            middlewares=[make_security_middleware(self.ctx)],
            client_max_size=512 * 1024 * 1024,
        )
        app.on_startup.append(self._on_startup)
        app.on_cleanup.append(self._on_cleanup)
        r = app.router
        r.add_get("/__boot", self.boot)
        r.add_get("/__desktop/state", self.state)
        r.add_post("/__desktop/policy", self.set_policy)
        r.add_get("/__desktop/approvals/stream", self.approvals_stream)
        r.add_post("/__desktop/approvals/{request_id}", self.approvals_decide)
        r.add_post("/__desktop/open-folder", self.open_folder)
        r.add_post("/__desktop/open-url", self.open_url)
        r.add_post("/__desktop/cloud", self.set_cloud)
        r.add_post("/__desktop/cloud/test", self.test_cloud)
        r.add_route("*", "/__gateway/{path:.*}", self.gateway_proxy)

        r.add_post("/api/message/chat", self.chat)
        r.add_get("/api/files", self.local_files)
        r.add_get("/api/download/{filename:.+}", self.local_download)
        r.add_get("/api/file_content/{filename:.+}", self.local_file_content)
        r.add_get("/api/export/{filename:.+}", self.local_export)
        r.add_post("/api/save_file/{filename:.+}", self.local_save_file)
        r.add_delete("/api/conversations/{conversation_id}", self.delete_conversation)
        r.add_post("/api/user/logout", self.logout)
        r.add_route("*", "/api/{path:.*}", self.proxy)

        r.add_get("/{path:.*}", self.static)
        return app

    async def _on_startup(self, app: web.Application) -> None:
        from gateway.chat_caller import _make_ssl_connector

        timeout = aiohttp.ClientTimeout(total=None, sock_connect=30, sock_read=None)
        self.http = aiohttp.ClientSession(
            timeout=timeout,
            connector=_make_ssl_connector(),
            trust_env=True,
            auto_decompress=False,
        )
        self.local_http = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60), trust_env=False)

    async def _on_cleanup(self, app: web.Application) -> None:
        if self.http is not None:
            await self.http.close()
        if self.local_http is not None:
            await self.local_http.close()

    # ------------------------------------------------------------------ 启动密钥 / 静态页面

    async def boot(self, request: web.Request) -> web.Response:
        secret = request.query.get("s", "")
        if not secret or not hmac.compare_digest(secret, self.ctx.secret):
            return web.Response(status=401, text="unauthorized")
        resp = web.HTTPFound("/")
        resp.set_cookie(COOKIE_NAME, self.ctx.secret, httponly=True, samesite="Strict", path="/")
        raise resp

    async def static(self, request: web.Request) -> web.StreamResponse:
        root = self.ctx.ui_dir or paths.ui_dist_dir()
        if not root.is_dir():
            return web.Response(status=503, text=f"桌面界面尚未构建：{root}")
        rel = request.match_info.get("path", "")
        candidate = (root / rel).resolve() if rel else root / "index.html"
        if candidate.is_file() and policy.is_path_under(str(candidate), str(root.resolve())):
            target = candidate
        else:
            target = root / "index.html"  # SPA 回退（vue-router history 模式）
        headers = {"Cache-Control": "no-cache" if target.name == "index.html" else "public, max-age=31536000, immutable"}
        return web.FileResponse(target, headers=headers)

    # ------------------------------------------------------------------ /__desktop

    async def state(self, request: web.Request) -> web.Response:
        standing = policy.standing_for(settings.preset())
        cloud = self.ctx.cloud
        return web.json_response({
            "version": __version__,
            "device": {"id": settings.device_id(), "name": settings.device_name(), "info": device.device_info()},
            "cloud": {
                "url": auth_store.agent_url(),
                "default_url": auth_store.default_agent_url(),
                "custom": auth_store.is_custom_agent_url(),
                "locked": False,
                "state": cloud.state,
                "online": cloud.connected,
                "logged_in": auth_store.is_logged_in(),
                "error": cloud.last_error,
            },
            "policy": {
                "preset": standing.preset,
                "mode": standing.mode,
                "approval": standing.approval,
                "presets": [
                    {"name": p.name, "label": p.label, "description": p.description, "danger": p.name == policy.DANGER_FULL_ACCESS}
                    for p in policy.PRESETS.values()
                ],
            },
            "approvals": self.ctx.broker.pending(),
            "gateway": self.ctx.gateway_info(),
            "paths": {"workspaces": str(paths.workspaces_root())},
        })

    async def set_policy(self, request: web.Request) -> web.Response:
        try:
            body = await request.json()
        except Exception:
            return json_error(400, "invalid json")
        name = str((body or {}).get("preset") or "")
        if name not in policy.PRESETS:
            return json_error(400, "unknown preset")
        settings.set_preset(name)
        return web.json_response({"success": True, "preset": name})

    @staticmethod
    def _clean_cloud_url(raw: Any) -> Optional[str]:
        """校验用户填的云端地址；空串表示「官方云服务」，非法返回 None。"""
        value = str(raw or "").strip().rstrip("/")
        if not value:
            return ""
        parsed = urlsplit(value)
        if parsed.scheme not in ("http", "https") or not parsed.netloc or parsed.query or parsed.fragment:
            return None
        return value

    async def set_cloud(self, request: web.Request) -> web.Response:
        """切换云端服务（官方 / 自定义，例如本机开发服务）。换了服务器就要重新登录。"""
        try:
            body = await request.json()
        except Exception:
            return json_error(400, "invalid json")
        value = self._clean_cloud_url((body or {}).get("url"))
        if value is None:
            return json_error(400, "地址格式不对，应类似 https://example.com 或 http://localhost:8080")
        if value and value.lower() == auth_store.default_agent_url().rstrip("/").lower():
            value = ""  # 填的就是官方地址：按「默认」记，以后官方换域名时不用用户操作
        changed = (value or auth_store.default_agent_url()).rstrip("/") != auth_store.agent_url().rstrip("/")
        if changed:
            auth_store.set_agent_url(value or None)
            self.convs.invalidate()
            await self.ctx.cloud.disconnect()
            self.ctx.cloud.poke()
        return web.json_response({
            "success": True,
            "changed": changed,
            "url": auth_store.agent_url(),
            "custom": auth_store.is_custom_agent_url(),
        })

    async def test_cloud(self, request: web.Request) -> web.Response:
        """只测试地址能不能连上，不保存任何东西。"""
        try:
            body = await request.json()
        except Exception:
            return json_error(400, "invalid json")
        value = self._clean_cloud_url((body or {}).get("url"))
        if value is None:
            return json_error(400, "地址格式不对")
        target = value or auth_store.default_agent_url()
        try:
            async with self.http.get(
                auth_store.api_url("/health", base=target),
                timeout=aiohttp.ClientTimeout(total=8),
                allow_redirects=False,
            ) as resp:
                await resp.read()
                ok = resp.status < 500  # /health 不存在（404）也说明服务在
        except Exception as exc:
            return web.json_response({"success": False, "message": f"无法连接：{exc}"})
        return web.json_response({"success": ok, "message": "" if ok else f"服务返回 HTTP {resp.status}"})

    # 多端互联（gateway）只开放渠道相关的接口；gateway 里的登录 / 地址设置接口在桌面端由本进程自己管，不对界面开放
    _GATEWAY_ALLOWED = ("api/weixin/", "api/feishu/", "api/wecom/", "api/xiaoai/", "api/rokid/")

    async def gateway_proxy(self, request: web.Request) -> web.Response:
        path = request.match_info.get("path", "")
        if not path.startswith(self._GATEWAY_ALLOWED):
            return json_error(403, "forbidden")
        info = self.ctx.gateway_info() or {}
        base = info.get("url")
        if not info.get("enabled") or not base:
            return json_error(503, "多端互联未启用")
        if self.local_http is None:
            return json_error(503, "not ready")
        headers = {}
        if request.headers.get("Content-Type"):
            headers["Content-Type"] = request.headers["Content-Type"]
        data = await request.read() if request.method not in ("GET", "HEAD") else None
        try:
            async with self.local_http.request(
                request.method, base.rstrip("/") + "/" + path, params=request.query, data=data, headers=headers
            ) as upstream:
                body = await upstream.read()
                return web.Response(
                    status=upstream.status,
                    body=body,
                    content_type=(upstream.content_type or "application/json"),
                    charset="utf-8" if (upstream.content_type or "").startswith(("application/json", "text/")) else None,
                )
        except aiohttp.ClientError as exc:
            return json_error(502, f"多端互联服务没有响应：{exc}")

    async def approvals_stream(self, request: web.Request) -> web.StreamResponse:
        resp = web.StreamResponse(headers={
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        })
        await resp.prepare(request)
        queue = self.ctx.broker.subscribe()
        try:
            await resp.write(b": ok\n\n")
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                except asyncio.TimeoutError:
                    await resp.write(b": ping\n\n")
                    continue
                await resp.write(f"data: {json.dumps(event, ensure_ascii=False)}\n\n".encode("utf-8"))
        except (ConnectionResetError, asyncio.CancelledError):
            pass
        finally:
            self.ctx.broker.unsubscribe(queue)
        return resp

    async def approvals_decide(self, request: web.Request) -> web.Response:
        try:
            body = await request.json()
        except Exception:
            return json_error(400, "invalid json")
        ok = self.ctx.broker.decide(request.match_info["request_id"], str((body or {}).get("decision") or "reject"))
        return web.json_response({"success": ok})

    async def open_folder(self, request: web.Request) -> web.Response:
        target = paths.workspaces_root()
        target.mkdir(parents=True, exist_ok=True)
        try:
            if sys.platform == "win32":
                os.startfile(str(target))  # type: ignore[attr-defined]  # noqa: S606
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(target)])
            else:
                subprocess.Popen(["xdg-open", str(target)])
        except Exception as exc:
            return json_error(500, f"无法打开文件夹：{exc}")
        return web.json_response({"success": True})

    async def open_url(self, request: web.Request) -> web.Response:
        """用系统默认浏览器打开官网产品文档。"""
        try:
            body = await request.json()
        except Exception:
            return json_error(400, "invalid json")
        parsed = urlsplit(str((body or {}).get("url") or "").strip())
        host = parsed.netloc.lower()
        if parsed.scheme != "https" or host not in ("www.soulprout.com", "soulprout.com") or not (parsed.path or "/").startswith("/docs"):
            return json_error(400, "只能打开官网文档")
        url = f"https://www.soulprout.com{parsed.path or '/docs'}"
        if parsed.query:
            url += f"?{parsed.query}"
        try:
            webbrowser.open(url)
        except Exception as exc:
            return json_error(500, f"无法打开网页：{exc}")
        return web.json_response({"success": True})

    # ------------------------------------------------------------------ 云端代理

    async def _fetch_cloud_conversations(self) -> Optional[List[Dict[str, Any]]]:
        token = auth_store.get_token()
        if not token or self.http is None:
            return None
        async with self.http.get(
            auth_store.api_url("/conversations"),
            headers={"Authorization": f"Bearer {token}", "Cookie": f"token={token}", "Accept-Encoding": "identity"},
        ) as resp:
            if resp.status != 200:
                return None
            data = await resp.json(content_type=None)
            return data if isinstance(data, list) else None

    async def proxy(self, request: web.Request) -> web.StreamResponse:
        """通用反向代理：流式透传请求体和响应体（SSE 也走这里），丢弃云端的 Set-Cookie。"""
        path = request.match_info["path"]
        url = auth_store.api_url("/" + path)
        has_body = request.method not in ("GET", "HEAD", "OPTIONS") and request.can_read_body
        try:
            upstream = await self.http.request(
                request.method,
                url,
                params=request.query,
                headers=upstream_headers(request),
                data=request.content if has_body else None,
                allow_redirects=False,
            )
        except aiohttp.ClientError as exc:
            return json_error(502, f"无法连接云端服务：{exc}")
        async with upstream:
            if path in _LOGIN_PATHS and request.method == "POST":
                return await self._finish_login(upstream)
            return await self._stream_back(request, upstream)

    async def _stream_back(self, request: web.Request, upstream: aiohttp.ClientResponse) -> web.StreamResponse:
        resp = web.StreamResponse(status=upstream.status, headers=response_headers(upstream))
        await resp.prepare(request)
        try:
            async for chunk in upstream.content.iter_any():
                await resp.write(chunk)
            await resp.write_eof()
        except (ConnectionResetError, asyncio.CancelledError):
            upstream.close()  # 界面侧断开：停止拉取；云端的运行不受影响（与网页端一致）
        return resp

    async def _finish_login(self, upstream: aiohttp.ClientResponse) -> web.Response:
        raw = await upstream.read()
        headers = response_headers(upstream)
        headers.pop("Content-Length", None)
        headers.pop("Content-Encoding", None)
        try:
            body = json.loads(raw.decode("utf-8"))
        except Exception:
            return web.Response(status=upstream.status, body=raw, headers=headers)
        if isinstance(body, dict) and body.get("success") and body.get("token"):
            auth_store.save_login(
                token=str(body["token"]),
                user_id=str(body.get("user_id") or ""),
                email=str(body.get("email") or ""),
            )
            self.convs.invalidate()
            self.ctx.cloud.poke()
            body.pop("token", None)  # 界面不需要拿到 token
        return web.json_response(body, status=upstream.status, headers={k: v for k, v in headers.items() if k.lower() != "content-type"})

    async def logout(self, request: web.Request) -> web.Response:
        try:
            if self.http is not None and auth_store.is_logged_in():
                async with self.http.post(auth_store.api_url("/user/logout"), headers=upstream_headers(request)) as resp:
                    await resp.read()
        except Exception as exc:
            logger.info("云端登出调用失败（忽略）: %s", exc)
        auth_store.clear_login()
        self.convs.invalidate()
        await self.ctx.cloud.disconnect()
        self.ctx.cloud.poke()
        return web.json_response({"message": "logged out"})

    # ------------------------------------------------------------------ 聊天：本地会话打标签 + 本地保存附件

    async def chat(self, request: web.Request) -> web.StreamResponse:
        payload: Dict[str, Any] = {}
        files: List[Dict[str, Any]] = []
        try:
            reader = await request.multipart()
            async for part in reader:
                if part.name == "chat_request":
                    payload = json.loads((await part.read()).decode("utf-8"))
                elif part.name == "files" and part.filename:
                    files.append({
                        "filename": _decode_upload_filename(part.filename),
                        "content_type": part.headers.get("Content-Type", "application/octet-stream"),
                        "data": bytes(await part.read()),
                    })
        except Exception as exc:
            return json_error(400, f"无法解析聊天请求：{exc}")
        if not isinstance(payload, dict):
            return json_error(400, "invalid chat_request")

        payload["client"] = "desktop"
        local_names: List[str] = []
        send_files = files
        if payload.get("agent_use") != "soulprout":
            cid = str(payload.get("conversation_id") or "").strip()
            if not cid:
                cid = uuid.uuid4().hex  # 桌面端自己分配，附件要先落到这个会话的本地工作区
                payload["conversation_id"] = cid
            if paths.is_valid_conversation_id(cid) and await self.convs.is_local(cid, creating_ok=True):
                self.convs.mark_local(cid)
                payload["workspace"] = "local"
                payload["device_id"] = settings.device_id()
                payload["device_name"] = settings.device_name()
                if files:
                    local_names = await asyncio.to_thread(self._save_uploads, cid, files)
                    payload["file_name_list"] = local_names
                    send_files = []  # 附件留在本机，不再传给云端

        form = _multipart_chat(payload, send_files)
        headers = upstream_headers(request)
        for key in list(headers):
            if key.lower() in ("content-type", "content-length"):
                headers.pop(key)
        try:
            upstream = await self.http.post(auth_store.api_url("/message/chat"), data=form, headers=headers, allow_redirects=False)
        except aiohttp.ClientError as exc:
            return json_error(502, f"无法连接云端服务：{exc}")
        async with upstream:
            return await self._stream_back(request, upstream)

    @staticmethod
    def _save_uploads(conversation_id: str, files: List[Dict[str, Any]]) -> List[str]:
        workspace = paths.workspace_dir(conversation_id)
        workspace.mkdir(parents=True, exist_ok=True)
        saved: List[str] = []
        for item in files:
            name = os.path.basename(_decode_upload_filename(str(item["filename"])).replace("\\", "/")).strip()
            if not name or name in (".", ".."):
                continue
            try:
                (workspace / name).write_bytes(item["data"])
                saved.append(name)
            except OSError as exc:
                logger.warning("保存上传文件失败 %s: %s", name, exc)
        return saved

    # ------------------------------------------------------------------ 本地会话的文件接口（与云端 tools.py 对应）

    async def _local_target(self, request: web.Request, conversation_id: Optional[str]):
        """返回本地会话的工作区目录；不是本地会话则返回 None（交给云端代理）。"""
        cid = (conversation_id or "").strip()
        if not cid or not paths.is_valid_conversation_id(cid):
            return None
        if not await self.convs.is_local(cid, creating_ok=False):
            return None
        return paths.workspace_dir(cid)

    @staticmethod
    def _resolve_in(workspace: Path, filename: str) -> Optional[Path]:
        # 路径参数可能被 URL 编码过一次；再解一次，避免中文文件名对不上
        rel = _decode_upload_filename(filename).replace("\\", "/").lstrip("/")
        target = (workspace / rel).resolve()
        root = workspace.resolve()
        if target != root and not policy.is_path_under(str(target), str(root)):
            return None
        return target

    async def local_files(self, request: web.Request) -> web.StreamResponse:
        workspace = await self._local_target(request, request.query.get("conversation_id"))
        if workspace is None:
            return await self.proxy_path(request, "files")
        result: List[str] = []
        if workspace.is_dir():
            for dirpath, _dirs, names in os.walk(workspace):
                for name in names:
                    result.append((Path(dirpath) / name).relative_to(workspace).as_posix())
        result.sort()
        return web.json_response({"files": result})

    async def local_download(self, request: web.Request) -> web.StreamResponse:
        filename = request.match_info["filename"]
        workspace = await self._local_target(request, request.query.get("conversation_id"))
        if workspace is None:
            return await self.proxy_path(request, f"download/{filename}")
        target = self._resolve_in(workspace, filename)
        if target is None or not target.is_file():
            return json_error(404, "File not found")
        return web.FileResponse(target, headers={
            "Content-Type": "application/octet-stream",
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(target.name)}",
        })

    async def local_file_content(self, request: web.Request) -> web.StreamResponse:
        filename = request.match_info["filename"]
        workspace = await self._local_target(request, request.query.get("conversation_id"))
        if workspace is None:
            return await self.proxy_path(request, f"file_content/{filename}")
        target = self._resolve_in(workspace, filename)
        if target is None or not target.is_file():
            return json_error(404, "File not found")
        content_type = _CONTENT_TYPES.get(target.suffix.lower(), "application/octet-stream")
        # 文本类文件显式按 UTF-8 读出再返回：Windows 上 FileResponse 偶发按系统默认编码猜测，
        # 前端 blob.text() 又固定按 UTF-8 解，两边不一致就会把中文预览成乱码。
        if "charset=utf-8" in content_type:
            try:
                body = target.read_bytes()
            except OSError:
                return json_error(500, "Internal server error")
            # 不是合法 UTF-8 时按系统默认编码（中文 Windows 多为 gb18030）转成 UTF-8 再给前端
            try:
                body.decode("utf-8")
            except UnicodeDecodeError:
                body = body.decode(locale.getpreferredencoding(False) or "utf-8", errors="replace").encode("utf-8")
            return web.Response(
                body=body,
                headers={
                    "Content-Type": content_type,
                    "Content-Disposition": f"inline; filename*=UTF-8''{quote(target.name)}",
                },
            )
        return web.FileResponse(target, headers={
            "Content-Type": content_type,
            "Content-Disposition": f"inline; filename*=UTF-8''{quote(target.name)}",
        })

    async def local_export(self, request: web.Request) -> web.StreamResponse:
        filename = request.match_info["filename"]
        workspace = await self._local_target(request, request.query.get("conversation_id"))
        if workspace is None:
            return await self.proxy_path(request, f"export/{filename}")
        return json_error(501, "本地会话暂不支持导出为 PDF / PPTX，请直接在本地工作区文件夹中使用该文件。")

    async def local_save_file(self, request: web.Request) -> web.StreamResponse:
        filename = request.match_info["filename"]
        form = await request.post()
        workspace = await self._local_target(request, str(form.get("conversation_id") or ""))
        if workspace is None:
            # 已经读过请求体，需要用读到的内容重新组装后转发
            data = aiohttp.FormData()
            for key in form:
                data.add_field(key, str(form[key]))
            headers = upstream_headers(request)
            for key in list(headers):
                if key.lower() in ("content-type", "content-length"):
                    headers.pop(key)
            try:
                upstream = await self.http.post(auth_store.api_url(f"/save_file/{filename}"), data=data, headers=headers, allow_redirects=False)
            except aiohttp.ClientError as exc:
                return json_error(502, f"无法连接云端服务：{exc}")
            async with upstream:
                return await self._stream_back(request, upstream)
        target = self._resolve_in(workspace, filename)
        if target is None:
            return json_error(400, "invalid filename path")
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(str(form.get("file_content") or ""), encoding="utf-8")
        except OSError:
            return json_error(500, "Internal server error")
        return web.json_response({"message": "保存成功", "filename": filename})

    async def proxy_path(self, request: web.Request, path: str) -> web.StreamResponse:
        """把当前请求按给定的云端路径转发（本地接口判定为「不是本地会话」时用）。"""
        url = auth_store.api_url("/" + path)
        try:
            upstream = await self.http.request(
                request.method, url, params=request.query, headers=upstream_headers(request), allow_redirects=False
            )
        except aiohttp.ClientError as exc:
            return json_error(502, f"无法连接云端服务：{exc}")
        async with upstream:
            return await self._stream_back(request, upstream)

    async def delete_conversation(self, request: web.Request) -> web.StreamResponse:
        cid = request.match_info["conversation_id"]
        was_local = await self.convs.is_local(cid, creating_ok=False)
        try:
            upstream = await self.http.delete(
                auth_store.api_url(f"/conversations/{quote(cid)}"), headers=upstream_headers(request), allow_redirects=False
            )
        except aiohttp.ClientError as exc:
            return json_error(502, f"无法连接云端服务：{exc}")
        async with upstream:
            if was_local and upstream.status < 300 and paths.is_valid_conversation_id(cid):
                shutil.rmtree(paths.workspace_dir(cid), ignore_errors=True)
                self.convs.forget(cid)
            return await self._stream_back(request, upstream)

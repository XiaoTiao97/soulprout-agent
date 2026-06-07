"""
小米 MiNA 云端 API 客户端（免刷机小爱接入）。

实现参考 migpt-next 的 @mi-gpt/miot 包，仅保留 Soulprout 轻量化接入所需能力：
- 小米账号登录（micoapi）
- 设备匹配（did）
- 对话历史轮询
- 远程 TTS 播报（mibrain text_to_speech）
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote, urlencode

logger = logging.getLogger(__name__)

LOGIN_API = "https://account.xiaomi.com/pass"
MINA_API = "https://api2.mina.mi.com"
CONVERSATION_API = "https://userprofile.mina.mi.com/device_profile/v2/conversation"

_DEFAULT_UA = (
    "Dalvik/2.1.0 (Linux; U; Android 10; RMX2111 Build/QP1A.190711.020) "
    "APP/xiaomi.mico APPV/2004040 MK/Uk1YMjIxMQ== PassportSDK/3.8.3 passport-ui/3.8.3"
)
_MINA_UA = "MICO/AndroidApp/@SHIP.TO.2A2FE0D7@/2.4.40"
_CONV_UA = (
    "Mozilla/5.0 (Linux; Android 10; 000; wv) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Version/4.0 Chrome/119.0.6045.193 Mobile Safari/537.36 "
    "/XiaoMi/HybridView/ micoSoundboxApp/i appVersion/A_2.4.40"
)

_GATEWAY_ROOT = Path(__file__).resolve().parent.parent.parent
XIAOAI_DATA_DIR = _GATEWAY_ROOT / "gateway_data" / "xiaoai"
XIAOAI_CONFIG_PATH = XIAOAI_DATA_DIR / "config.json"
XIAOAI_SESSION_PATH = XIAOAI_DATA_DIR / ".mi.json"


def _json_write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _json_read(path: Path) -> Optional[dict]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _md5_hex(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def _sha1_b64(text: str) -> str:
    import base64
    return base64.b64encode(hashlib.sha1(text.encode("utf-8")).digest()).decode("ascii")


def _encode_query(data: Dict[str, Any]) -> str:
    parts = []
    for key, value in data.items():
        if value is None:
            value = ""
        parts.append(f"{quote(str(key), safe='')}={quote(str(value), safe='')}")
    return "&".join(parts)


def _parse_auth_pass(text: str) -> Dict[str, Any]:
    if not text:
        return {}
    cleaned = text.replace("&&&START&&&", "")
    cleaned = re.sub(r":(\d{9,})", r':"\1"', cleaned)
    try:
        return json.loads(cleaned) or {}
    except json.JSONDecodeError:
        return {}


def _cookie_header(cookies: Dict[str, Any]) -> str:
    parts = []
    for key, value in cookies.items():
        if value is None or value == "":
            continue
        parts.append(f"{key}={value};")
    return " ".join(parts)


@dataclass
class MiDevice:
    device_id: str = ""
    name: str = ""
    hardware: str = ""
    serial_number: str = ""
    device_sn_profile: str = ""


@dataclass
class MiAccount:
    user_id: str
    password: str = ""
    pass_token: str = ""
    did: str = ""
    device_id: str = ""
    service_token: str = ""
    pass_data: Dict[str, Any] = field(default_factory=dict)
    device: Optional[MiDevice] = None
    sid: str = "micoapi"


@dataclass
class ConversationMessage:
    query: str
    timestamp: int
    answer_type: str = ""


class MiNAClient:
    def __init__(self, account: MiAccount, *, timeout: float = 10.0):
        self.account = account
        self._timeout = timeout

    @property
    def device_name(self) -> str:
        if self.account.device:
            return self.account.device.name or self.account.did
        return self.account.did

    async def play_text(self, text: str) -> bool:
        payload = json.dumps({"text": text, "save": 0}, ensure_ascii=False)
        res = await self._call_mina(
            "POST",
            "/remote/ubus",
            {
                "deviceId": self.account.device.device_id if self.account.device else "",
                "path": "mibrain",
                "method": "text_to_speech",
                "message": payload,
            },
        )
        if not isinstance(res, dict):
            logger.warning("[xiaoai] TTS 失败: %s", res)
            return False
        if res.get("code") == 0:
            return True
        logger.warning("[xiaoai] TTS 失败: %s", res)
        return False

    async def get_conversations(
        self,
        *,
        limit: int = 10,
        timestamp: Optional[int] = None,
    ) -> List[ConversationMessage]:
        params: Dict[str, Any] = {
            "limit": limit,
            "requestId": str(uuid.uuid4()),
            "source": "dialogu",
            "hardware": self.account.device.hardware if self.account.device else "",
        }
        if timestamp is not None:
            params["timestamp"] = timestamp

        try:
            import aiohttp
        except ImportError:
            logger.error("[xiaoai] aiohttp 未安装")
            return []

        cookies = {
            "userId": self.account.user_id,
            "serviceToken": self.account.service_token,
            "deviceId": self.account.device.device_id if self.account.device else "",
        }
        headers = {
            "User-Agent": _CONV_UA,
            "Referer": "https://userprofile.mina.mi.com/dialogue-note/index.html",
            "Cookie": _cookie_header(cookies),
        }
        timeout = aiohttp.ClientTimeout(total=self._timeout)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(CONVERSATION_API, params=params, headers=headers) as resp:
                if resp.status == 401:
                    raise PermissionError("小米登录凭证已过期")
                body = await resp.json(content_type=None)
        if not isinstance(body, dict) or body.get("code") != 0:
            logger.warning("[xiaoai] 拉取对话历史失败: %s", body)
            return []

        data = body.get("data")
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except json.JSONDecodeError:
                return []
        records = (data or {}).get("records") or []
        messages: List[ConversationMessage] = []
        for record in records:
            answers = record.get("answers") or []
            if not answers:
                continue
            answer = answers[0] or {}
            if answer.get("type") not in {"TTS", "LLM"}:
                continue
            if len(answers) != 1:
                continue
            query = str(record.get("query") or "").strip()
            if not query:
                continue
            messages.append(
                ConversationMessage(
                    query=query,
                    timestamp=int(record.get("time") or 0),
                    answer_type=str(answer.get("type") or ""),
                )
            )
        return messages

    async def _call_mina(self, method: str, path: str, data: Optional[Dict[str, Any]] = None) -> Any:
        try:
            import aiohttp
        except ImportError:
            return None

        payload = {
            **(data or {}),
            "requestId": str(uuid.uuid4()),
            "timestamp": int(__import__("time").time()),
        }
        url = f"{MINA_API}{path}"
        cookies = {
            "userId": self.account.user_id,
            "serviceToken": self.account.service_token,
            "sn": self.account.device.serial_number if self.account.device else "",
            "hardware": self.account.device.hardware if self.account.device else "",
            "deviceId": self.account.device.device_id if self.account.device else "",
            "deviceSNProfile": self.account.device.device_sn_profile if self.account.device else "",
        }
        headers = {
            "User-Agent": _MINA_UA,
            "Content-Type": "application/x-www-form-urlencoded",
            "Cookie": _cookie_header(cookies),
        }
        timeout = aiohttp.ClientTimeout(total=self._timeout)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            if method == "GET":
                async with session.get(url, params=payload, headers=headers) as resp:
                    if resp.status == 401:
                        raise PermissionError("小米登录凭证已过期")
                    body = await resp.json(content_type=None)
            else:
                body = _encode_query(payload)
                async with session.post(url, data=body, headers=headers) as resp:
                    if resp.status == 401:
                        raise PermissionError("小米登录凭证已过期")
                    body = await resp.json(content_type=None)
        if not isinstance(body, dict):
            return body
        if body.get("code") != 0:
            logger.debug("[xiaoai] MiNA 调用失败 path=%s body=%s", path, body)
            return None
        return body.get("data")

    @staticmethod
    async def _get_device_list(account: MiAccount, *, timeout: float = 10.0) -> List[Dict[str, Any]]:
        client = MiNAClient(account, timeout=timeout)
        res = await client._call_mina("GET", "/admin/v2/device_list")
        if isinstance(res, list):
            return res
        return []


async def login_mina(
    *,
    user_id: str,
    password: str = "",
    pass_token: str = "",
    did: str,
    relogin: bool = False,
    timeout: float = 10.0,
) -> Optional[MiNAClient]:
    """登录小米账号并绑定指定 did 的 MiNA 设备。"""
    if not user_id or not did:
        logger.error("[xiaoai] 缺少 user_id 或 did")
        return None
    if not pass_token and not password:
        logger.error("[xiaoai] 缺少 password 或 pass_token")
        return None

    store = _json_read(XIAOAI_SESSION_PATH) or {}
    cached = store.get("mina") or {}
    device_id = cached.get("deviceId") or f"android_{uuid.uuid4()}"

    account = MiAccount(
        user_id=str(user_id),
        password=password,
        pass_token=pass_token or str(cached.get("passToken") or ""),
        did=did,
        device_id=device_id,
        service_token=str(cached.get("serviceToken") or ""),
        pass_data=dict(cached.get("pass") or {}),
    )

    if relogin or not account.service_token:
        logged_in = await _perform_login(account, timeout=timeout)
        if not logged_in:
            return None
        store["mina"] = _account_to_store(account)
        _json_write(XIAOAI_SESSION_PATH, store)

    device = await _resolve_device(account, timeout=timeout)
    if not device:
        logger.error("[xiaoai] 找不到设备 did=%r，请检查米家中的设备名称", did)
        return None
    account.device = device
    return MiNAClient(account, timeout=timeout)


async def test_mina_login(
    *,
    user_id: str,
    password: str = "",
    pass_token: str = "",
    did: str,
    timeout: float = 10.0,
) -> Dict[str, Any]:
    client = await login_mina(
        user_id=user_id,
        password=password,
        pass_token=pass_token,
        did=did,
        relogin=True,
        timeout=timeout,
    )
    if client is None:
        return {"success": False, "message": "登录失败，请检查账号、密码或 passToken"}
    return {
        "success": True,
        "message": f"登录成功，已匹配设备：{client.device_name}",
        "device_name": client.device_name,
        "device_id": client.account.device.device_id if client.account.device else "",
    }


async def _perform_login(account: MiAccount, *, timeout: float) -> bool:
    try:
        import aiohttp
    except ImportError:
        logger.error("[xiaoai] aiohttp 未安装")
        return False

    cookies = {
        "userId": account.user_id,
        "deviceId": account.device_id,
        "passToken": account.pass_token or account.pass_data.get("passToken") or "",
    }
    headers = {
        "User-Agent": _DEFAULT_UA,
        "Content-Type": "application/x-www-form-urlencoded",
        "Cookie": _cookie_header(cookies),
    }
    timeout_cfg = aiohttp.ClientTimeout(total=timeout)

    async with aiohttp.ClientSession(timeout=timeout_cfg) as session:
        params = {"sid": account.sid, "_json": "true", "_locale": "zh_CN"}
        async with session.get(f"{LOGIN_API}/serviceLogin", params=params, headers=headers) as resp:
            text = await resp.text()
        pass_data = _parse_auth_pass(text)
        if pass_data.get("isError"):
            logger.error("[xiaoai] 登录失败: %s", pass_data)
            return False

        if pass_data.get("code") != 0:
            if not account.password:
                logger.error("[xiaoai] 登录态失效且未提供 password")
                return False
            auth_body = _encode_query({
                "_json": "true",
                "qs": pass_data.get("qs", ""),
                "sid": account.sid,
                "_sign": pass_data.get("_sign", ""),
                "callback": pass_data.get("callback", ""),
                "user": account.user_id,
                "hash": _md5_hex(account.password).upper(),
            })
            async with session.post(
                f"{LOGIN_API}/serviceLoginAuth2",
                data=auth_body,
                headers=headers,
            ) as resp:
                text = await resp.text()
            pass_data = _parse_auth_pass(text)
            if pass_data.get("isError"):
                logger.error("[xiaoai] OAuth2 登录失败: %s", pass_data)
                return False

        notification_url = str(pass_data.get("notificationUrl") or "")
        if "identity/authStart" in notification_url:
            logger.error(
                "[xiaoai] 登录需要验证码，请配置 passToken。"
                "教程: https://github.com/idootop/migpt-next/issues/4"
            )
            return False

        location = pass_data.get("location")
        nonce = pass_data.get("nonce")
        pass_token = pass_data.get("passToken")
        ssecurity = pass_data.get("ssecurity")
        if not location or not nonce or not pass_token or not ssecurity:
            logger.error("[xiaoai] 登录响应不完整: %s", pass_data)
            return False

        client_sign = _sha1_b64(f"nonce={nonce}&{ssecurity}")
        async with session.get(
            str(location),
            params={"_userIdNeedEncrypt": "true", "clientSign": client_sign},
            headers=headers,
            allow_redirects=True,
        ) as resp:
            service_token = ""
            for cookie in resp.headers.getall("Set-Cookie", []):
                if "serviceToken=" in cookie:
                    service_token = cookie.split("serviceToken=")[1].split(";")[0]
                    break

        if not service_token:
            logger.error("[xiaoai] 获取 serviceToken 失败")
            return False

        account.service_token = service_token
        account.pass_token = str(pass_token)
        account.pass_data = pass_data
        return True


async def _resolve_device(account: MiAccount, *, timeout: float) -> Optional[MiDevice]:
    devices = await MiNAClient._get_device_list(account, timeout=timeout)
    for item in devices:
        candidates = [
            item.get("deviceID"),
            item.get("miotDID"),
            item.get("name"),
            item.get("alias"),
            item.get("mac"),
        ]
        if account.did not in candidates:
            continue
        return MiDevice(
            device_id=str(item.get("deviceID") or ""),
            name=str(item.get("name") or item.get("alias") or account.did),
            hardware=str(item.get("hardware") or ""),
            serial_number=str(item.get("serialNumber") or ""),
            device_sn_profile=str(item.get("deviceSNProfile") or ""),
        )
    return None


def _account_to_store(account: MiAccount) -> dict:
    return {
        "userId": account.user_id,
        "deviceId": account.device_id,
        "serviceToken": account.service_token,
        "passToken": account.pass_token,
        "pass": account.pass_data,
        "did": account.did,
        "sid": account.sid,
    }


def load_xiaoai_config() -> Optional[dict]:
    cfg = _json_read(XIAOAI_CONFIG_PATH)
    if cfg:
        return cfg
    user_id = os.getenv("XIAOMI_USER_ID", "").strip()
    password = os.getenv("XIAOMI_PASSWORD", "").strip()
    pass_token = os.getenv("XIAOMI_PASS_TOKEN", "").strip()
    did = os.getenv("XIAOMI_DID", "").strip()
    if user_id and did and (password or pass_token):
        return {
            "user_id": user_id,
            "password": password,
            "pass_token": pass_token,
            "did": did,
        }
    return None


def save_xiaoai_config(
    *,
    user_id: str,
    did: str,
    password: str = "",
    pass_token: str = "",
    call_ai_keywords: Optional[List[str]] = None,
    heartbeat_ms: int = 1000,
    debug: bool = False,
) -> None:
    existing = _json_read(XIAOAI_CONFIG_PATH) or {}
    data = {
        "user_id": user_id.strip(),
        "did": did.strip(),
        "password": password if password else str(existing.get("password") or ""),
        "pass_token": pass_token if pass_token else str(existing.get("pass_token") or ""),
        "call_ai_keywords": call_ai_keywords if call_ai_keywords is not None else existing.get(
            "call_ai_keywords", ["请", "你"]
        ),
        "heartbeat_ms": max(1000, int(heartbeat_ms or existing.get("heartbeat_ms") or 1000)),
        "debug": bool(debug),
    }
    _json_write(XIAOAI_CONFIG_PATH, data)


def has_xiaoai_config() -> bool:
    cfg = load_xiaoai_config()
    if not cfg:
        return False
    user_id = str(cfg.get("user_id") or "").strip()
    did = str(cfg.get("did") or "").strip()
    password = str(cfg.get("password") or "").strip()
    pass_token = str(cfg.get("pass_token") or "").strip()
    return bool(user_id and did and (password or pass_token))


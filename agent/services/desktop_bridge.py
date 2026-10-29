"""桌面端接入云端 Agent 的「胶水层」。

把桌面端相关的差异集中在这一个文件里，现有 Agent 主流程只在几个点上调用这里的函数：

1. ``adapt_tools``          —— 给模型看的工具定义：本地会话 / 灵芽模式下，为 read/write/edit/read_picture/bash
                               补上 ``target`` 与沙盒升级参数，并按设备系统改写描述。其它会话原样返回。
2. ``route_local_tool``     —— 工具真正执行前判断去云端还是去用户电脑，本地的转发给 ``desktop_hub``。
3. ``prepare_request``      —— 聊天请求进来时校验 workspace=local 的合法性。
4. ``device_prompt_section``—— 灵芽模式系统提示词里的设备状态（桌面端在线/离线始终显示，其他渠道仅在线时显示）。
5. ``source_header``        —— 灵芽模式下附在每条用户消息前的精简来源行：``Source: Wechat 2026-10-29 11:15 Thu``。

设计要点：
- 工作区标签（cloud/local）在会话创建时确定、之后不变；本地任务会话的所有本地类工具都发往桌面端。
- 灵芽模式的会话永远是同一个（conversation_id == user_id），由模型通过 ``target`` 参数自己选云端还是本地。
- 设备在线与否不会改变工具定义（只改系统提示词里的状态行），因此不影响工具前缀的缓存。
- 环境变量 ``DESKTOP_BRIDGE_ENABLED=0`` 可整体关闭，此时所有函数退化为空操作，行为与未接入桌面端时一致。
"""

from __future__ import annotations

import copy
import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from agent.services.desktop_hub import DeviceCallTimeout, DeviceOffline, hub

logger = logging.getLogger(__name__)

LOCAL_TOOL_NAMES = frozenset({"read", "write", "edit", "read_picture", "bash"})
# 会产生写入/执行效果的工具（沙盒升级参数的词汇沿用 deepseek-harness，见 desktop/NOTICE.md）。
MUTATING_TOOL_NAMES = frozenset({"write", "edit", "bash"})
ESCALATION_TARGETS = ("workspace-write", "danger-full-access")

# route_local_tool 的返回哨兵：表示「不归桌面端管，继续走云端原逻辑」
NOT_ROUTED = object()

_BEIJING = timezone(timedelta(hours=8))
_WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
_CHANNEL_LABELS = {
    "weixin": "Wechat",
    "feishu": "Feishu",
    "wecom": "WeCom",
    "xiaoai": "Xiaoai",
    "rokid": "Rokid",
    "desktop": "Desktop",
    "mobile": "Mobile",
    "web": "Web",
}

BASH_CALL_TIMEOUT_S = 3900.0
OTHER_CALL_TIMEOUT_S = 900.0


def enabled() -> bool:
    return os.getenv("DESKTOP_BRIDGE_ENABLED", "1").strip().lower() not in ("0", "false", "no", "off")


def channel_label(name: str) -> str:
    key = (name or "").strip().lower()
    return _CHANNEL_LABELS.get(key, key[:1].upper() + key[1:] if key else "Web")


def _format_time(ts: Optional[float]) -> str:
    if not ts:
        return "unknown"
    return datetime.fromtimestamp(float(ts), _BEIJING).strftime("%Y-%m-%d %H:%M")


# ---------------------------------------------------------------------------
# 会话工作区标签（带短 TTL 缓存，避免每次工具调用都查库）
# ---------------------------------------------------------------------------

_CONV_TTL_S = 60.0
_CONV_CACHE_MAX = 2048
_conv_cache: Dict[str, tuple] = {}


async def conversation_doc(config, conversation_id: str) -> Optional[Dict[str, Any]]:
    cid = (conversation_id or "").strip()
    if not cid:
        return None
    hit = _conv_cache.get(cid)
    now = time.monotonic()
    if hit and now - hit[0] < _CONV_TTL_S:
        return hit[1]
    doc = await config.db_conversation.find_one(
        {"conversation_id": cid},
        {"_id": 0, "user_id": 1, "workspace": 1, "device_id": 1, "agent_use": 1},
    )
    if doc is None:
        return None  # 新会话尚未落库，不缓存空结果
    if len(_conv_cache) >= _CONV_CACHE_MAX:
        _conv_cache.clear()
    _conv_cache[cid] = (now, doc)
    return doc


def clear_conversation_cache() -> None:
    _conv_cache.clear()


# ---------------------------------------------------------------------------
# 1. 工具定义改写
# ---------------------------------------------------------------------------

_ESCALATION_NOTE = (
    " Local file operations run under a sandbox policy; a blocked operation is reported as "
    "`[sandbox: file access denied under <mode> mode]` — a policy decision, not a bug in the call. "
    "When the marker says escalation is available and a wider mode would let it succeed, retry the exact "
    "same call once with `sandbox_permissions` (the narrowest wider mode that suffices) plus a one-sentence "
    "`justification`; the user is asked to approve. A rejected escalation is final: stop and explain, "
    "never work around it."
)

_TARGET_NOTE = (
    " Optional `target`: \"cloud\" (default) runs in the server sandbox; \"local\" runs on the user's own "
    "computer and only works while the desktop app is online (see LOCAL DEVICE in the system prompt)."
)

_ESCALATION_PROPS = {
    "sandbox_permissions": {
        "type": "string",
        "enum": list(ESCALATION_TARGETS),
        "description": (
            "Local only. The wider sandbox mode this call needs. Valid only as a one-shot retry of a call "
            "the sandbox just denied; requires justification and user approval."
        ),
    },
    "justification": {
        "type": "string",
        "description": "Required with sandbox_permissions: one sentence for the user explaining why this exact call needs the wider access.",
    },
}

_TARGET_PROP = {
    "type": "string",
    "enum": ["cloud", "local"],
    "description": "Where to run: \"cloud\" (server sandbox, default) or \"local\" (the user's own computer, when online).",
}


def _os_hint(info: Dict[str, Any]) -> str:
    os_name = (info or {}).get("os") or ""
    family = (info or {}).get("os_family") or ""
    shell = (info or {}).get("shell") or ""
    if not os_name and not family:
        return "the user's own computer"
    detail = os_name or family
    if shell:
        detail += f", shell: {shell}"
    return f"the user's own computer ({detail})"


def _local_bash_description(info: Dict[str, Any]) -> str:
    family = (info or {}).get("os_family") or ""
    if family == "windows":
        syntax = "Use Windows commands (cmd or PowerShell syntax)."
    elif family in ("darwin", "linux"):
        syntax = "Use Unix shell commands."
    else:
        syntax = "Use commands appropriate for that system."
    return (
        f"Run a command on {_os_hint(info)}, with the user's own privileges, in the conversation workspace. "
        f"{syntax} There is no isolation from the rest of the computer, so the user may be asked to approve the "
        "command; a denied command is reported as `[sandbox: ...]` and is final for that command."
    )


def _add_props(tool: Dict[str, Any], props: Dict[str, Any]) -> None:
    parameters = tool.setdefault("function", {}).setdefault("parameters", {"type": "object", "properties": {}})
    parameters.setdefault("properties", {})
    for key, value in props.items():
        parameters["properties"].setdefault(key, copy.deepcopy(value))


def _append_description(tool: Dict[str, Any], text: str) -> None:
    fn = tool.setdefault("function", {})
    fn["description"] = (fn.get("description") or "") + text


async def _latest_device_info(user_id: str, device_id: Optional[str]) -> Dict[str, Any]:
    """工具定义用「最后一次已知」的设备信息（来自库而非实时连接），这样在线/离线切换不会改变工具前缀。"""
    try:
        row = await (hub.store.get(user_id, device_id) if device_id else hub.store.latest(user_id))
    except Exception as exc:
        logger.warning("[DesktopBridge] 读取设备信息失败: %s", exc)
        return {}
    return (row or {}).get("info") or {}


async def resolve_workspace(chat) -> Dict[str, Any]:
    """返回当前会话的工作区信息：{workspace, device_id, soulprout}。库里已有的会话以库为准。"""
    doc = await conversation_doc(chat.config, chat.conversation_id)
    if doc:
        workspace = doc.get("workspace") or "cloud"
        device_id = doc.get("device_id")
    else:
        workspace = (getattr(chat, "workspace", None) or "cloud")
        device_id = getattr(chat, "device_id", None)
    return {
        "workspace": workspace,
        "device_id": device_id,
        "soulprout": getattr(chat, "agent_use", None) == "soulprout",
    }


async def adapt_tools(chat, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """按会话类型改写工具定义。云端会话（含所有网页端会话）原样返回同一个列表对象。"""
    if not enabled():
        return tools
    try:
        ws = await resolve_workspace(chat)
    except Exception as exc:
        logger.warning("[DesktopBridge] 解析工作区失败，按云端处理: %s", exc)
        return tools

    local_task = ws["workspace"] == "local"
    soulprout = ws["soulprout"]
    if not (local_task or soulprout):
        return tools

    info = await _latest_device_info(getattr(chat, "user_id", "") or "", ws["device_id"] if local_task else None)

    adapted: List[Dict[str, Any]] = []
    for tool in tools:
        name = (tool.get("function") or {}).get("name")
        if name == "list_info" and soulprout:
            tool = copy.deepcopy(tool)
            props = tool["function"].setdefault("parameters", {}).setdefault("properties", {})
            category = props.setdefault("category", {"type": "string"})
            enum = list(category.get("enum") or [])
            if "device" not in enum:
                enum.append("device")
            category["enum"] = enum
            category["description"] = (category.get("description") or "") + " / device"
            _append_description(
                tool,
                "\n- category=device: returns the user's desktop device status (online/offline, system, "
                "connected channels); use it to re-check before or after a local operation",
            )
        elif name in LOCAL_TOOL_NAMES:
            tool = copy.deepcopy(tool)
            if local_task:
                if name == "bash":
                    tool["function"]["description"] = _local_bash_description(info)
                else:
                    _append_description(tool, f" The workspace is on {_os_hint(info)}.")
            else:  # 灵芽模式：由模型选择 target
                _add_props(tool, {"target": _TARGET_PROP})
                _append_description(tool, _TARGET_NOTE)
                if name == "bash":
                    _append_description(tool, f" For target=local: {_local_bash_description(info)}")
            # 本地任务里读写的范围也受权限设置限制（读被拒时同样可以带升级参数重试），所以五个工具都带
            _add_props(tool, _ESCALATION_PROPS)
            _append_description(tool, _ESCALATION_NOTE)
        adapted.append(tool)
    return adapted


# ---------------------------------------------------------------------------
# 2. 工具路由
# ---------------------------------------------------------------------------

def _offline_message(exc: DeviceOffline) -> str:
    name = f"「{exc.device_name}」" if exc.device_name else ""
    seen = f"（最后在线：{_format_time(exc.last_seen)}）" if exc.last_seen else ""
    return (
        f"错误：用户电脑{name}当前未连接{seen}，本地操作无法执行。"
        "请如实告诉用户本地电脑暂时不可用、哪些事没能完成，不要反复重试；"
        "需要确认最新状态时可调用 list_info(category=\"device\")。"
    )


async def route_local_tool(config, name: str, arguments: Dict[str, Any]) -> Any:
    """决定一次 read/write/edit/read_picture/bash 调用在哪里执行。

    返回 ``NOT_ROUTED`` 表示走云端原逻辑（此时已把云端函数不认识的参数剔除）；
    否则返回要给 Agent 的工具结果。
    """
    target = arguments.pop("target", None)
    if not enabled():
        arguments.pop("sandbox_permissions", None)
        arguments.pop("justification", None)
        return NOT_ROUTED

    conversation_id = str(arguments.get("conversation_id") or "")
    doc = await conversation_doc(config, conversation_id)

    local = False
    device_id: Optional[str] = None
    kind = "task"
    if doc:
        kind = "soulprout" if doc.get("agent_use") == "soulprout" else "task"
        if (doc.get("workspace") or "cloud") == "local":
            local, device_id = True, doc.get("device_id")
        elif kind == "soulprout" and str(target or "").strip().lower() == "local":
            local = True

    if not local:
        arguments.pop("sandbox_permissions", None)
        arguments.pop("justification", None)
        return NOT_ROUTED

    user_id = str((doc or {}).get("user_id") or "")
    timeout = BASH_CALL_TIMEOUT_S if name == "bash" else OTHER_CALL_TIMEOUT_S
    if conversation_id in _pending_sync:
        # 之前设备离线没推送成功的智能体文件 / 技能，趁设备回来先补上
        await sync_to_device(config, conversation_id)
    try:
        return await hub.call(
            user_id,
            name,
            dict(arguments),
            device_id=device_id,
            conversation_id=conversation_id,
            context={"kind": kind},
            timeout=timeout,
        )
    except DeviceOffline as exc:
        message = _offline_message(exc)
    except DeviceCallTimeout:
        message = "错误：本地工具调用超时，用户电脑未在规定时间内返回结果。"
    except Exception as exc:
        logger.warning("[DesktopBridge] 本地工具调用失败 tool=%s: %s", name, exc)
        message = f"错误：本地工具调用失败：{exc}"
    if name == "read_picture":
        return {"ok": False, "message": message, "base64": None, "media_type": None}
    return message


# ---------------------------------------------------------------------------
# 2.5 智能体文件 / 技能：云端准备好之后推送到本地工作区
# ---------------------------------------------------------------------------
#
# 智能体卡片的文件和技能只存在云端。云端原有流程会把它们复制进「云端的会话工作区」；
# 本地会话的工具在用户电脑上执行，所以这里在原有复制完成之后，把这个目录里的内容同步到设备的本地工作区。
# 本地会话的云端目录除此之外不会被写入（read/write/edit/bash 都已转发到本地），所以它就是「待同步清单」。

SYNC_CHUNK_BYTES = 3 * 1024 * 1024
SYNC_MAX_FILES = 2000
SYNC_MAX_TOTAL_BYTES = 300 * 1024 * 1024
_SYNC_CALL_TIMEOUT_S = 120.0

_pending_sync: set = set()


def _scan_cloud_workspace(config, conversation_id: str) -> List[Dict[str, Any]]:
    root = os.path.join(config.local_file_path, conversation_id)
    files: List[Dict[str, Any]] = []
    total = 0
    if not os.path.isdir(root):
        return files
    for dirpath, _dirs, names in os.walk(root):
        for name in names:
            full = os.path.join(dirpath, name)
            try:
                size = os.path.getsize(full)
            except OSError:
                continue
            total += size
            files.append({"path": os.path.relpath(full, root).replace("\\", "/"), "size": size})
            if len(files) > SYNC_MAX_FILES or total > SYNC_MAX_TOTAL_BYTES:
                raise ValueError(f"workspace too large to sync (>{SYNC_MAX_FILES} files or >{SYNC_MAX_TOTAL_BYTES // 1024 // 1024}MB)")
    return files


def _read_chunk(path: str, offset: int, length: int) -> bytes:
    with open(path, "rb") as fh:
        fh.seek(offset)
        return fh.read(length)


async def sync_to_device(config, conversation_id: str) -> bool:
    """把本地会话在云端准备好的文件（智能体文件、技能）推送到设备工作区。

    非本地会话直接返回 True，不做任何事。设备离线时记入待同步集合，设备回来后在下一次本地工具调用前补推。
    """
    if not enabled():
        return True
    import base64

    try:
        doc = await conversation_doc(config, conversation_id)
        if not doc or (doc.get("workspace") or "cloud") != "local":
            return True
        user_id, device_id = str(doc.get("user_id") or ""), doc.get("device_id")
        files = await _to_thread(_scan_cloud_workspace, config, conversation_id)
        if not files:
            _pending_sync.discard(conversation_id)
            return True
        needed = await hub.call(
            user_id, "sync_manifest", {"files": files},
            device_id=device_id, conversation_id=conversation_id, timeout=_SYNC_CALL_TIMEOUT_S,
        )
        needed_paths = set(needed) if isinstance(needed, list) else {f["path"] for f in files}
        root = os.path.join(config.local_file_path, conversation_id)
        batch: List[Dict[str, Any]] = []
        batch_bytes = 0

        async def flush() -> None:
            nonlocal batch, batch_bytes
            if batch:
                await hub.call(
                    user_id, "sync_put", {"files": batch},
                    device_id=device_id, conversation_id=conversation_id, timeout=_SYNC_CALL_TIMEOUT_S,
                )
            batch, batch_bytes = [], 0

        for item in files:
            if item["path"] not in needed_paths:
                continue
            full = os.path.join(root, item["path"])
            offset, first = 0, True
            while first or offset < item["size"]:
                chunk = await _to_thread(_read_chunk, full, offset, SYNC_CHUNK_BYTES)
                batch.append({
                    "path": item["path"],
                    "b64": base64.b64encode(chunk).decode("ascii"),
                    "append": not first,
                })
                batch_bytes += len(chunk)
                offset += len(chunk)
                first = False
                if batch_bytes >= SYNC_CHUNK_BYTES:
                    await flush()
                if not chunk:
                    break
        await flush()
        _pending_sync.discard(conversation_id)
        return True
    except (DeviceOffline, DeviceCallTimeout):
        _pending_sync.add(conversation_id)
        logger.info("[DesktopBridge] 设备不在线，智能体文件/技能待同步 conversation=%s", conversation_id)
        return False
    except Exception as exc:
        logger.warning("[DesktopBridge] 同步到设备失败 conversation=%s: %s", conversation_id, exc)
        return False


async def _to_thread(fn, *args):
    import asyncio

    return await asyncio.to_thread(fn, *args)


# ---------------------------------------------------------------------------
# 3. 请求校验
# ---------------------------------------------------------------------------

class LocalWorkspaceError(Exception):
    pass


async def prepare_request(chat_request, user_id: str) -> None:
    """规范化聊天请求里的 workspace/device_id。只有桌面端会带 workspace=local，网页端请求原样通过。"""
    workspace = (getattr(chat_request, "workspace", None) or "").strip().lower()
    if workspace != "local" or not enabled() or getattr(chat_request, "agent_use", None) == "soulprout":
        chat_request.workspace = None
        chat_request.device_id = None
        return
    device_id = (getattr(chat_request, "device_id", None) or "").strip()
    row = await (hub.store.get(user_id, device_id) if device_id else hub.store.latest(user_id))
    if not row:
        raise LocalWorkspaceError("未找到已连接过的桌面端设备，无法创建本地会话")
    chat_request.workspace = "local"
    chat_request.device_id = row.get("device_id") or device_id
    chat_request.device_name = row.get("device_name") or ""


# ---------------------------------------------------------------------------
# 4. 灵芽模式系统提示词里的设备状态
# ---------------------------------------------------------------------------

_DEVICE_PROMPT_STATIC = (
    "# LOCAL DEVICE\n"
    "read/write/edit/read_picture/bash take an optional `target`: \"cloud\" (default, your sandbox on the "
    "server) or \"local\" (the user's own computer, when the desktop app is online). The two are separate "
    "file systems; a file created in one is not visible in the other. Local operations may be blocked by "
    "the user's permission settings or need their approval; that is the user's decision, so explain it "
    "instead of working around it. If a local call fails because the computer is offline, tell the user "
    "what could not be done and do not retry in a loop; list_info(category=\"device\") re-checks the status.\n"
    "Each user message starts with a system-added line `Source: <channel> <time>`; it is metadata, not "
    "something the user typed.\n"
)


async def device_prompt_section(user_id: str) -> str:
    if not enabled():
        return ""
    try:
        snap = await hub.snapshot(user_id)
    except Exception as exc:
        logger.warning("[DesktopBridge] 读取设备状态失败: %s", exc)
        return ""
    if not snap.get("known"):
        # 没装过桌面端：不打扰，只让模型知道 target=local 目前不可用
        return _DEVICE_PROMPT_STATIC + "Desktop: never connected (target=local is unavailable).\n"
    name = snap.get("device_name") or "computer"
    os_name = (snap.get("info") or {}).get("os") or ""
    label = f"\"{name}\"" + (f", {os_name}" if os_name else "")
    if snap.get("online"):
        lines = [f"Desktop: online ({label})"]
        channels = [channel_label(k) for k, v in sorted((snap.get("channels") or {}).items()) if v]
        if channels:
            lines.append("Connected channels: " + ", ".join(channels))
    else:
        lines = [f"Desktop: offline ({label}, last online {_format_time(snap.get('last_seen'))})"]
    return _DEVICE_PROMPT_STATIC + "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# 5. 用户消息来源行（仅灵芽模式）
# ---------------------------------------------------------------------------

def source_header(chat) -> Optional[str]:
    if not enabled() or getattr(chat, "agent_use", None) != "soulprout":
        return None
    if getattr(chat, "runtime_mode", "main") == "scheduled":
        label = "Scheduled"
    elif getattr(chat, "source_channel", None):
        label = channel_label(chat.source_channel)
    elif getattr(chat, "client", None):
        label = channel_label(chat.client)
    else:
        label = "Web"
    now = datetime.now(_BEIJING)
    return f"Source: {label} {now.strftime('%Y-%m-%d %H:%M')} {_WEEKDAYS[now.weekday()]}"


def apply_source_header(content: Any, meta: Optional[str]) -> Any:
    """把存下来的来源行拼到用户消息正文前（只处理纯文本；图片等多段内容不动）。"""
    if meta and isinstance(content, str):
        return f"{meta}\n{content}"
    return content


# ---------------------------------------------------------------------------
# list_info(category="device")
# ---------------------------------------------------------------------------

async def describe_devices(user_id: str) -> str:
    snap = await hub.snapshot(user_id)
    if not snap.get("known"):
        return json.dumps({"desktop": "never connected"}, ensure_ascii=False)
    info = snap.get("info") or {}
    out: Dict[str, Any] = {
        "desktop": {
            "name": snap.get("device_name"),
            "status": "online" if snap.get("online") else "offline",
            "system": info.get("os"),
            "shell": info.get("shell"),
            "last_seen": _format_time(snap.get("last_seen")),
        }
    }
    if snap.get("online"):
        out["channels"] = {channel_label(k): bool(v) for k, v in sorted((snap.get("channels") or {}).items())}
    return json.dumps(out, ensure_ascii=False, indent=2)

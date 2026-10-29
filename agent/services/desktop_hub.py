"""桌面端在线连接、设备状态与本地工具调用（RPC）。

桌面端（desktop/）启动后通过 ``/desktop/ws`` 连到云端，之后：

- 心跳维持在线状态，云端据此得知「用户电脑是否在线」；
- 云端 Agent 调用 read / write / edit / read_picture / bash 时，若会话在本地工作区，
  就把调用通过这条连接发给用户电脑执行，拿到结果再回给 Agent。

本模块只做连接管理与请求/响应关联，不关心具体工具语义（语义在 desktop_bridge 与桌面端）。
当前云端是单进程部署：连接表放在进程内存里。若以后改多 worker，需要在这里加跨进程转发。
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol
from uuid import uuid4

logger = logging.getLogger(__name__)

# 心跳：桌面端约每 25 秒发一次 ping；超过这个时间没收到任何帧就判定离线（电脑休眠/断网的半开连接）。
HEARTBEAT_TIMEOUT_S = 75.0
# last_seen 写库的最短间隔，避免每次心跳都落库。
TOUCH_INTERVAL_S = 30.0


class DeviceOffline(Exception):
    """目标设备当前不在线（或调用过程中掉线）。"""

    def __init__(self, device_name: str = "", last_seen: Optional[float] = None, device_id: str = ""):
        self.device_name = device_name
        self.last_seen = last_seen
        self.device_id = device_id
        super().__init__(f"device offline: {device_name or device_id or 'unknown'}")


class DeviceCallTimeout(Exception):
    """设备在线，但调用超时未返回。"""


class DeviceStore(Protocol):
    async def upsert(self, user_id: str, device_id: str, fields: Dict[str, Any]) -> None: ...
    async def get(self, user_id: str, device_id: str) -> Optional[Dict[str, Any]]: ...
    async def latest(self, user_id: str) -> Optional[Dict[str, Any]]: ...
    async def list(self, user_id: str) -> List[Dict[str, Any]]: ...


class MongoDeviceStore:
    """设备状态表 ``user_devices``：每个 (user_id, device_id) 一条，只存「最后一次已知」的信息。

    在线与否以内存里的连接为准（重启即全部离线），库里只保存设备信息、渠道状态和 last_seen。
    """

    def __init__(self, collection=None):
        self._collection = collection

    @property
    def collection(self):
        if self._collection is None:
            from agent.core.config import Config

            self._collection = Config().database["user_devices"]
        return self._collection

    async def upsert(self, user_id: str, device_id: str, fields: Dict[str, Any]) -> None:
        await self.collection.update_one(
            {"user_id": user_id, "device_id": device_id},
            {"$set": fields, "$setOnInsert": {"user_id": user_id, "device_id": device_id}},
            upsert=True,
        )

    async def get(self, user_id: str, device_id: str) -> Optional[Dict[str, Any]]:
        return await self.collection.find_one({"user_id": user_id, "device_id": device_id}, {"_id": 0})

    async def latest(self, user_id: str) -> Optional[Dict[str, Any]]:
        return await self.collection.find_one({"user_id": user_id}, {"_id": 0}, sort=[("last_seen", -1)])

    async def list(self, user_id: str) -> List[Dict[str, Any]]:
        cursor = self.collection.find({"user_id": user_id}, {"_id": 0}).sort("last_seen", -1)
        return await cursor.to_list(length=50)


@dataclass
class DesktopConn:
    ws: Any
    user_id: str
    device_id: str
    device_name: str = ""
    info: Dict[str, Any] = field(default_factory=dict)
    channels: Dict[str, bool] = field(default_factory=dict)
    connected_at: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    last_touch_write: float = 0.0
    pending: Dict[str, "asyncio.Future"] = field(default_factory=dict)


class DesktopHub:
    def __init__(self, store: Optional[DeviceStore] = None):
        self._conns: Dict[str, Dict[str, DesktopConn]] = {}
        self._lock = asyncio.Lock()
        self._store = store

    @property
    def store(self) -> DeviceStore:
        if self._store is None:
            self._store = MongoDeviceStore()
        return self._store

    # ------------------------------------------------------------------ 连接管理

    async def register(self, conn: DesktopConn) -> None:
        old: Optional[DesktopConn] = None
        async with self._lock:
            devices = self._conns.setdefault(conn.user_id, {})
            old = devices.get(conn.device_id)
            devices[conn.device_id] = conn
        if old is not None and old is not conn:
            self._fail_pending(old, DeviceOffline(old.device_name, old.last_seen, old.device_id))
            try:
                await old.ws.close(code=1012)
            except Exception:
                pass
        await self.store.upsert(
            conn.user_id,
            conn.device_id,
            {
                "kind": "desktop",
                "device_name": conn.device_name,
                "info": conn.info,
                "channels": conn.channels,
                "last_seen": conn.last_seen,
                "connected_at": conn.connected_at,
            },
        )

    async def unregister(self, conn: DesktopConn) -> None:
        was_current = False
        async with self._lock:
            devices = self._conns.get(conn.user_id)
            if devices and devices.get(conn.device_id) is conn:
                was_current = True
                devices.pop(conn.device_id, None)
                if not devices:
                    self._conns.pop(conn.user_id, None)
        self._fail_pending(conn, DeviceOffline(conn.device_name, conn.last_seen, conn.device_id))
        if not was_current:
            return  # 已被同一设备的新连接顶替：别用旧连接的状态覆盖库里新连接写入的内容
        try:
            await self.store.upsert(conn.user_id, conn.device_id, {"last_seen": conn.last_seen, "channels": {}})
        except Exception as exc:  # 落库失败不应影响断开流程
            logger.warning("[DesktopHub] 写入下线状态失败: %s", exc)

    @staticmethod
    def _fail_pending(conn: DesktopConn, exc: Exception) -> None:
        for fut in list(conn.pending.values()):
            if not fut.done():
                fut.set_exception(exc)
        conn.pending.clear()

    def get_conn(self, user_id: str, device_id: Optional[str] = None) -> Optional[DesktopConn]:
        devices = self._conns.get(user_id) or {}
        if device_id:
            return devices.get(device_id)
        if not devices:
            return None
        return max(devices.values(), key=lambda c: c.connected_at)

    def online_devices(self, user_id: str) -> List[DesktopConn]:
        return list((self._conns.get(user_id) or {}).values())

    # ------------------------------------------------------------------ 帧处理

    async def touch(self, conn: DesktopConn, channels: Optional[Dict[str, Any]] = None) -> None:
        now = time.time()
        conn.last_seen = now
        changed = False
        if channels is not None:
            normalized = {str(k): bool(v) for k, v in channels.items()}
            if normalized != conn.channels:
                conn.channels = normalized
                changed = True
        if changed or now - conn.last_touch_write >= TOUCH_INTERVAL_S:
            conn.last_touch_write = now
            fields: Dict[str, Any] = {"last_seen": now}
            if changed:
                fields["channels"] = conn.channels
            try:
                await self.store.upsert(conn.user_id, conn.device_id, fields)
            except Exception as exc:
                logger.warning("[DesktopHub] 写入心跳失败: %s", exc)

    def handle_result(self, conn: DesktopConn, data: Dict[str, Any]) -> None:
        call_id = str(data.get("call_id") or "")
        fut = conn.pending.get(call_id)
        if fut is None or fut.done():
            return  # 未知或已超时/取消的 call_id：丢弃，只允许应答发给本连接的请求
        if data.get("ok"):
            fut.set_result(data.get("result"))
        else:
            fut.set_result(str(data.get("error") or "错误：本地工具执行失败"))

    # ------------------------------------------------------------------ 调用

    async def call(
        self,
        user_id: str,
        tool: str,
        arguments: Dict[str, Any],
        *,
        device_id: Optional[str] = None,
        conversation_id: str = "",
        context: Optional[Dict[str, Any]] = None,
        timeout: float = 300.0,
    ) -> Any:
        conn = self.get_conn(user_id, device_id)
        if conn is None:
            row = await (self.store.get(user_id, device_id) if device_id else self.store.latest(user_id))
            raise DeviceOffline(
                (row or {}).get("device_name", ""),
                (row or {}).get("last_seen"),
                device_id or (row or {}).get("device_id", ""),
            )
        call_id = uuid4().hex
        fut: "asyncio.Future" = asyncio.get_running_loop().create_future()
        conn.pending[call_id] = fut
        try:
            await conn.ws.send_json(
                {
                    "type": "tool_call",
                    "call_id": call_id,
                    "tool": tool,
                    "arguments": arguments,
                    "conversation_id": conversation_id,
                    "context": context or {},
                }
            )
            return await asyncio.wait_for(fut, timeout)
        except asyncio.TimeoutError:
            await self._send_cancel(conn, call_id)
            raise DeviceCallTimeout(f"{tool} timed out after {timeout:.0f}s") from None
        except asyncio.CancelledError:
            await self._send_cancel(conn, call_id)
            raise
        except DeviceOffline:
            raise
        except Exception as exc:  # 发送失败 = 连接已不可用
            raise DeviceOffline(conn.device_name, conn.last_seen, conn.device_id) from exc
        finally:
            conn.pending.pop(call_id, None)

    @staticmethod
    async def _send_cancel(conn: DesktopConn, call_id: str) -> None:
        try:
            await conn.ws.send_json({"type": "cancel", "call_id": call_id})
        except Exception:
            pass

    # ------------------------------------------------------------------ 状态查询

    async def snapshot(self, user_id: str) -> Dict[str, Any]:
        """给 Agent 看的设备状态快照：最近一台桌面设备 + 是否在线 + 在线的渠道。"""
        online = self.online_devices(user_id)
        if online:
            conn = max(online, key=lambda c: c.connected_at)
            return {
                "known": True,
                "online": True,
                "device_id": conn.device_id,
                "device_name": conn.device_name,
                "info": conn.info,
                "channels": dict(conn.channels),
                "last_seen": conn.last_seen,
            }
        row = await self.store.latest(user_id)
        if not row:
            return {"known": False, "online": False}
        return {
            "known": True,
            "online": False,
            "device_id": row.get("device_id", ""),
            "device_name": row.get("device_name", ""),
            "info": row.get("info") or {},
            "channels": {},
            "last_seen": row.get("last_seen"),
        }


hub = DesktopHub()

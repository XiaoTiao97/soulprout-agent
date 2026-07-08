"""
Gateway 服务入口。

Soulprout Gateway 是除 Web 端以外所有平台接入 Agent 核心功能的统一端口。

职责
----
1. 构建平台适配器（微信、飞书、小爱音箱等）
2. 启动管理 Web 服务（http://localhost:8082）用于平台配置与登录
3. 将所有平台收到的消息路由到 call_agent_chat()，获得完整回复后发回平台
4. 等待退出信号（Ctrl+C / SIGTERM）后优雅关闭

实现参考
--------
- 微信接入参考 hermes-agent：https://github.com/NousResearch/hermes-agent
- 飞书 WebSocket 接入参考 hermes-agent（gateway/platforms/feishu.py）
- 企业微信 WebSocket 接入参考 hermes-agent（gateway/platforms/wecom.py）

启动方式
--------
    python gateway/main.py
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys
from pathlib import Path

# 保证以 `python gateway/main.py` 启动时也能正确解析顶层包
_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from gateway.base import BasePlatformAdapter, MessageEvent
from gateway.chat_caller import call_agent_chat
from gateway.platforms.feishu import FeishuAdapter
from gateway.platforms.wecom import WecomAdapter
from gateway.platforms.weixin import WeixinAdapter
from gateway.platforms.xiaoai import XiaoaiAdapter
from gateway.web import (
    app as web_app,
    set_feishu_adapter,
    set_wecom_adapter,
    set_weixin_adapter,
    set_xiaoai_adapter,
    start_web_server,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 父进程看门狗
# ---------------------------------------------------------------------------
#
# gateway 进程由 Tauri 桌面端（或本地调试时的父进程）拉起时，会通过环境变量
# GATEWAY_PARENT_PID 传入父进程 PID。桌面端关闭时会主动 kill 本进程，但为防止
# 出现「桌面端被强制结束 / 崩溃 / 未走到清理逻辑」导致 gateway 变成孤儿进程、
# 长期占用端口从而导致下次启动/安装失败的情况，这里额外做一层保险：
# 定期检测父进程是否还存活，一旦父进程消失就立即自我退出。


def _pid_alive(pid: int) -> bool:
    if sys.platform == "win32":
        import ctypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        handle = ctypes.windll.kernel32.OpenProcess(
            PROCESS_QUERY_LIMITED_INFORMATION, False, pid
        )
        if not handle:
            return False
        try:
            exit_code = ctypes.c_ulong()
            if not ctypes.windll.kernel32.GetExitCodeProcess(
                handle, ctypes.byref(exit_code)
            ):
                return False
            return exit_code.value == STILL_ACTIVE
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)
    else:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True


async def _watch_parent_process(parent_pid: int, interval: float = 3.0) -> None:
    """父进程消失后立即自我退出，避免残留为孤儿进程。"""
    while True:
        await asyncio.sleep(interval)
        if not _pid_alive(parent_pid):
            logger.warning(
                "[Gateway] 检测到父进程 (pid=%d) 已退出，自动关闭 Gateway 进程", parent_pid
            )
            os._exit(0)


# ---------------------------------------------------------------------------
# 平台适配器注册表
# ---------------------------------------------------------------------------

_adapters: dict[str, BasePlatformAdapter] = {}
_weixin_adapter: WeixinAdapter | None = None
_feishu_adapter: FeishuAdapter | None = None
_wecom_adapter: WecomAdapter | None = None
_xiaoai_adapter: XiaoaiAdapter | None = None


def get_platform_adapter(platform: str) -> BasePlatformAdapter | None:
    return _adapters.get(platform)


# ---------------------------------------------------------------------------
# 消息处理器（所有平台消息的统一业务入口）
# ---------------------------------------------------------------------------

async def on_message(event: MessageEvent) -> None:
    """
    所有平台消息汇聚点。

    接收来自平台的消息事件，调用 Agent Chat 服务，
    将 assistant 完整回复发回给对应平台的发送方。
    """
    platform = event.source.platform if event.source else "unknown"
    chat_id = event.source.chat_id if event.source else ""
    user_id = event.source.user_id or chat_id

    logger.info(
        "[Gateway] 收到消息 platform=%s chat=%s type=%s text=%r",
        platform,
        chat_id,
        event.message_type.value,
        event.text[:80],
    )

    if not event.text.strip():
        return

    try:
        from gateway.config_store import get_agent_user_id
        configured_user_id = get_agent_user_id()
        reply = await call_agent_chat(
            message=event.text,
            user_id=configured_user_id or user_id,
            conversation_id=configured_user_id or user_id,
        )
        logger.info("[Gateway] Agent 回复 platform=%s chat=%s: %r", platform, chat_id, reply[:80])
    except Exception as exc:
        logger.error("[Gateway] call_agent_chat 异常: %s", exc, exc_info=True)
        reply = "（系统错误，请稍后重试）"

    if not chat_id:
        logger.warning("[Gateway] chat_id 为空，无法发送回复")
        return

    adapter = _adapters.get(platform)
    if adapter is None:
        logger.warning("[Gateway] 无对应 adapter 可发送，platform=%s", platform)
        return

    result = await adapter.send(chat_id, reply)
    if not result.success:
        logger.error("[Gateway] 发送回复失败 platform=%s: %s", platform, result.error)


# ---------------------------------------------------------------------------
# 构建适配器
# ---------------------------------------------------------------------------

def build_weixin_adapter() -> WeixinAdapter:
    adapter = WeixinAdapter()
    adapter.set_message_handler(on_message)
    return adapter


def build_feishu_adapter() -> FeishuAdapter:
    adapter = FeishuAdapter()
    adapter.set_message_handler(on_message)
    return adapter


def build_wecom_adapter() -> WecomAdapter:
    adapter = WecomAdapter()
    adapter.set_message_handler(on_message)
    return adapter


def build_xiaoai_adapter() -> XiaoaiAdapter:
    adapter = XiaoaiAdapter()
    adapter.set_message_handler(on_message)
    return adapter


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

async def _connect_adapter_bg(name: str, adapter: "BasePlatformAdapter", web_port: int) -> None:
    """后台尝试连接单个平台 adapter，失败不阻塞启动。"""
    try:
        connected = await adapter.connect()
        if connected:
            logger.info("[Gateway] %s adapter 已连接", name)
        else:
            logger.info("[Gateway] %s 未连接，可在管理界面 http://localhost:%d/%s 配置", name, web_port, name)
    except Exception as exc:
        logger.error("[Gateway] %s adapter 连接异常: %s", name, exc, exc_info=True)


async def run() -> None:
    global _weixin_adapter, _feishu_adapter, _wecom_adapter, _xiaoai_adapter

    web_host = os.getenv("GATEWAY_WEB_HOST", "0.0.0.0")
    web_port = int(os.getenv("GATEWAY_WEB_PORT", "8082"))

    _weixin_adapter = build_weixin_adapter()
    _feishu_adapter = build_feishu_adapter()
    _wecom_adapter = build_wecom_adapter()
    _xiaoai_adapter = build_xiaoai_adapter()
    _adapters["weixin"] = _weixin_adapter
    _adapters["feishu"] = _feishu_adapter
    _adapters["wecom"] = _wecom_adapter
    _adapters["xiaoai"] = _xiaoai_adapter
    set_weixin_adapter(_weixin_adapter)
    set_feishu_adapter(_feishu_adapter)
    set_wecom_adapter(_wecom_adapter)
    set_xiaoai_adapter(_xiaoai_adapter)

    stop_event = asyncio.Event()

    def _on_signal(*_):
        logger.info("[Gateway] 收到退出信号，正在关闭…")
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _on_signal)
        except (NotImplementedError, OSError):
            pass

    parent_pid_raw = os.getenv("GATEWAY_PARENT_PID", "").strip()
    if parent_pid_raw.isdigit():
        parent_pid = int(parent_pid_raw)
        logger.info("[Gateway] 已启用父进程看门狗，父进程 pid=%d", parent_pid)
        asyncio.create_task(_watch_parent_process(parent_pid), name="parent-watchdog")

    # Web 服务优先启动，保证 Tauri 能立刻加载管理界面
    web_task = asyncio.create_task(
        start_web_server(host=web_host, port=web_port),
        name="gateway-web",
    )

    logger.info("[Gateway] 管理界面启动中 http://localhost:%d …", web_port)

    # 各平台 adapter 在后台并发连接，不阻塞 web 服务开启
    connect_tasks = [
        asyncio.create_task(_connect_adapter_bg("weixin", _weixin_adapter, web_port), name="connect-weixin"),
        asyncio.create_task(_connect_adapter_bg("feishu", _feishu_adapter, web_port), name="connect-feishu"),
        asyncio.create_task(_connect_adapter_bg("wecom", _wecom_adapter, web_port), name="connect-wecom"),
        asyncio.create_task(_connect_adapter_bg("xiaoai", _xiaoai_adapter, web_port), name="connect-xiaoai"),
    ]

    try:
        await stop_event.wait()
    except KeyboardInterrupt:
        pass
    finally:
        for t in connect_tasks:
            t.cancel()

        web_task.cancel()
        try:
            await web_task
        except (asyncio.CancelledError, Exception):
            pass

        for name, adapter in _adapters.items():
            if adapter.is_connected:
                logger.info("[Gateway] 断开 %s adapter…", name)
                await adapter.disconnect()

        logger.info("[Gateway] 已全部关闭")


if __name__ == "__main__":
    asyncio.run(run())

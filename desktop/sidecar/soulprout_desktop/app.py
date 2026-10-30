"""桌面端 sidecar 的装配与运行。

环境变量（由 Tauri 壳在启动 sidecar 时设置；单独调试时都有默认值）：

- ``SOULPROUT_DESKTOP_PORT``    本地 HTTP 服务端口（默认随机空闲端口）
- ``SOULPROUT_DESKTOP_SECRET``  本次启动的访问密钥（默认随机生成并打印启动地址）
- ``SOULPROUT_PARENT_PID``      父进程 PID，父进程消失时自动退出，避免残留孤儿进程
- ``SOULPROUT_NO_GATEWAY=1``    不启动合并进来的 gateway（只调试桌面功能时用）
- ``AGENT_URL``                 仅测试用。产品默认连官网，用户在设置里改地址。
"""

from __future__ import annotations

import asyncio
import logging
import os
import secrets
import signal
import sys
from typing import Optional

from aiohttp import web

from . import auth_store, paths, policy, settings
from .approvals import ApprovalBroker
from .cloud_client import CloudClient
from .gateway_host import GatewayHost, find_free_port
from .local_tools import LocalToolRunner
from .server import AppContext, DesktopServer

logger = logging.getLogger(__name__)

CHANNEL_WATCH_INTERVAL_S = 4.0


def _pid_alive(pid: int) -> bool:
    if sys.platform == "win32":
        import ctypes

        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            if not ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return False
            return code.value == 259  # STILL_ACTIVE
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


async def _watch_parent(pid: int, stop_event: asyncio.Event, interval: float = 3.0) -> None:
    while not stop_event.is_set():
        await asyncio.sleep(interval)
        if not _pid_alive(pid):
            logger.warning("[Desktop] 父进程 (pid=%d) 已退出，自动关闭", pid)
            os._exit(0)


async def _watch_channels(cloud: CloudClient, stop_event: asyncio.Event) -> None:
    """渠道连接状态变化时立刻上报云端（云端据此决定系统提示词里写不写这个渠道）。"""
    last = GatewayHost.channel_status()
    while not stop_event.is_set():
        await asyncio.sleep(CHANNEL_WATCH_INTERVAL_S)
        current = GatewayHost.channel_status()
        if current != last:
            last = current
            await cloud.push_channels()


async def run_app(*, port: Optional[int] = None, enable_gateway: Optional[bool] = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s - %(message)s")

    port = port or int(os.getenv("SOULPROUT_DESKTOP_PORT", "") or find_free_port())
    secret = os.getenv("SOULPROUT_DESKTOP_SECRET", "").strip() or secrets.token_urlsafe(32)
    parent_pid = os.getenv("SOULPROUT_PARENT_PID", "").strip()
    if enable_gateway is None:
        enable_gateway = os.getenv("SOULPROUT_NO_GATEWAY", "").strip().lower() not in ("1", "true", "yes")

    paths.state_dir().mkdir(parents=True, exist_ok=True)
    paths.workspaces_root().mkdir(parents=True, exist_ok=True)
    auth_store.redirect_gateway_storage()
    auth_store.sync_gateway_agent_url()
    # 各渠道的存储目录重定向要导入渠道模块（飞书 SDK 导入要二三十秒），交给 GatewayHost 在后台线程里做，
    # 不能挡在界面服务启动之前。

    broker = ApprovalBroker()
    runner = LocalToolRunner(lambda: policy.standing_for(settings.preset()), broker)
    gateway = GatewayHost(enabled=enable_gateway)

    def make_connector():
        from gateway.chat_caller import _make_ssl_connector

        return _make_ssl_connector()

    cloud = CloudClient(
        executor=runner.execute,
        get_token=auth_store.get_token,
        get_agent_url=auth_store.agent_url,
        get_channels=GatewayHost.channel_status,
        on_cancel=broker.cancel_call,
        ssl_connector_factory=make_connector,
        on_auth_failed=auth_store.clear_login,
    )
    ctx = AppContext(secret=secret, port=port, broker=broker, cloud=cloud, gateway_info=gateway.info)
    app = DesktopServer(ctx).build_app()
    runner_web = web.AppRunner(app, access_log=None)
    await runner_web.setup()
    await web.TCPSite(runner_web, "127.0.0.1", port).start()

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except (NotImplementedError, OSError, RuntimeError):
            pass

    # Tauri 壳靠这一行（以及端口可连通）判断 sidecar 已就绪；单独调试时直接用这个地址打开页面。
    print(f"SOULPROUT_DESKTOP_READY http://127.0.0.1:{port}/__boot?s={secret}", flush=True)

    tasks = [
        asyncio.create_task(cloud.run(stop_event), name="desktop-cloud"),
        asyncio.create_task(_watch_channels(cloud, stop_event), name="desktop-channels"),
    ]
    if parent_pid.isdigit():
        tasks.append(asyncio.create_task(_watch_parent(int(parent_pid), stop_event), name="desktop-parent"))
    gateway.start(parent_pid)

    try:
        await stop_event.wait()
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await gateway.stop()
        await runner_web.cleanup()
        logger.info("[Desktop] 已关闭")

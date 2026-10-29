"""把原有 gateway（微信 / 飞书 / 企业微信 / 小爱等渠道）作为桌面端的一部分运行。

直接复用 ``gateway.main.run``，不改 gateway 的任何代码：

- 管理页面只绑定本机（``GATEWAY_WEB_HOST=127.0.0.1``），桌面界面用一个内嵌窗口打开它；
- 渠道是否连通由各个 adapter 自己的 ``is_connected`` 决定，和桌面端在线与否互相独立——
  装了桌面端但没连微信是正常状态，所以这里只如实上报每个渠道当前的连接情况；
- 父进程看门狗沿用 gateway 自带的 ``GATEWAY_PARENT_PID`` 机制。
"""

from __future__ import annotations

import asyncio
import logging
import os
import socket
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def redirect_platform_storage() -> None:
    """把各渠道的凭证/会话数据（微信登录态、飞书/企业微信配置等）也放进桌面端的状态目录。

    gateway 默认把它们写在可执行文件旁边的 ``gateway_data/``；桌面端统一放到受保护的状态目录里，
    Agent 的本地文件工具碰不到这里。这些都是模块级路径常量，运行时覆盖即可，不用改 gateway 代码。
    """
    import importlib

    from . import paths

    base = paths.state_dir() / "gateway"
    plans = {
        "gateway.platforms.weixin": {"WEIXIN_DATA_DIR": ("weixin", None)},
        "gateway.platforms.feishu": {"FEISHU_DATA_DIR": ("feishu", None), "FEISHU_CONFIG_PATH": ("feishu", "config.json")},
        "gateway.platforms.wecom": {"WECOM_DATA_DIR": ("wecom", None), "WECOM_CONFIG_PATH": ("wecom", "config.json")},
        "gateway.platforms.xiaoai_miot": {
            "XIAOAI_DATA_DIR": ("xiaoai", None),
            "XIAOAI_CONFIG_PATH": ("xiaoai", "config.json"),
            "XIAOAI_SESSION_PATH": ("xiaoai", ".mi.json"),
        },
    }
    for module_name, attrs in plans.items():
        try:
            module = importlib.import_module(module_name)
        except Exception as exc:  # 缺可选依赖时跳过该渠道即可
            logger.info("[Desktop] 跳过渠道存储重定向 %s: %s", module_name, exc)
            continue
        for attr, (folder, filename) in attrs.items():
            target = base / folder
            setattr(module, attr, target / filename if filename else target)


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


class GatewayHost:
    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self.web_port: Optional[int] = None
        self._task: Optional["asyncio.Task"] = None
        self.error = ""

    def start(self, parent_pid: str = "") -> None:
        if not self.enabled or self._task is not None:
            return
        self.web_port = int(os.getenv("SOULPROUT_GATEWAY_PORT", "") or find_free_port())
        os.environ["GATEWAY_WEB_HOST"] = "127.0.0.1"
        os.environ["GATEWAY_WEB_PORT"] = str(self.web_port)
        if parent_pid:
            os.environ["GATEWAY_PARENT_PID"] = parent_pid
        self._task = asyncio.create_task(self._run(), name="desktop-gateway")

    async def _run(self) -> None:
        try:
            from gateway.main import run

            await run(cli_mode=False, daemon_mode=False)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.error = str(exc)
            logger.error("[Desktop] gateway 异常退出: %s", exc, exc_info=True)

    async def stop(self) -> None:
        task, self._task = self._task, None
        if task is None:
            return
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass

    @staticmethod
    def channel_status() -> Dict[str, bool]:
        """每个渠道当前是否已连接。"""
        try:
            from gateway.platform_registry import iter_platform_adapters

            return {name: bool(getattr(adapter, "is_connected", False)) for name, adapter in iter_platform_adapters()}
        except Exception:
            return {}

    def info(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "url": f"http://127.0.0.1:{self.web_port}/" if self.enabled and self.web_port else None,
            "channels": self.channel_status(),
            "error": self.error,
        }

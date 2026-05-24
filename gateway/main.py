"""
Gateway 服务入口。

Soulprout Gateway 是除 Web 端以外所有平台（目前支持微信个人号）
接入 Agent 核心功能的统一端口。

职责
----
1. 构建 WeixinAdapter（个人微信平台适配器）
2. 启动管理 Web 服务（http://localhost:8082）用于微信扫码登录
3. 将所有平台收到的消息路由到 call_agent_chat()，获得完整回复后发回平台
4. 等待退出信号（Ctrl+C / SIGTERM）后优雅关闭

微信实现参考
-----------
本 Gateway 的微信接入实现参考了 hermes-agent 项目的个人微信适配器：
    https://github.com/NousResearch/hermes-agent

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

from gateway.base import MessageEvent
from gateway.chat_caller import call_agent_chat
from gateway.platforms.weixin import WeixinAdapter
from gateway.web import app as web_app, set_weixin_adapter, start_web_server

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)

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

    # 发回对应平台
    if not chat_id:
        logger.warning("[Gateway] chat_id 为空，无法发送回复")
        return

    # 找到正确的 adapter 发送（目前只有 weixin）
    global _weixin_adapter
    if _weixin_adapter and platform == "weixin":
        result = await _weixin_adapter.send(chat_id, reply)
        if not result.success:
            logger.error("[Gateway] 发送回复失败: %s", result.error)
    else:
        logger.warning("[Gateway] 无对应 adapter 可发送，platform=%s", platform)


# ---------------------------------------------------------------------------
# 构建适配器
# ---------------------------------------------------------------------------

_weixin_adapter: WeixinAdapter | None = None


def build_weixin_adapter() -> WeixinAdapter:
    """创建并配置 WeixinAdapter 实例。"""
    adapter = WeixinAdapter()
    adapter.set_message_handler(on_message)
    return adapter


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

async def run() -> None:
    global _weixin_adapter

    web_host = os.getenv("GATEWAY_WEB_HOST", "0.0.0.0")
    web_port = int(os.getenv("GATEWAY_WEB_PORT", "8082"))

    # ── 构建微信 adapter ──
    _weixin_adapter = build_weixin_adapter()
    set_weixin_adapter(_weixin_adapter)

    # ── 尝试连接（若无凭证则跳过，等待用户通过 Web UI 扫码后再连接）──
    connected = await _weixin_adapter.connect()
    if connected:
        logger.info("[Gateway] 微信 adapter 已连接，开始接收消息")
    else:
        logger.info(
            "[Gateway] 微信未连接（凭证未配置或尚未扫码）。"
            "请打开管理界面 http://localhost:%d 进行扫码登录。",
            web_port,
        )

    # ── 启动管理 Web 服务 ──
    stop_event = asyncio.Event()

    def _on_signal(*_):
        logger.info("[Gateway] 收到退出信号，正在关闭…")
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _on_signal)
        except (NotImplementedError, OSError):
            # Windows 不支持 add_signal_handler，依靠 KeyboardInterrupt
            pass

    # 并行运行：Web 管理服务 + 等待退出
    web_task = asyncio.create_task(
        start_web_server(host=web_host, port=web_port),
        name="gateway-web",
    )

    logger.info(
        "[Gateway] 启动完成。管理界面：http://localhost:%d  按 Ctrl+C 退出",
        web_port,
    )

    try:
        await stop_event.wait()
    except KeyboardInterrupt:
        pass
    finally:
        web_task.cancel()
        try:
            await web_task
        except (asyncio.CancelledError, Exception):
            pass

        if _weixin_adapter and _weixin_adapter.is_connected:
            await _weixin_adapter.disconnect()

        logger.info("[Gateway] 已全部关闭")


if __name__ == "__main__":
    asyncio.run(run())

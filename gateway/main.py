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

    weixin_connected = await _weixin_adapter.connect()
    if weixin_connected:
        logger.info("[Gateway] 微信 adapter 已连接")
    else:
        logger.info("[Gateway] 微信未连接，可在管理界面 http://localhost:%d/weixin 扫码登录", web_port)

    feishu_connected = await _feishu_adapter.connect()
    if feishu_connected:
        logger.info("[Gateway] 飞书 adapter 已连接")
    else:
        logger.info("[Gateway] 飞书未连接，可在管理界面 http://localhost:%d/feishu 配置", web_port)

    wecom_connected = await _wecom_adapter.connect()
    if wecom_connected:
        logger.info("[Gateway] 企业微信 adapter 已连接")
    else:
        logger.info("[Gateway] 企业微信未连接，可在管理界面 http://localhost:%d/wecom 配置", web_port)

    xiaoai_connected = await _xiaoai_adapter.connect()
    if xiaoai_connected:
        logger.info("[Gateway] 小爱音箱 adapter 已连接")
    else:
        logger.info("[Gateway] 小爱音箱未连接，可在管理界面 http://localhost:%d/xiaoai 配置", web_port)

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

        for name, adapter in _adapters.items():
            if adapter.is_connected:
                logger.info("[Gateway] 断开 %s adapter…", name)
                await adapter.disconnect()

        logger.info("[Gateway] 已全部关闭")


if __name__ == "__main__":
    asyncio.run(run())

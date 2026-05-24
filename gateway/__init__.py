"""
Gateway 模块 — 平台消息网关。

提供统一的平台接入抽象，目前支持：
- 个人微信 (WeixinAdapter)  基于腾讯 iLink Bot API，扫码登录，长轮询收消息

快速使用示例：
    from gateway.base import MessageEvent, SendResult
    from gateway.platforms.weixin import WeixinAdapter

    adapter = WeixinAdapter()
    adapter.set_message_handler(my_handler)
    await adapter.connect()
"""

from gateway.base import (
    BasePlatformAdapter,
    MessageEvent,
    MessageHandler,
    MessageType,
    SendResult,
    SessionSource,
)

__all__ = [
    "BasePlatformAdapter",
    "MessageEvent",
    "MessageHandler",
    "MessageType",
    "SendResult",
    "SessionSource",
]

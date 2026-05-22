"""
Gateway 模块 — 平台消息网关。

提供统一的平台接入抽象，目前支持：
- 微信客服 (WeComKFAdapter)  企业微信对外客服，通过 sync_msg 拉取消息

快速使用示例：
    from gateway.base import MessageEvent, SendResult, SessionSource
    from gateway.platforms.wecom_kf import WeComKFAdapter, WeComKFConfig

    config = WeComKFConfig.from_env()
    adapter = WeComKFAdapter(config)
    adapter.set_message_handler(my_handler)

    # 在 FastAPI lifespan 中：
    await adapter.connect()
    app.include_router(adapter.get_router())
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

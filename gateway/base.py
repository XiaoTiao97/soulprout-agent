warmingwarming"""
Gateway 基础接口模块。

定义所有平台适配器共用的数据结构和抽象基类。
后续新增平台只需继承 BasePlatformAdapter 并实现抽象方法即可。
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 消息类型
# ---------------------------------------------------------------------------

class MessageType(Enum):
    TEXT = "text"
    IMAGE = "image"
    VOICE = "voice"
    VIDEO = "video"
    FILE = "file"
    EVENT = "event"


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------

@dataclass
class SessionSource:
    """消息来源信息，用于将回复路由回正确的位置。"""

    platform: str
    """平台名称，例如 'wecom_callback'。"""

    chat_id: str
    """会话唯一标识符（用于发送回复）。"""

    chat_name: Optional[str] = None
    """会话显示名称。"""

    chat_type: str = "dm"
    """会话类型：'dm'（私聊）或 'group'（群聊）。"""

    user_id: Optional[str] = None
    """发送方用户 ID。"""

    user_name: Optional[str] = None
    """发送方用户名。"""


@dataclass
class MessageEvent:
    """来自平台的统一入站消息格式。"""

    text: str
    """消息文本内容。"""

    source: Optional[SessionSource] = None
    """消息来源信息。"""

    message_type: MessageType = MessageType.TEXT
    """消息类型。"""

    message_id: Optional[str] = None
    """平台原始消息 ID（用于去重等）。"""

    raw_message: Any = None
    """平台原始消息体（XML / JSON 等）。"""

    media_urls: List[str] = field(default_factory=list)
    """媒体文件本地路径列表（当前版本暂不使用）。"""


@dataclass
class SendResult:
    """发送消息的结果。"""

    success: bool

    message_id: Optional[str] = None
    """平台返回的消息 ID。"""

    error: Optional[str] = None
    """失败时的错误描述。"""

    raw_response: Any = None
    """平台原始响应数据。"""


# ---------------------------------------------------------------------------
# 类型别名
# ---------------------------------------------------------------------------

MessageHandler = Callable[[MessageEvent], Awaitable[None]]


# ---------------------------------------------------------------------------
# 抽象基类
# ---------------------------------------------------------------------------

class BasePlatformAdapter(ABC):
    """
    平台适配器抽象基类。

    子类需实现以下方法：
    - connect      建立连接（初始化 HTTP 客户端、获取 token 等）
    - disconnect   断开连接并释放资源
    - send         向指定会话发送消息
    - get_chat_info 获取会话基本信息

    框架会通过 set_message_handler() 注入消息处理回调，
    适配器在收到入站消息时调用 handle_message() 触发该回调。
    """

    def __init__(self, platform: str):
        self.platform = platform
        self._message_handler: Optional[MessageHandler] = None
        self._running: bool = False

    # ------------------------------------------------------------------
    # 消息处理器注入
    # ------------------------------------------------------------------

    def set_message_handler(self, handler: MessageHandler) -> None:
        """注入消息处理回调，由上层业务逻辑在启动时调用。"""
        self._message_handler = handler

    async def handle_message(self, event: MessageEvent) -> None:
        """将入站消息分发给已注册的处理器。"""
        if self._message_handler is not None:
            try:
                await self._message_handler(event)
            except Exception:
                logger.exception("[%s] handle_message 抛出异常", self.platform)
        else:
            logger.warning("[%s] 收到消息但未注册处理器: %s", self.platform, event.text[:50])

    # ------------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------------

    def build_source(
        self,
        chat_id: str,
        chat_name: Optional[str] = None,
        chat_type: str = "dm",
        user_id: Optional[str] = None,
        user_name: Optional[str] = None,
    ) -> SessionSource:
        """构造当前平台的 SessionSource 实例。"""
        return SessionSource(
            platform=self.platform,
            chat_id=str(chat_id),
            chat_name=chat_name,
            chat_type=chat_type,
            user_id=str(user_id) if user_id else None,
            user_name=user_name,
        )

    # ------------------------------------------------------------------
    # 抽象方法
    # ------------------------------------------------------------------

    @abstractmethod
    async def connect(self) -> bool:
        """建立连接，返回 True 表示成功。"""
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        """断开连接并释放所有资源。"""
        ...

    @abstractmethod
    async def send(
        self,
        chat_id: str,
        content: str,
        reply_to: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SendResult:
        """向指定 chat_id 发送文本消息。"""
        ...

    @abstractmethod
    async def get_chat_info(self, chat_id: str) -> Dict[str, Any]:
        """获取会话基本信息（名称、类型等）。"""
        ...

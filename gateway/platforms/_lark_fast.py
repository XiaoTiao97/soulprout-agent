"""飞书 SDK（lark-oapi）的快速入口。

为什么需要它
------------
``import lark_oapi`` 会把飞书开放平台**所有**业务域（人事、招聘、考勤、云文档……）的接口模型
一次性导入：约 9000 个模块，在普通机器上要 20~30 秒（杀毒软件实时扫描时更久）。
根源有两处：

1. ``lark_oapi/__init__.py`` 和 ``lark_oapi/api/__init__.py`` 无条件导入全部子包；
2. ``lark_oapi.client.Client`` 初始化时给每个业务域都挂一个服务对象，``client.py`` 顶部因此导入全部服务。

而网关只用到：发消息（``client.im.v1.message.create``）、事件分发、WebSocket 长连接——
这些加起来不到 100 个模块、不足 1 秒。

做法
----
先放两个空壳包 ``lark_oapi`` / ``lark_oapi.api`` 进 ``sys.modules``（只带正确的 ``__path__``），
这样 ``lark_oapi.core`` / ``lark_oapi.ws`` / ``lark_oapi.api.im.v1`` 等子模块仍按需正常导入，
但不会触发上面两处全量导入；再提供一个只挂了 ``im`` 服务的轻量 ``Client``（构造流程与 SDK 的
``ClientBuilder`` 一致）。

任何一步失败都会清掉空壳并退回完整的 ``import lark_oapi``，所以最坏情况只是回到原来的慢速度，
不会因为 SDK 升级内部结构而不可用。
"""

from __future__ import annotations

import importlib
import importlib.machinery
import importlib.util
import logging
import os
import sys
import types
import urllib.parse
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

_light: Optional[types.SimpleNamespace] = None


def _purge() -> None:
    for name in [m for m in sys.modules if m == "lark_oapi" or m.startswith("lark_oapi.")]:
        del sys.modules[name]


def _install_stub(name: str, locations: list) -> None:
    module = types.ModuleType(name)
    module.__path__ = list(locations)  # type: ignore[attr-defined]
    module.__package__ = name
    spec = importlib.machinery.ModuleSpec(name, None, is_package=True)
    spec.submodule_search_locations = list(locations)
    module.__spec__ = spec
    module.__lark_fast_stub__ = True  # type: ignore[attr-defined]
    sys.modules[name] = module


def _validate_domain(domain: str) -> None:
    """与 SDK 的校验一致：只允许 https://host[:port]（loopback 允许 http），防止把凭证发到别处。"""
    if not isinstance(domain, str) or not domain:
        raise ValueError("domain must be a non-empty https URL")
    parsed = urllib.parse.urlsplit(domain)
    if parsed.scheme == "http":
        if (parsed.hostname or "").lower() not in ("127.0.0.1", "localhost", "::1"):
            raise ValueError(f"domain must use https scheme (got {domain!r})")
    elif parsed.scheme != "https":
        raise ValueError(f"domain must use https scheme (got {domain!r})")
    if not parsed.netloc or "@" in parsed.netloc or parsed.path or parsed.query or parsed.fragment:
        raise ValueError(f"domain must be an origin (scheme + host[:port]) (got {domain!r})")


def _build_light() -> types.SimpleNamespace:
    spec = importlib.util.find_spec("lark_oapi")  # 只查找，不执行 __init__
    if spec is None:
        raise ImportError("No module named 'lark_oapi'")
    locations = list(spec.submodule_search_locations or [])
    if not locations:
        raise ImportError("lark_oapi is not a package")

    _install_stub("lark_oapi", locations)
    _install_stub("lark_oapi.api", [os.path.join(p, "api") for p in locations])

    from lark_oapi.api.im.service import ImService
    from lark_oapi.core import logger as sdk_logger
    from lark_oapi.core.enum import LogLevel
    from lark_oapi.core.model import Config
    from lark_oapi.core.token import TokenManager

    class LightClient:
        """只带 ``im`` 服务的 Client；``Client.builder()...build()`` 的用法与 SDK 一致。"""

        def __init__(self) -> None:
            self._config: Optional[Any] = None
            self.im: Optional[Any] = None

        @staticmethod
        def builder() -> "LightClientBuilder":
            return LightClientBuilder()

        @property
        def config(self) -> Optional[Any]:
            return self._config

    class LightClientBuilder:
        def __init__(self) -> None:
            self._config = Config()

        def app_id(self, app_id: str) -> "LightClientBuilder":
            self._config.app_id = app_id
            return self

        def app_secret(self, app_secret: str) -> "LightClientBuilder":
            self._config.app_secret = app_secret
            return self

        def domain(self, domain: str) -> "LightClientBuilder":
            _validate_domain(domain)
            self._config.domain = domain
            return self

        def timeout(self, timeout: float) -> "LightClientBuilder":
            self._config.timeout = timeout
            return self

        def log_level(self, log_level: Any) -> "LightClientBuilder":
            self._config.log_level = log_level
            return self

        def build(self) -> LightClient:
            client = LightClient()
            client._config = self._config
            if self._config.cache is not None:
                TokenManager.cache = self._config.cache
            sdk_logger.setLevel(int(self._config.log_level.value))
            client.im = ImService(self._config)
            return client

    _install_light_dispatcher()

    return types.SimpleNamespace(Client=LightClient, LogLevel=LogLevel, __lark_light__=True)


def _install_light_dispatcher() -> None:
    """用只含 IM 事件的轻量分发器占住 ``lark_oapi.event.dispatcher_handler``。

    SDK 原版 ``dispatcher_handler.py`` 顶部会导入所有业务域的事件 processor（corehr/hire/... 数千个模块），
    ``ws/client.py`` 又依赖它。WebSocket 通道只走 ``_do_without_validation``（连接本身已鉴权，
    不做验签/解密），逻辑与原版完全一致；其它事件可用 ``register_p2_customized_event`` 注册。
    """
    from lark_oapi.api.im.v1.processor import P2ImMessageReceiveV1Processor
    from lark_oapi.core.const import UTF_8
    from lark_oapi.core.enum import LogLevel
    from lark_oapi.core.exception import EventException
    from lark_oapi.core.json import JSON
    from lark_oapi.core.log import logger
    from lark_oapi.core.utils import Strings
    from lark_oapi.event.context import EventContext
    from lark_oapi.event.custom import CustomizedEventProcessor

    class EventDispatcherHandler:
        def __init__(self) -> None:
            self._processorMap: dict = {}
            self._callback_processor_map: dict = {}
            self._encrypt_key: Optional[str] = None
            self._verification_token: Optional[str] = None

        def _do_without_validation(self, payload: bytes) -> Any:
            pl = payload.decode(UTF_8)
            context = JSON.unmarshal(pl, EventContext)
            if Strings.is_not_empty(context.schema):  # v2 事件
                context.schema = "p2"
                context.type = context.header.event_type
                context.token = context.header.token
            elif Strings.is_not_empty(context.uuid):  # v1 事件
                context.schema = "p1"
                context.type = context.event.get("type")

            key = f"{context.schema}.{context.type}"
            if key in self._callback_processor_map:
                processor = self._callback_processor_map[key]
                return processor.do(JSON.unmarshal(pl, processor.type()))
            processor = self._processorMap.get(key)
            if processor is None:
                raise EventException(f"processor not found, type: {context.type}")
            processor.do(JSON.unmarshal(pl, processor.type()))
            return None

        do_without_validation = _do_without_validation

        def do(self, req: Any) -> Any:  # HTTP 回调模式：网关不使用
            raise NotImplementedError("轻量事件分发器只支持 WebSocket 通道")

        @staticmethod
        def builder(encrypt_key: str, verification_token: str, level: Optional[LogLevel] = None) -> "Builder":
            if level is not None:
                logger.setLevel(int(level.value))
            return Builder(encrypt_key, verification_token)

    class Builder:
        def __init__(self, encrypt_key: str, verification_token: str) -> None:
            self._encrypt_key = encrypt_key
            self._verification_token = verification_token
            self._processorMap: dict = {}

        def _register(self, key: str, processor: Any) -> "Builder":
            if key in self._processorMap:
                raise EventException(f"processor already registered, type: {key}")
            self._processorMap[key] = processor
            return self

        def register_p2_im_message_receive_v1(self, f: Callable[[Any], None]) -> "Builder":
            return self._register("p2.im.message.receive_v1", P2ImMessageReceiveV1Processor(f))

        def register_p1_customized_event(self, event_type: str, f: Callable[[Any], None]) -> "Builder":
            return self._register(f"p1.{event_type}", CustomizedEventProcessor(f))

        def register_p2_customized_event(self, event_type: str, f: Callable[[Any], None]) -> "Builder":
            return self._register(f"p2.{event_type}", CustomizedEventProcessor(f))

        def __getattr__(self, name: str) -> Any:
            if name.startswith("register_"):
                raise AttributeError(
                    f"{name}: 快速入口的事件分发器只内置 IM 消息事件；其它事件请用 register_p2_customized_event"
                )
            raise AttributeError(name)

        def build(self) -> EventDispatcherHandler:
            handler = EventDispatcherHandler()
            handler._encrypt_key = self._encrypt_key
            handler._verification_token = self._verification_token
            handler._processorMap = self._processorMap
            return handler

    module = types.ModuleType("lark_oapi.event.dispatcher_handler")
    module.EventDispatcherHandler = EventDispatcherHandler  # type: ignore[attr-defined]
    module.EventDispatcherHandlerBuilder = Builder  # type: ignore[attr-defined]
    module.__lark_fast_stub__ = True  # type: ignore[attr-defined]
    sys.modules["lark_oapi.event.dispatcher_handler"] = module


def load_lark() -> Any:
    """返回行为上等价于 ``import lark_oapi as lark`` 的对象（只保证 ``Client`` / ``LogLevel``）。

    lark-oapi 没安装时抛 ``ImportError``（调用方据此判断飞书不可用）。
    """
    global _light
    if _light is not None:
        return _light

    existing = sys.modules.get("lark_oapi")
    if existing is not None and not getattr(existing, "__lark_fast_stub__", False):
        return existing  # 完整的 SDK 已经被别处导入过，直接用

    try:
        _light = _build_light()
        return _light
    except Exception:
        logger.warning("[feishu] 快速导入飞书 SDK 失败，退回完整导入（会慢很多）", exc_info=True)
        _purge()
        return importlib.import_module("lark_oapi")  # 没安装则抛 ImportError

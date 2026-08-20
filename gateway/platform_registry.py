"""平台适配器注册表。

必须独立成模块：Gateway 以 ``python gateway/main.py`` 启动时，入口文件是
``__main__``，``from gateway.main import get_platform_adapter`` 会再加载一份
空的 ``gateway.main``，定时投递就找不到 weixin adapter。
"""

from __future__ import annotations

from typing import Optional

from gateway.base import BasePlatformAdapter

_adapters: dict[str, BasePlatformAdapter] = {}


def set_platform_adapter(platform: str, adapter: BasePlatformAdapter) -> None:
    key = (platform or "").strip().lower()
    if not key:
        return
    _adapters[key] = adapter


def get_platform_adapter(platform: str) -> Optional[BasePlatformAdapter]:
    return _adapters.get((platform or "").strip().lower())


def iter_platform_adapters() -> list[tuple[str, BasePlatformAdapter]]:
    return list(_adapters.items())

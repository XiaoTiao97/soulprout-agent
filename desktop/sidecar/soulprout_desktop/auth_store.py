"""登录凭证与云端地址。

凭证存放在 gateway 的 ``config_store`` 里（``agent_token`` / ``agent_user_id`` / ``agent_url``）：
桌面端合并了 gateway，它的各个渠道要用同一个登录态调用云端，所以只保留这一份，不另存。

``redirect_gateway_storage()`` 把 gateway 的 settings 文件重定向到桌面端的状态目录——
gateway 默认放在可执行文件旁边，装在 Program Files 之类的位置时不可写，也不应该和程序文件混在一起。
这是在运行时改一个模块级路径，不需要改 gateway 的任何代码。
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from . import paths, settings

logger = logging.getLogger(__name__)

_redirected = False


def redirect_gateway_storage() -> None:
    global _redirected
    from gateway import config_store

    target = paths.state_dir() / "gateway" / "settings.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    config_store._SETTINGS_PATH = target  # noqa: SLF001 - 有意重定向，见模块说明
    _redirected = True


def _store():
    from gateway import config_store

    if not _redirected:
        redirect_gateway_storage()
    return config_store


def agent_url() -> str:
    """云端地址：设置里的自定义地址 > 测试用 AGENT_URL > 官方云服务。

    桌面端默认永远是官网。本地联调请在设置里改，不要靠 AGENT_URL 锁死地址。
    测试仍可通过 AGENT_URL 指向假上游。
    """
    override = settings.agent_url_override()
    if override:
        return override
    env = os.getenv("AGENT_URL", "").strip()
    if env:
        return env.rstrip("/")
    return default_agent_url()


def default_agent_url() -> str:
    """官方云服务地址。不受 AGENT_URL / 本地联调地址影响，避免设置里把 localhost 当成官网。"""
    from gateway.config_store import _DEFAULT_AGENT_URL

    return _DEFAULT_AGENT_URL


def is_custom_agent_url() -> bool:
    """当前连的不是官方云服务（设置覆盖或测试用 AGENT_URL）。"""
    return agent_url().rstrip("/").lower() != default_agent_url().rstrip("/").lower()


def is_agent_url_locked() -> bool:
    """界面里始终允许改地址；测试用的 AGENT_URL 不再锁死设置。"""
    return False


def sync_gateway_agent_url() -> None:
    """让 gateway 记的地址跟桌面端实际连的一致（默认官网）。"""
    current = agent_url()
    store = _store()
    if store.get_agent_url().rstrip("/") != current.rstrip("/"):
        store.update_settings(agent_url=current)


def set_agent_url(url: Optional[str]) -> str:
    """切换云端地址（空 / None = 恢复官方云服务）。登录凭证是按服务器签发的，所以换地址必须清掉旧登录态。"""
    value = (url or "").strip().rstrip("/")
    settings.set_agent_url_override(value or None)
    new_url = agent_url()
    _store().update_settings(agent_url=new_url)
    clear_login()
    return new_url


def get_token() -> str:
    return _store().get_agent_token()


def get_user_id() -> str:
    return _store().get_agent_user_id()


def is_logged_in() -> bool:
    return bool(get_token())


def save_login(*, token: str, user_id: str = "", email: str = "", mode: str = "email") -> None:
    store = _store()
    store.update_settings(
        agent_url=agent_url(),
        agent_token=token,
        agent_user_id=user_id,
        agent_email=email,
        agent_login_mode=mode,
    )
    logger.info("已保存登录凭证 user_id=%s", user_id)


def clear_login() -> None:
    _store().update_settings(agent_token="", agent_user_id="", agent_email="")


def api_url(path: str, base: Optional[str] = None) -> str:
    """云端 HTTP 接口完整地址（自部署直连不加 /api，线上经反向代理加 /api），规则与 gateway 一致。"""
    return _store().api_path(base or agent_url(), path)


def ws_url(path: str, base: Optional[str] = None) -> str:
    return _store().ws_path(base or agent_url(), path)

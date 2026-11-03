"""Agent 后端日志。

替代 print：记录同时写到控制台和按天滚动的日志文件。
超过保留天数的旧文件会在启动和每天滚动时删掉。

带用户的记录把 user_id 放在整行最前面，例如：
    [1000001] 2026-11-03 16:14:01 INFO agent.services.agent - ...
没有用户时不占这个前缀。

当前用户来自 contextvars。HTTP 中间件、WebSocket、定时任务和 Chat
会在进入对应用户的工作时绑定它；同一任务里后续创建的子任务会继承。
"""

from __future__ import annotations

import logging
import os
import time
from contextlib import contextmanager
from contextvars import ContextVar, Token
from pathlib import Path
from logging.handlers import TimedRotatingFileHandler

_USER_ID: ContextVar[str | None] = ContextVar("agent_log_user_id", default=None)

_LOG_FILE_NAME = "agent.log"
_CONFIGURED = False
_FILE_HANDLER: logging.Handler | None = None
_STREAM_HANDLER: logging.Handler | None = None

_FOREIGN_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access", "uvicorn.asgi")


def _clean_user_id(user_id: str | None) -> str | None:
    if user_id is None:
        return None
    text = str(user_id).strip()
    return text or None


def current_user_id() -> str | None:
    return _USER_ID.get()


def bind_user_id(user_id: str | None) -> Token:
    """把当前任务的日志用户设为 user_id。空值会清掉前缀。返回的 token 交给 reset_user_id。"""
    return _USER_ID.set(_clean_user_id(user_id))


def reset_user_id(token: Token) -> None:
    _USER_ID.reset(token)


@contextmanager
def user_log_scope(user_id: str | None):
    """在一段工作期间绑定用户，结束时恢复之前的值。适合会接着处理其他用户的长任务。"""
    token = bind_user_id(user_id)
    try:
        yield
    finally:
        reset_user_id(token)


class UserIdFormatter(logging.Formatter):
    """有 user_id 时把它放在整行最前面。"""

    def format(self, record: logging.LogRecord) -> str:
        user_id = _clean_user_id(getattr(record, "user_id", None)) or current_user_id()
        record.user_prefix = f"[{user_id}] " if user_id else ""
        return super().format(record)


def _retention_days() -> int:
    raw = (os.getenv("AGENT_LOG_RETENTION_DAYS") or "3").strip()
    try:
        days = int(raw)
    except ValueError:
        days = 3
    return days if days > 0 else 3


def _log_dir() -> Path:
    configured = (os.getenv("AGENT_LOG_DIR") or "").strip()
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parent.parent / "logs"


def _log_level() -> int:
    name = (os.getenv("AGENT_LOG_LEVEL") or "INFO").strip().upper()
    return getattr(logging, name, logging.INFO)


def purge_expired_logs(log_dir: Path, retention_days: int, active_name: str = _LOG_FILE_NAME) -> None:
    """删掉保留期之前的滚动文件。正在写的 agent.log 不动。"""
    if not log_dir.is_dir():
        return
    cutoff = time.time() - retention_days * 86400
    for path in log_dir.iterdir():
        if not path.is_file() or path.name == active_name:
            continue
        if not path.name.startswith(active_name):
            continue
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink()
        except OSError:
            continue


class RetentionTimedRotatingFileHandler(TimedRotatingFileHandler):
    def __init__(self, filename: str, retention_days: int):
        self.retention_days = retention_days
        super().__init__(
            filename,
            when="midnight",
            interval=1,
            backupCount=retention_days,
            encoding="utf-8",
        )

    def doRollover(self) -> None:
        super().doRollover()
        purge_expired_logs(Path(self.baseFilename).parent, self.retention_days, Path(self.baseFilename).name)


def _adopt_foreign_loggers(level: int) -> None:
    """让 uvicorn 的日志也进同一套 handler，避免只出现在控制台。"""
    for name in _FOREIGN_LOGGERS:
        foreign = logging.getLogger(name)
        foreign.handlers.clear()
        foreign.propagate = True
        foreign.setLevel(level)


def setup_logging() -> None:
    """初始化根日志。重复调用是安全的，后一次会重新收编 uvicorn。"""
    global _CONFIGURED, _FILE_HANDLER, _STREAM_HANDLER

    level = _log_level()
    retention_days = _retention_days()
    log_dir = _log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    purge_expired_logs(log_dir, retention_days)

    formatter = UserIdFormatter(
        fmt="%(user_prefix)s%(asctime)s %(levelname)s %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    root = logging.getLogger()
    root.setLevel(level)

    if _FILE_HANDLER is None:
        _FILE_HANDLER = RetentionTimedRotatingFileHandler(str(log_dir / _LOG_FILE_NAME), retention_days)
        _FILE_HANDLER.setFormatter(formatter)
        _FILE_HANDLER.setLevel(level)
    if _STREAM_HANDLER is None:
        _STREAM_HANDLER = logging.StreamHandler()
        _STREAM_HANDLER.setFormatter(formatter)
        _STREAM_HANDLER.setLevel(level)

    if _FILE_HANDLER not in root.handlers:
        root.addHandler(_FILE_HANDLER)
    if _STREAM_HANDLER not in root.handlers:
        root.addHandler(_STREAM_HANDLER)

    _adopt_foreign_loggers(level)

    if not _CONFIGURED:
        _CONFIGURED = True
        logging.getLogger(__name__).info(
            "日志已启用 dir=%s retention_days=%s",
            log_dir,
            retention_days,
        )

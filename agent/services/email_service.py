"""
邮箱验证码服务（基于阿里云邮件推送 DM 服务）。

职责
----
1. 校验邮箱格式
2. 生成 6 位数字验证码，并发送到指定邮箱
3. 在进程内缓存验证码（带 TTL 与发送速率限制）
4. 提供 `verify_code` 接口用于一次性消费验证码

配置项（环境变量）
------------------
- ``ALIYUN_ACCESS_KEY_ID`` / ``ALIYUN_ACCESS_KEY_SECRET``  阿里云 AK/SK
- ``ALIYUN_DM_ENDPOINT``           DM 接入点，默认 ``dm.aliyuncs.com``
- ``ALIYUN_DM_ACCOUNT_NAME``       已验证的发信地址（必填）
- ``ALIYUN_DM_FROM_ALIAS``         发件人显示名，默认 ``Soulprout``
- ``EMAIL_CODE_TTL_SECONDS``       验证码有效期，默认 600（10 分钟）
- ``EMAIL_CODE_RESEND_SECONDS``    再次发送的最小间隔，默认 60（秒）
"""

from __future__ import annotations

import logging
import os
import random
import re
import time
from dataclasses import dataclass
from threading import Lock
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 邮箱格式校验
# ---------------------------------------------------------------------------

_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")


def is_valid_email(email: str) -> bool:
    return bool(email and _EMAIL_RE.match(email.strip()))


# ---------------------------------------------------------------------------
# 内存中的验证码缓存
# ---------------------------------------------------------------------------

@dataclass
class _CodeRecord:
    code: str
    expire_at: float
    last_sent_at: float


_codes: Dict[str, _CodeRecord] = {}
_lock = Lock()


def _ttl_seconds() -> int:
    try:
        return int(os.getenv("EMAIL_CODE_TTL_SECONDS", "600"))
    except ValueError:
        return 600


def _resend_seconds() -> int:
    try:
        return int(os.getenv("EMAIL_CODE_RESEND_SECONDS", "60"))
    except ValueError:
        return 60


def _norm_email(email: str) -> str:
    return email.strip().lower()


# ---------------------------------------------------------------------------
# 阿里云 DM 客户端
# ---------------------------------------------------------------------------

def _build_dm_client():
    """按需创建 DM 客户端（懒加载，避免在未配置邮件时崩溃）。"""
    try:
        from alibabacloud_dm20151123.client import Client as Dm20151123Client
        from alibabacloud_tea_openapi import models as open_api_models
    except ImportError as exc:
        raise RuntimeError(
            "未安装 alibabacloud_dm20151123 / alibabacloud_tea_openapi，请先 pip install 这些依赖"
        ) from exc

    access_key_id = os.getenv("ALIYUN_ACCESS_KEY_ID", "").strip()
    access_key_secret = os.getenv("ALIYUN_ACCESS_KEY_SECRET", "").strip()
    if not access_key_id or not access_key_secret:
        raise RuntimeError("未配置 ALIYUN_ACCESS_KEY_ID / ALIYUN_ACCESS_KEY_SECRET")

    config = open_api_models.Config(
        access_key_id=access_key_id,
        access_key_secret=access_key_secret,
    )
    config.endpoint = os.getenv("ALIYUN_DM_ENDPOINT", "dm.aliyuncs.com").strip()
    return Dm20151123Client(config)


def _send_verification_email(email: str, code: str) -> None:
    """通过阿里云 DM 同步发送一封验证码邮件。失败时抛出异常。"""
    from alibabacloud_dm20151123 import models as dm_20151123_models
    from alibabacloud_tea_util import models as util_models

    account_name = os.getenv("ALIYUN_DM_ACCOUNT_NAME", "").strip()
    if not account_name:
        raise RuntimeError("未配置 ALIYUN_DM_ACCOUNT_NAME（发信邮箱地址）")

    from_alias = os.getenv("ALIYUN_DM_FROM_ALIAS", "Soulprout").strip() or "Soulprout"

    client = _build_dm_client()

    subject = f"【Soulprout】您的登录验证码：{code}"
    html_body = f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width:520px; margin:0 auto; padding:24px;">
      <h2 style="color:#1eb48c; margin:0 0 16px;">Soulprout 登录验证码</h2>
      <p style="color:#333; font-size:15px; line-height:1.7;">您好，<br/>您正在登录 Soulprout，本次登录的验证码为：</p>
      <div style="margin:20px 0; padding:18px 28px; background:#f5fbf9; border:1px solid #1eb48c33; border-radius:12px; text-align:center;">
        <span style="font-size:32px; font-weight:700; letter-spacing:8px; color:#1eb48c;">{code}</span>
      </div>
      <p style="color:#666; font-size:13px; line-height:1.7;">验证码 10 分钟内有效，请勿向他人泄露。若非本人操作请忽略本邮件。</p>
      <p style="color:#999; font-size:12px; margin-top:24px;">—— Soulprout 团队</p>
    </div>
    """
    text_body = f"您的 Soulprout 登录验证码为：{code}，10 分钟内有效，请勿泄露。"

    request = dm_20151123_models.SingleSendMailRequest(
        account_name=account_name,
        address_type=1,
        reply_to_address=False,
        to_address=email,
        subject=subject,
        html_body=html_body,
        text_body=text_body,
        from_alias=from_alias,
    )
    runtime = util_models.RuntimeOptions()
    resp = client.single_send_mail_with_options(request, runtime)
    logger.info("[Email] 验证码已发送 email=%s envId=%s", email, getattr(resp.body, "env_id", "?"))


# ---------------------------------------------------------------------------
# 对外 API
# ---------------------------------------------------------------------------

class EmailSendError(Exception):
    """发送验证码失败时抛出的统一异常。"""


def request_email_code(email: str) -> None:
    """生成一个 6 位验证码，缓存在内存中并通过阿里云 DM 发出。

    抛出 :class:`EmailSendError`：邮箱格式非法、未配置 DM 服务、发送速率受限或第三方 API 异常。
    """
    if not is_valid_email(email):
        raise EmailSendError("邮箱格式不合法")

    key = _norm_email(email)
    now = time.time()
    resend_gap = _resend_seconds()

    with _lock:
        record = _codes.get(key)
        if record and (now - record.last_sent_at) < resend_gap:
            wait = int(resend_gap - (now - record.last_sent_at))
            raise EmailSendError(f"请求过于频繁，请 {wait} 秒后再试")

    code = f"{random.randint(0, 999999):06d}"

    # 实际发送（耗时，放锁外）
    try:
        _send_verification_email(key, code)
    except Exception as exc:
        logger.error("[Email] 验证码发送失败 email=%s: %s", key, exc, exc_info=True)
        raise EmailSendError(f"邮件发送失败：{exc}")

    with _lock:
        _codes[key] = _CodeRecord(
            code=code,
            expire_at=now + _ttl_seconds(),
            last_sent_at=now,
        )
        _cleanup_locked(now)


def verify_email_code(email: str, code: str) -> bool:
    """一次性校验验证码。成功后立即移除缓存。"""
    if not email or not code:
        return False

    key = _norm_email(email)
    submitted = code.strip()
    now = time.time()

    with _lock:
        record = _codes.get(key)
        if not record:
            return False
        if record.expire_at < now:
            _codes.pop(key, None)
            return False
        if record.code != submitted:
            return False
        _codes.pop(key, None)
        return True


def _cleanup_locked(now: float) -> None:
    """清理已过期条目（调用前需持有 _lock）。"""
    expired = [k for k, v in _codes.items() if v.expire_at < now]
    for k in expired:
        _codes.pop(k, None)

"""信封加密（Envelope Encryption）模块。

设计要点：
1. 主密钥（KEK）仅从服务器环境变量（API_KEY_MASTER_KEYS / API_KEY_MASTER_KEY）加载，绝不写入数据库。
   支持多版本主密钥轮换：格式为 `v2:<base64_or_hex>,v1:<base64_or_hex>`；加密使用最新版本，解密按记录的 kek_version 匹配。
   若未显式配置，则使用 HKDF-SHA256 从 JWT_SECRET_KEY 派生 32 字节主密钥（并打印启动警告，建议生产环境独立配置）。
2. 每条用户 Key 独立生成 32 字节随机 DEK（数据加密密钥）。
3. 使用 AES-256-GCM 加密，cryptography 的 AESGCM.encrypt 自动将 16 字节认证标签（Tag）拼在密文末尾。
4. 加密与解密全程强制绑定 AAD（Additional Authenticated Data）= `f"{user_id}:{provider}".encode("utf-8")`，
   防止跨用户或跨平台密文搬运篡改。
"""

from __future__ import annotations

import base64
import hashlib
import logging
import os
from dataclasses import dataclass
from typing import Dict, Tuple

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

logger = logging.getLogger(__name__)

_NONCE_LEN = 12
_DEK_LEN = 32
_KEK_CACHE: Tuple[int, Dict[int, bytes]] | None = None


@dataclass(frozen=True)
class EnvelopePayload:
    kek_version: int
    dek_iv: bytes
    dek_wrapped: bytes
    key_iv: bytes
    key_cipher: bytes


def _decode_raw_key(raw: str) -> bytes:
    """将 64 位 hex、base64 或普通长字符串解析为 32 字节密钥。"""
    text = raw.strip()
    if len(text) == 64:
        try:
            return bytes.fromhex(text)
        except ValueError:
            pass
    try:
        decoded = base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))
        if len(decoded) == 32:
            return decoded
    except Exception:
        pass
    try:
        decoded = base64.b64decode(text)
        if len(decoded) == 32:
            return decoded
    except Exception:
        pass
    # 任意高熵口令通过 HKDF-SHA256 派生为标准 32 字节密钥
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"soulprout-api-key-kek-salt-v1",
        info=b"soulprout-envelope-kek",
    )
    return hkdf.derive(text.encode("utf-8"))


def _load_master_keys() -> Tuple[int, Dict[int, bytes]]:
    """加载主密钥表，返回 (最新版本号, {版本号: 32字节密钥})。"""
    global _KEK_CACHE
    if _KEK_CACHE is not None:
        return _KEK_CACHE

    multi_raw = (os.getenv("API_KEY_MASTER_KEYS") or "").strip()
    single_raw = (os.getenv("API_KEY_MASTER_KEY") or "").strip()

    keys: Dict[int, bytes] = {}
    if multi_raw:
        for item in multi_raw.split(","):
            item = item.strip()
            if not item:
                continue
            if ":" in item:
                ver_str, secret_str = item.split(":", 1)
                ver = int(ver_str.strip().lstrip("vV"))
                keys[ver] = _decode_raw_key(secret_str)
            else:
                keys[1] = _decode_raw_key(item)
    elif single_raw:
        keys[1] = _decode_raw_key(single_raw)
    else:
        fallback = (
            os.getenv("JWT_SECRET_KEY")
            or "soulprout-local-dev-only-change-before-production"
        ).strip()
        logger.warning(
            "[crypto] 未配置独立的 API_KEY_MASTER_KEY，当前从 JWT_SECRET_KEY 派生主密钥；"
            "SaaS 生产环境请在 agent/.env 中配置独立的 API_KEY_MASTER_KEY（32字节随机 hex/base64）"
        )
        keys[1] = _decode_raw_key(f"kek-fallback:{fallback}")

    latest_version = max(keys.keys())
    _KEK_CACHE = (latest_version, keys)
    return _KEK_CACHE


def build_aad(user_id: str, provider: str) -> bytes:
    """构造绑定用户与供应商的 AAD 上下文。"""
    uid = str(user_id or "").strip()
    prov = str(provider or "").strip().lower()
    if not uid or not prov:
        raise ValueError("user_id 与 provider 不能为空")
    return f"{uid}:{prov}".encode("utf-8")


def encrypt_secret(plaintext: str, user_id: str, provider: str) -> EnvelopePayload:
    """使用信封加密保护明文 API Key。"""
    secret = (plaintext or "").strip()
    if not secret:
        raise ValueError("待加密的密钥不能为空")

    latest_ver, keys = _load_master_keys()
    kek = keys[latest_ver]
    aad = build_aad(user_id, provider)

    # 1. 生成当前记录独立的随机 32 字节 DEK
    dek = os.urandom(_DEK_LEN)

    # 2. 用 DEK 加密用户真实 API Key（AESGCM 自动将 16B Tag 附在密文后）
    key_iv = os.urandom(_NONCE_LEN)
    key_cipher = AESGCM(dek).encrypt(key_iv, secret.encode("utf-8"), aad)

    # 3. 用主密钥（KEK）包裹 DEK（同样绑定 AAD）
    dek_iv = os.urandom(_NONCE_LEN)
    dek_wrapped = AESGCM(kek).encrypt(dek_iv, dek, aad)

    return EnvelopePayload(
        kek_version=latest_ver,
        dek_iv=dek_iv,
        dek_wrapped=dek_wrapped,
        key_iv=key_iv,
        key_cipher=key_cipher,
    )


def decrypt_secret(payload: EnvelopePayload, user_id: str, provider: str) -> str:
    """解密信封密文，若 AAD 不匹配或密文被篡改则直接抛出异常。"""
    _, keys = _load_master_keys()
    kek = keys.get(payload.kek_version)
    if kek is None:
        raise RuntimeError(f"找不到对应版本的主密钥: kek_version={payload.kek_version}")

    aad = build_aad(user_id, provider)
    dek = AESGCM(kek).decrypt(payload.dek_iv, payload.dek_wrapped, aad)
    raw = AESGCM(dek).decrypt(payload.key_iv, payload.key_cipher, aad)
    return raw.decode("utf-8")


def hash_api_key(plaintext: str) -> str:
    """生成用于索引查找的不可逆 SHA-256 摘要（如 Rokid Bearer Token 查找）。"""
    return hashlib.sha256((plaintext or "").strip().encode("utf-8")).hexdigest()


def mask_api_key(plaintext: str) -> str:
    """生成仅用于前端展示的脱敏掩码（如 sk-a****9f2b），绝不暴露完整 Key。"""
    s = (plaintext or "").strip()
    if len(s) <= 8:
        return s[:2] + "****"
    prefix_len = 6 if s.startswith("sk-") and len(s) > 12 else 4
    return f"{s[:prefix_len]}****{s[-4:]}"

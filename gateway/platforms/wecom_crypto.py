"""企业微信回调加解密模块。

实现与腾讯官方 WXBizMsgCrypt SDK 兼容的 AES-CBC 加解密，
用于企业微信回调消息的签名校验、加密与解密。
"""

from __future__ import annotations

import base64
import hashlib
import os
import secrets
import socket
import struct
from typing import Optional
from xml.etree import ElementTree as ET

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


class WeComCryptoError(Exception):
    """加解密相关错误基类。"""


class SignatureError(WeComCryptoError):
    """签名验证失败。"""


class DecryptError(WeComCryptoError):
    """解密失败。"""


class EncryptError(WeComCryptoError):
    """加密失败。"""


class _PKCS7Encoder:
    block_size = 32

    @classmethod
    def encode(cls, text: bytes) -> bytes:
        amount_to_pad = cls.block_size - (len(text) % cls.block_size)
        if amount_to_pad == 0:
            amount_to_pad = cls.block_size
        pad = bytes([amount_to_pad]) * amount_to_pad
        return text + pad

    @classmethod
    def decode(cls, decrypted: bytes) -> bytes:
        if not decrypted:
            raise DecryptError("empty decrypted payload")
        pad = decrypted[-1]
        if pad < 1 or pad > cls.block_size:
            raise DecryptError("invalid PKCS7 padding")
        if decrypted[-pad:] != bytes([pad]) * pad:
            raise DecryptError("malformed PKCS7 padding")
        return decrypted[:-pad]


def _sha1_signature(token: str, timestamp: str, nonce: str, encrypt: str) -> str:
    parts = sorted([token, timestamp, nonce, encrypt])
    return hashlib.sha1("".join(parts).encode("utf-8")).hexdigest()


class WXBizMsgCrypt:
    """企业微信回调加解密工具类。

    参数：
        token:            企业微信后台配置的 Token
        encoding_aes_key: 企业微信后台生成的 EncodingAESKey（43位）
        receive_id:       接收方 ID，自建应用填企业 CorpID
    """

    def __init__(self, token: str, encoding_aes_key: str, receive_id: str):
        if not token:
            raise ValueError("token 不能为空")
        if not encoding_aes_key:
            raise ValueError("encoding_aes_key 不能为空")
        if len(encoding_aes_key) != 43:
            raise ValueError("encoding_aes_key 长度必须为 43 个字符")
        if not receive_id:
            raise ValueError("receive_id 不能为空")

        self.token = token
        self.receive_id = receive_id
        self.key = base64.b64decode(encoding_aes_key + "=")
        self.iv = self.key[:16]

    def verify_url(self, msg_signature: str, timestamp: str, nonce: str, echostr: str) -> str:
        """验证企业微信回调 URL，返回解密后的 echostr。"""
        plain = self.decrypt(msg_signature, timestamp, nonce, echostr)
        return plain.decode("utf-8")

    def decrypt(self, msg_signature: str, timestamp: str, nonce: str, encrypt: str) -> bytes:
        """验签并解密企业微信回调消息，返回 XML 明文字节。"""
        expected = _sha1_signature(self.token, timestamp, nonce, encrypt)
        if expected != msg_signature:
            raise SignatureError("签名不匹配")
        try:
            cipher_text = base64.b64decode(encrypt)
        except Exception as exc:
            raise DecryptError(f"base64 解码失败: {exc}") from exc
        try:
            cipher = Cipher(
                algorithms.AES(self.key), modes.CBC(self.iv), backend=default_backend()
            )
            decryptor = cipher.decryptor()
            padded = decryptor.update(cipher_text) + decryptor.finalize()
            plain = _PKCS7Encoder.decode(padded)
            content = plain[16:]  # 跳过 16 字节随机前缀
            xml_length = socket.ntohl(struct.unpack("I", content[:4])[0])
            xml_content = content[4 : 4 + xml_length]
            receive_id = content[4 + xml_length :].decode("utf-8")
        except WeComCryptoError:
            raise
        except Exception as exc:
            raise DecryptError(f"解密失败: {exc}") from exc

        if receive_id != self.receive_id:
            raise DecryptError("receive_id 不匹配")
        return xml_content

    def encrypt(
        self,
        plaintext: str,
        nonce: Optional[str] = None,
        timestamp: Optional[str] = None,
    ) -> str:
        """加密明文并返回带签名的 XML 字符串（用于主动回复场景）。"""
        import time as _time

        nonce = nonce or self._random_nonce()
        timestamp = timestamp or str(int(_time.time()))
        encrypt = self._encrypt_bytes(plaintext.encode("utf-8"))
        signature = _sha1_signature(self.token, timestamp, nonce, encrypt)
        root = ET.Element("xml")
        ET.SubElement(root, "Encrypt").text = encrypt
        ET.SubElement(root, "MsgSignature").text = signature
        ET.SubElement(root, "TimeStamp").text = timestamp
        ET.SubElement(root, "Nonce").text = nonce
        return ET.tostring(root, encoding="unicode")

    def _encrypt_bytes(self, raw: bytes) -> str:
        try:
            random_prefix = os.urandom(16)
            msg_len = struct.pack("I", socket.htonl(len(raw)))
            payload = random_prefix + msg_len + raw + self.receive_id.encode("utf-8")
            padded = _PKCS7Encoder.encode(payload)
            cipher = Cipher(
                algorithms.AES(self.key), modes.CBC(self.iv), backend=default_backend()
            )
            encryptor = cipher.encryptor()
            encrypted = encryptor.update(padded) + encryptor.finalize()
            return base64.b64encode(encrypted).decode("utf-8")
        except Exception as exc:
            raise EncryptError(f"加密失败: {exc}") from exc

    @staticmethod
    def _random_nonce(length: int = 10) -> str:
        alphabet = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
        return "".join(secrets.choice(alphabet) for _ in range(length))

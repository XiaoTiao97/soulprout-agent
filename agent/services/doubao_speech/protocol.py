"""豆包语音 V3 二进制帧编解码（流式识别 sauc 与双向流式合成 tts/bidirection 共用）。

帧头固定 4 字节::

    byte0: 协议版本(高4位=1) | 头大小(低4位=1，单位 4 字节)
    byte1: 消息类型(高4位)   | 标志位(低4位)
    byte2: 序列化方式(高4位) | 压缩方式(低4位)
    byte3: 保留

其后按「消息类型 + 标志位」的不同追加字段，全部大端序。
"""

from __future__ import annotations

import gzip
import json
import struct
from dataclasses import dataclass, field
from typing import Any, Optional

# ---- 消息类型 ----
MSG_FULL_CLIENT = 0b0001
MSG_AUDIO_ONLY_CLIENT = 0b0010  # 仅识别：纯音频包
MSG_FULL_SERVER = 0b1001
MSG_AUDIO_ONLY_SERVER = 0b1011  # 仅合成：音频响应
MSG_ERROR = 0b1111

# ---- 标志位 ----
FLAG_NONE = 0b0000
FLAG_POS_SEQ = 0b0001  # 带正序号
FLAG_LAST = 0b0010  # 最后一包（无序号）
FLAG_NEG_SEQ = 0b0011  # 最后一包（带负序号）
FLAG_WITH_EVENT = 0b0100  # 带 event 编号（合成协议）

# ---- 序列化 / 压缩 ----
SER_RAW = 0b0000
SER_JSON = 0b0001
COMP_NONE = 0b0000
COMP_GZIP = 0b0001

# ---- 合成协议 event ----
EV_START_CONNECTION = 1
EV_FINISH_CONNECTION = 2
EV_CONNECTION_STARTED = 50
EV_CONNECTION_FAILED = 51
EV_CONNECTION_FINISHED = 52
EV_START_SESSION = 100
EV_CANCEL_SESSION = 101
EV_FINISH_SESSION = 102
EV_SESSION_STARTED = 150
EV_SESSION_CANCELED = 151
EV_SESSION_FINISHED = 152
EV_SESSION_FAILED = 153
EV_TASK_REQUEST = 200
EV_TTS_SENTENCE_START = 350
EV_TTS_SENTENCE_END = 351
EV_TTS_RESPONSE = 352

# 这些 event 的帧里不带 session id，而是带 connection id（或什么都不带）
_CONNECTION_LEVEL_EVENTS = {
    EV_START_CONNECTION,
    EV_FINISH_CONNECTION,
    EV_CONNECTION_STARTED,
    EV_CONNECTION_FAILED,
    EV_CONNECTION_FINISHED,
}
# 客户端发出的连接级 event：无任何 id 字段
_CLIENT_CONNECTION_EVENTS = {EV_START_CONNECTION, EV_FINISH_CONNECTION}


def _header(msg_type: int, flags: int, serialization: int, compression: int) -> bytes:
    return bytes([(0b0001 << 4) | 0b0001, (msg_type << 4) | flags, (serialization << 4) | compression, 0])


def _json_bytes(obj: Any) -> bytes:
    return json.dumps(obj, ensure_ascii=False).encode("utf-8")


# ======================================================================
# 识别（sauc）
# ======================================================================

def asr_full_request(params: dict) -> bytes:
    """首包：带配置的 JSON，不压缩、无序号。"""
    payload = _json_bytes(params)
    return _header(MSG_FULL_CLIENT, FLAG_NONE, SER_JSON, COMP_NONE) + struct.pack(">I", len(payload)) + payload


def asr_audio_request(audio: bytes, last: bool = False) -> bytes:
    """音频包；last=True 表示最后一包（通知服务端音频结束）。"""
    flags = FLAG_LAST if last else FLAG_NONE
    return _header(MSG_AUDIO_ONLY_CLIENT, flags, SER_RAW, COMP_NONE) + struct.pack(">I", len(audio)) + audio


@dataclass
class AsrServerMessage:
    is_error: bool = False
    error_code: int = 0
    sequence: Optional[int] = None
    is_last: bool = False
    payload: Any = None  # 已反序列化的 JSON（dict）或错误文本


def parse_asr_server(data: bytes) -> AsrServerMessage:
    if len(data) < 4:
        raise ValueError("ASR 帧过短")
    msg_type = data[1] >> 4
    flags = data[1] & 0x0F
    serialization = data[2] >> 4
    compression = data[2] & 0x0F
    header_size = (data[0] & 0x0F) * 4
    pos = header_size

    if msg_type == MSG_ERROR:
        code = struct.unpack_from(">I", data, pos)[0]
        size = struct.unpack_from(">I", data, pos + 4)[0]
        body = data[pos + 8 : pos + 8 + size]
        return AsrServerMessage(is_error=True, error_code=code, payload=body.decode("utf-8", "replace"))

    if msg_type != MSG_FULL_SERVER:
        raise ValueError(f"未知的 ASR 消息类型: {msg_type:#06b}")

    msg = AsrServerMessage()
    if flags & 0b0001:
        msg.sequence = struct.unpack_from(">i", data, pos)[0]
        pos += 4
    msg.is_last = bool(flags & 0b0010)
    size = struct.unpack_from(">I", data, pos)[0]
    pos += 4
    body = data[pos : pos + size]
    if compression == COMP_GZIP:
        body = gzip.decompress(body)
    msg.payload = json.loads(body.decode("utf-8")) if serialization == SER_JSON and body else {}
    return msg


# ======================================================================
# 合成（tts/bidirection）
# ======================================================================

def tts_event_frame(event: int, payload: dict | bytes | None = None, session_id: str | None = None) -> bytes:
    """客户端事件帧。连接级事件不带 session id；会话级事件必须带。"""
    if payload is None:
        body = b"{}"
    elif isinstance(payload, (bytes, bytearray)):
        body = bytes(payload)
    else:
        body = _json_bytes(payload)

    out = _header(MSG_FULL_CLIENT, FLAG_WITH_EVENT, SER_JSON, COMP_NONE)
    out += struct.pack(">i", event)
    if event not in _CLIENT_CONNECTION_EVENTS:
        sid = (session_id or "").encode("utf-8")
        out += struct.pack(">I", len(sid)) + sid
    out += struct.pack(">I", len(body)) + body
    return out


@dataclass
class TtsServerMessage:
    is_error: bool = False
    error_code: int = 0
    event: int = 0
    session_id: str = ""
    is_audio: bool = False
    audio: bytes = b""
    payload: Any = field(default_factory=dict)


def parse_tts_server(data: bytes) -> TtsServerMessage:
    if len(data) < 4:
        raise ValueError("TTS 帧过短")
    msg_type = data[1] >> 4
    flags = data[1] & 0x0F
    serialization = data[2] >> 4
    compression = data[2] & 0x0F
    pos = (data[0] & 0x0F) * 4

    if msg_type == MSG_ERROR:
        code = struct.unpack_from(">I", data, pos)[0]
        size = struct.unpack_from(">I", data, pos + 4)[0]
        body = data[pos + 8 : pos + 8 + size]
        return TtsServerMessage(is_error=True, error_code=code, payload=body.decode("utf-8", "replace"))

    if msg_type not in (MSG_FULL_SERVER, MSG_AUDIO_ONLY_SERVER):
        raise ValueError(f"未知的 TTS 消息类型: {msg_type:#06b}")

    msg = TtsServerMessage()
    if flags & FLAG_WITH_EVENT:
        msg.event = struct.unpack_from(">i", data, pos)[0]
        pos += 4
        # 连接级与会话级事件的第一个 id 字段都是「长度 + 字符串」，只是含义不同
        if msg.event not in (EV_FINISH_CONNECTION, EV_START_CONNECTION):
            id_len = struct.unpack_from(">I", data, pos)[0]
            pos += 4
            raw_id = data[pos : pos + id_len].decode("utf-8", "replace")
            pos += id_len
            if msg.event not in _CONNECTION_LEVEL_EVENTS:
                msg.session_id = raw_id

    size = struct.unpack_from(">I", data, pos)[0]
    pos += 4
    body = data[pos : pos + size]
    if compression == COMP_GZIP:
        body = gzip.decompress(body)

    if msg_type == MSG_AUDIO_ONLY_SERVER:
        msg.is_audio = True
        msg.audio = body
    elif serialization == SER_JSON and body:
        try:
            msg.payload = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError:
            msg.payload = {}
    return msg

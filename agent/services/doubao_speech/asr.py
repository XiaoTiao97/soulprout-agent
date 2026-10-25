"""豆包流式语音识别（大模型 sauc，双向流式优化版 bigmodel_async）。

用法::

    asr = DoubaoAsr(end_window_ms=800)
    await asr.connect()
    await asr.send_audio(pcm_bytes)      # 16k / 16bit / 单声道，建议 100~200ms 一包
    async for ev in asr.events():        # {"type": "partial"|"final", "text": ...}
        ...
    await asr.finish()                   # 发送最后一包
    await asr.close()

断句：开启 ``show_utterances`` 后，服务端按静音时长（``end_window_size``）切分语句，
每句结束时该 utterance 的 ``definite`` 为 True，这里转成 ``final`` 事件。
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, AsyncIterator, Optional

import aiohttp

from agent.core.config import Config
from agent.services.doubao_speech import protocol as p

logger = logging.getLogger(__name__)

ASR_URL = "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async"
# 豆包流式语音识别模型 2.0（按时长计费）
ASR_RESOURCE_ID = "volc.seedasr.sauc.duration"
SAMPLE_RATE = 16000

config = Config()

# 断句静音时长的允许范围（毫秒）。官方下限 200。
MIN_END_WINDOW_MS = 200
MAX_END_WINDOW_MS = 5000


class DoubaoSpeechNotConfigured(RuntimeError):
    pass


def speech_configured() -> bool:
    return bool((config.doubao_speech_api_key or "").strip())


def auth_headers(resource_id: str) -> dict[str, str]:
    """新版控制台：只需要一个 API Key（X-Api-Key）。"""
    if not speech_configured():
        raise DoubaoSpeechNotConfigured("未配置 DOUBAO_SPEECH_API_KEY")
    return {
        "X-Api-Key": config.doubao_speech_api_key.strip(),
        "X-Api-Resource-Id": resource_id,
        "X-Api-Connect-Id": str(uuid.uuid4()),
    }


class DoubaoAsr:
    def __init__(self, end_window_ms: int = 800, user_id: str = "standby"):
        self.end_window_ms = max(MIN_END_WINDOW_MS, min(MAX_END_WINDOW_MS, int(end_window_ms)))
        self.user_id = user_id
        self._session: Optional[aiohttp.ClientSession] = None
        self._ws: Optional[aiohttp.ClientWebSocketResponse] = None
        # 已经以 final 形式汇报过的 utterance（用起始时间做 key）
        self._finalized: set[Any] = set()
        self.log_id = ""

    async def connect(self) -> None:
        headers = auth_headers(ASR_RESOURCE_ID)
        self._session = aiohttp.ClientSession()
        try:
            self._ws = await self._session.ws_connect(ASR_URL, headers=headers, max_msg_size=0, heartbeat=None)
        except aiohttp.WSServerHandshakeError as e:
            await self.close()
            raise RuntimeError(f"连接豆包识别服务失败: HTTP {e.status} {e.message}") from e
        except Exception:
            await self.close()
            raise
        try:
            self.log_id = self._ws._response.headers.get("X-Tt-Logid", "")  # type: ignore[union-attr]
        except Exception:
            pass

        params = {
            "user": {"uid": self.user_id},
            "audio": {"format": "pcm", "codec": "raw", "rate": SAMPLE_RATE, "bits": 16, "channel": 1},
            "request": {
                "model_name": "bigmodel",
                "enable_itn": True,
                "enable_punc": True,
                "enable_ddc": True,
                "show_utterances": True,
                "enable_nonstream": True,  # 二遍识别，与官方示例一致，提高准确率
                "end_window_size": self.end_window_ms,
            },
        }
        await self._ws.send_bytes(p.asr_full_request(params))

    async def send_audio(self, pcm: bytes, last: bool = False) -> None:
        if self._ws is None or self._ws.closed:
            return
        await self._ws.send_bytes(p.asr_audio_request(pcm, last=last))

    async def finish(self) -> None:
        """发送最后一包，服务端会把尚未判停的内容收尾成 definite。"""
        await self.send_audio(b"", last=True)

    async def events(self) -> AsyncIterator[dict]:
        """持续产出 partial / final / error 事件，连接关闭后结束。"""
        assert self._ws is not None
        async for raw in self._ws:
            if raw.type == aiohttp.WSMsgType.BINARY:
                try:
                    msg = p.parse_asr_server(raw.data)
                except Exception as e:  # 帧解析失败不应拖垮整个会话
                    logger.warning("[doubao-asr] 帧解析失败: %s", e)
                    continue
                if msg.is_error:
                    yield {"type": "error", "code": msg.error_code, "message": str(msg.payload)}
                    return
                for ev in self._convert(msg.payload):
                    yield ev
                if msg.is_last:
                    return
            elif raw.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.CLOSING, aiohttp.WSMsgType.ERROR):
                return

    def _convert(self, payload: dict) -> list[dict]:
        result = (payload or {}).get("result") or {}
        out: list[dict] = []
        utterances = result.get("utterances") or []
        if not utterances:
            text = (result.get("text") or "").strip()
            if text:
                out.append({"type": "partial", "text": text})
            return out

        partial = ""
        for u in utterances:
            text = (u.get("text") or "").strip()
            key = u.get("start_time", text)
            if u.get("definite"):
                if key in self._finalized:
                    continue
                self._finalized.add(key)
                if text:
                    out.append({"type": "final", "text": text, "start_ms": u.get("start_time"), "end_ms": u.get("end_time")})
            else:
                partial = text
        if partial:
            out.append({"type": "partial", "text": partial})
        return out

    async def close(self) -> None:
        try:
            if self._ws is not None and not self._ws.closed:
                await self._ws.close()
        finally:
            if self._session is not None and not self._session.closed:
                await self._session.close()
            self._ws = None
            self._session = None

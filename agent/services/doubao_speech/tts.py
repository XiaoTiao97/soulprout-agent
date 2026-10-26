"""豆包双向流式语音合成（V3 tts/bidirection）。

一个 ``DoubaoTts`` 对应一次连接 + 一个会话（通常对应 Agent 的一轮回复）::

    tts = DoubaoTts(voice="...")
    await tts.connect()                  # StartConnection + StartSession，等到 SessionStarted
    await tts.send_text("第一句。")      # 可多次调用，边生成边送
    await tts.finish()                   # 文本送完（FinishSession）
    async for ev in tts.events():        # audio / sentence_start / sentence_end / done / error
        ...
    await tts.close()

打断：``await tts.cancel()``。
"""

from __future__ import annotations

import logging
import uuid
from typing import AsyncIterator, Optional

import aiohttp

from agent.core.config import Config
from agent.services.doubao_speech import protocol as p
from agent.services.doubao_speech.asr import auth_headers

logger = logging.getLogger(__name__)

TTS_URL = "wss://openspeech.bytedance.com/api/v3/tts/bidirection"
# 豆包语音合成模型 2.0
TTS_RESOURCE_ID = "seed-tts-2.0"
SAMPLE_RATE = 24000

# 可选音色（2.0 音色）：key 是界面 / 接口传的音色 id，value 是豆包 speaker
VOICES: dict[str, str] = {
    "female": "zh_female_xiaohe_uranus_bigtts",
    "male": "zh_male_liufei_uranus_bigtts",
}
DEFAULT_VOICE = "female"

config = Config()


def resolve_voice(voice: str | None) -> str:
    """接受音色 id（female / male）或完整 speaker 名；不认识的一律用默认女声。"""
    v = (voice or "").strip()
    if v in VOICES:
        return VOICES[v]
    if v in VOICES.values():
        return v
    return VOICES[DEFAULT_VOICE]


class DoubaoTts:
    def __init__(self, voice: str | None = None, speech_rate: int = 0, user_id: str = "standby"):
        self.voice = resolve_voice(voice)
        self.speech_rate = max(-50, min(100, int(speech_rate)))
        self.user_id = user_id
        self.session_id = uuid.uuid4().hex
        self._session: Optional[aiohttp.ClientSession] = None
        self._ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self._started = False
        self.log_id = ""

    def _base(self, event: int) -> dict:
        return {"event": event}

    def _audio_params(self) -> dict:
        return {"format": "pcm", "sample_rate": SAMPLE_RATE, "speech_rate": self.speech_rate}

    async def _recv(self) -> p.TtsServerMessage:
        assert self._ws is not None
        while True:
            raw = await self._ws.receive()
            if raw.type == aiohttp.WSMsgType.BINARY:
                return p.parse_tts_server(raw.data)
            if raw.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.CLOSING, aiohttp.WSMsgType.ERROR):
                raise RuntimeError("豆包合成连接已关闭")

    async def connect(self) -> None:
        headers = auth_headers(TTS_RESOURCE_ID)
        self._session = aiohttp.ClientSession()
        try:
            self._ws = await self._session.ws_connect(TTS_URL, headers=headers, max_msg_size=0, heartbeat=None)
        except aiohttp.WSServerHandshakeError as e:
            await self.close()
            raise RuntimeError(f"连接豆包合成服务失败: HTTP {e.status} {e.message}") from e
        except Exception:
            await self.close()
            raise

        try:
            await self._ws.send_bytes(p.tts_event_frame(p.EV_START_CONNECTION))
            msg = await self._recv()
            if msg.is_error or msg.event == p.EV_CONNECTION_FAILED:
                raise RuntimeError(f"豆包合成建连失败: {msg.payload}")

            start = self._base(p.EV_START_SESSION)
            start["req_params"] = {"speaker": self.voice, "audio_params": self._audio_params()}
            await self._ws.send_bytes(p.tts_event_frame(p.EV_START_SESSION, start, self.session_id))
            msg = await self._recv()
            if msg.is_error or msg.event == p.EV_SESSION_FAILED:
                raise RuntimeError(f"豆包合成会话启动失败: {msg.payload}")
            if msg.event != p.EV_SESSION_STARTED:
                raise RuntimeError(f"豆包合成会话启动异常，收到 event={msg.event}")
        except Exception:
            await self.close()
            raise
        self._started = True

    async def send_text(self, text: str) -> None:
        text = (text or "").strip()
        if not text or self._ws is None or self._ws.closed:
            return
        body = self._base(p.EV_TASK_REQUEST)
        body["req_params"] = {"text": text, "speaker": self.voice, "audio_params": self._audio_params()}
        await self._ws.send_bytes(p.tts_event_frame(p.EV_TASK_REQUEST, body, self.session_id))

    async def finish(self) -> None:
        if self._ws is None or self._ws.closed:
            return
        await self._ws.send_bytes(p.tts_event_frame(p.EV_FINISH_SESSION, {}, self.session_id))

    async def cancel(self) -> None:
        if self._ws is None or self._ws.closed:
            return
        await self._ws.send_bytes(p.tts_event_frame(p.EV_CANCEL_SESSION, {}, self.session_id))

    async def events(self) -> AsyncIterator[dict]:
        """产出 audio / sentence_start / sentence_end / done / canceled / error，会话结束后返回。"""
        while True:
            try:
                msg = await self._recv()
            except RuntimeError as e:
                yield {"type": "error", "message": str(e)}
                return
            except Exception as e:
                yield {"type": "error", "message": f"合成帧解析失败: {e}"}
                return

            if msg.is_error:
                yield {"type": "error", "code": msg.error_code, "message": str(msg.payload)}
                return
            if msg.is_audio:
                if msg.audio:
                    yield {"type": "audio", "data": msg.audio}
                continue
            if msg.event == p.EV_TTS_SENTENCE_START:
                yield {"type": "sentence_start", "text": (msg.payload or {}).get("text", "")}
            elif msg.event == p.EV_TTS_SENTENCE_END:
                yield {"type": "sentence_end"}
            elif msg.event == p.EV_SESSION_FINISHED:
                yield {"type": "done"}
                return
            elif msg.event == p.EV_SESSION_CANCELED:
                yield {"type": "canceled"}
                return
            elif msg.event in (p.EV_SESSION_FAILED, p.EV_CONNECTION_FAILED):
                yield {"type": "error", "message": str(msg.payload)}
                return

    async def close(self) -> None:
        try:
            if self._ws is not None and not self._ws.closed:
                try:
                    await self._ws.send_bytes(p.tts_event_frame(p.EV_FINISH_CONNECTION))
                except Exception:
                    pass
                await self._ws.close()
        finally:
            if self._session is not None and not self._session.closed:
                await self._session.close()
            self._ws = None
            self._session = None

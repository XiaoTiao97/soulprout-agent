"""待命（Standby）语音通道：把手机端的 PCM / 文本代理到豆包流式识别与双向流式合成。

密钥只留在后端；手机端 WebView 无法给 WebSocket 加请求头，所以必须经此代理。

- ``GET /voice/config``：是否已配置、默认参数。
- ``WS  /voice/asr?token=&end_window_ms=``
    上行：二进制 PCM（16k/16bit/单声道），文本 ``{"type":"finish"}``、``{"type":"ping"}``。
    下行：``{"type":"ready"|"partial"|"final"|"error"|"end"|"pong", ...}``。
    ping / pong 是应用层心跳：手机息屏后连接会被网络侧悄悄回收，靠它保活并发现死连接。
- ``WS  /voice/tts?token=&voice=&speech_rate=``
    上行：``{"type":"text","text":"..."}``、``{"type":"finish"}``、``{"type":"cancel"}``、``{"type":"ping"}``。
    下行：二进制 PCM（24k/16bit/单声道）与 ``{"type":"ready"|"sentence_start"|"sentence_end"|"done"|"canceled"|"error"|"pong"}``。
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Awaitable, Optional

from fastapi import APIRouter, Depends, WebSocket
from pydantic import BaseModel

from agent.database.models.user import UserInfo
from agent.services.auth import get_current_user, require_user
from agent.services.voice_turn_judge import judge_user_finished
from agent.services.doubao_speech.asr import ASR_RESOURCE_ID, DoubaoAsr, speech_configured
from agent.services.doubao_speech.tts import DEFAULT_VOICE, TTS_RESOURCE_ID, VOICES, DoubaoTts

logger = logging.getLogger(__name__)
router = APIRouter()

DEFAULT_END_WINDOW_MS = 800


def _token_from_ws(ws: WebSocket) -> Optional[str]:
    token = (ws.query_params.get("token") or "").strip()
    if token:
        return token
    auth = ws.headers.get("authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return (ws.cookies.get("token") or "").strip() or None


async def _accept_and_auth(ws: WebSocket) -> Optional[UserInfo]:
    """接受连接并校验登录；失败时发一条 error 再关闭，返回 None。"""
    await ws.accept()
    token = _token_from_ws(ws)
    if not token:
        await ws.close(code=1008)
        return None
    try:
        user = await get_current_user(token)
    except Exception:
        await ws.close(code=1008)
        return None
    if not speech_configured():
        await _send_json(ws, {"type": "error", "message": "服务端未配置豆包语音（DOUBAO_SPEECH_API_KEY）"})
        await _safe_close(ws)
        return None
    return user


async def _send_json(ws: WebSocket, obj: dict) -> None:
    try:
        await ws.send_text(json.dumps(obj, ensure_ascii=False))
    except Exception:
        pass


async def _safe_close(ws: WebSocket, code: int = 1000) -> None:
    try:
        await ws.close(code=code)
    except Exception:
        pass


async def _run_pair(reader: Awaitable, forwarder: Awaitable) -> None:
    """读取客户端与转发下行并发运行，任一方结束就收尾另一方。"""
    tasks = [asyncio.ensure_future(reader), asyncio.ensure_future(forwarder)]
    try:
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for t in tasks:
            if not t.done():
                t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


@router.get("/voice/config")
async def voice_config(_user: UserInfo = Depends(require_user)):
    return {
        "configured": speech_configured(),
        "voices": VOICES,
        "default_voice": DEFAULT_VOICE,
        "asr_resource_id": ASR_RESOURCE_ID,
        "tts_resource_id": TTS_RESOURCE_ID,
        "end_window_ms": DEFAULT_END_WINDOW_MS,
        "asr_sample_rate": 16000,
        "tts_sample_rate": 24000,
    }


class TurnJudgeRequest(BaseModel):
    # 当前对话窗口内用户说过的全部内容（含已发给 Agent 的部分）
    total_voice_text: str = ""
    # 尚未发给 Agent 的最新内容
    current_voice_text: str = ""


@router.post("/voice/turn-judge")
async def voice_turn_judge(body: TurnJudgeRequest, _user: UserInfo = Depends(require_user)):
    """语义判断用户这轮话是否说完。``user_finished`` 为 null 表示判断失败，调用方应按说完处理。"""
    finished = await judge_user_finished(body.total_voice_text, body.current_voice_text)
    return {"user_finished": finished}


@router.websocket("/voice/asr")
async def voice_asr(ws: WebSocket):
    user = await _accept_and_auth(ws)
    if user is None:
        return

    try:
        end_window_ms = int(ws.query_params.get("end_window_ms") or DEFAULT_END_WINDOW_MS)
    except ValueError:
        end_window_ms = DEFAULT_END_WINDOW_MS

    asr = DoubaoAsr(end_window_ms=end_window_ms, user_id=str(user.user_id))
    try:
        await asr.connect()
    except Exception as e:
        logger.warning("[voice/asr] 连接失败 user=%s: %s", user.user_id, e)
        await _send_json(ws, {"type": "error", "message": str(e)})
        await _safe_close(ws)
        return

    await _send_json(ws, {"type": "ready", "end_window_ms": asr.end_window_ms})

    async def reader():
        while True:
            msg = await ws.receive()
            if msg["type"] == "websocket.disconnect":
                return
            if msg.get("bytes") is not None:
                await asr.send_audio(msg["bytes"])
            elif msg.get("text"):
                try:
                    data = json.loads(msg["text"])
                except json.JSONDecodeError:
                    continue
                kind = data.get("type")
                if kind == "finish":
                    await asr.finish()
                elif kind == "ping":
                    await _send_json(ws, {"type": "pong"})

    async def forwarder():
        async for ev in asr.events():
            await _send_json(ws, ev)
            if ev.get("type") == "error":
                return
        await _send_json(ws, {"type": "end"})

    try:
        await _run_pair(reader(), forwarder())
    except Exception as e:
        logger.warning("[voice/asr] 异常 user=%s: %s", user.user_id, e)
    finally:
        await asr.close()
        await _safe_close(ws)


@router.websocket("/voice/tts")
async def voice_tts(ws: WebSocket):
    user = await _accept_and_auth(ws)
    if user is None:
        return

    voice = (ws.query_params.get("voice") or "").strip() or None
    try:
        speech_rate = int(ws.query_params.get("speech_rate") or 0)
    except ValueError:
        speech_rate = 0

    tts = DoubaoTts(voice=voice, speech_rate=speech_rate, user_id=str(user.user_id))
    try:
        await tts.connect()
    except Exception as e:
        logger.warning("[voice/tts] 连接失败 user=%s: %s", user.user_id, e)
        await _send_json(ws, {"type": "error", "message": str(e)})
        await _safe_close(ws)
        return

    await _send_json(ws, {"type": "ready"})

    async def reader():
        while True:
            msg = await ws.receive()
            if msg["type"] == "websocket.disconnect":
                # 客户端走了：打断合成，避免继续计费
                await tts.cancel()
                return
            text = msg.get("text")
            if not text:
                continue
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                continue
            kind = data.get("type")
            if kind == "text":
                await tts.send_text(data.get("text") or "")
            elif kind == "finish":
                await tts.finish()
            elif kind == "cancel":
                await tts.cancel()
            elif kind == "ping":
                await _send_json(ws, {"type": "pong"})

    async def forwarder():
        async for ev in tts.events():
            if ev["type"] == "audio":
                await ws.send_bytes(ev["data"])
                continue
            await _send_json(ws, ev)

    try:
        await _run_pair(reader(), forwarder())
    except Exception as e:
        logger.warning("[voice/tts] 异常 user=%s: %s", user.user_id, e)
    finally:
        await tts.close()
        await _safe_close(ws)

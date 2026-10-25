from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from agent.database.models.user import UserInfo
from agent.services.asr import transcribe
from agent.services.auth import require_user

router = APIRouter()


@router.post("/asr/transcribe")
async def asr_transcribe(audio: UploadFile = File(...), _user: UserInfo = Depends(require_user)):
    audio_bytes = await audio.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="音频为空")

    fmt = "wav"
    name = (audio.filename or "").lower()
    if name.endswith(".pcm"):
        fmt = "pcm"

    try:
        text = await transcribe(audio_bytes, audio_format=fmt)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"语音识别失败: {e}") from e

    return {"text": text}

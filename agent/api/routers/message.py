from datetime import datetime, timezone
from fastapi import APIRouter, Request, UploadFile, File, Form, Query
from agent.services.auth import get_current_user
from agent.services.agent import Chat
from agent.database.crud.message import get_message_by_conv_id
from agent.api.models.message import ChatRequest, ChatResponse
from fastapi.responses import StreamingResponse
from agent.core.config import Config
import asyncio
import traceback
import json
import os
import aiofiles.os as aio_os
import aiofiles
import time

# 工具（如 web_search）执行期间可能长时间无业务事件；定期发 SSE comment 保活，
# 避免 Cloudflare/Nginx 等因空闲断开 Gateway 到 Agent 的长连接。
_SSE_HEARTBEAT_INTERVAL_S = 15.0

config = Config()
models_info_list = config.models_info_list
router = APIRouter()

@router.get("/message/models")
async def get_models_list():
    models_dict = {}
    for models_info in models_info_list:
        if models_info.get("model_use") == True:
            models_dict[models_info.get("model_source")] = [model.get("name") for model in models_info.get("models")]
    return models_dict

@router.get("/message/{conversation_id}")
async def get_messages(
        conversation_id: str,
        limit: int | None = Query(None, ge=1, le=500),
        before: float | None = Query(None, description="Unix timestamp in milliseconds; return messages before this time"),
):
    before_dt = None
    if before is not None:
        before_dt = datetime.fromtimestamp(before / 1000, tz=timezone.utc).replace(tzinfo=None)
    messages = await get_message_by_conv_id(conversation_id, limit=limit, before=before_dt)
    return messages

@router.post("/message/chat", response_class=StreamingResponse)
async def chat_stream(
        request: Request,
        chat_request: str = Form(...),
        files: list[UploadFile] = File(None),
):
    token = request.cookies.get("token")
    if token:
        user = await get_current_user(token)

    # 解析 chat_request JSON
    chat_req_dict = json.loads(chat_request)
    chat_request = ChatRequest(**chat_req_dict)
    chat_request.user_id = user.user_id
    try:
        from agent.database.crud.user_channel_binding import upsert_channel_binding
        await upsert_channel_binding(
            user.user_id,
            getattr(chat_request, "channel", None) or "",
            getattr(chat_request, "chat_id", None) or "",
        )
    except Exception:
        pass

    # 临时保存文件到临时目录
    temp_file_paths = []
    file_name_list = []
    if files:
        if chat_request.conversation_id == "":
            file_dir = f"/home/soulprout_data/temp_{int(time.time())}"
            chat_request.temp_file_path = file_dir
        else:
            file_dir = f"/home/soulprout_data/{chat_request.conversation_id}"
            chat_request.temp_file_path = None
        await aio_os.makedirs(file_dir, exist_ok=True)

        for file in files:
            temp_file_path = os.path.join(file_dir, file.filename)
            file_name_list.append(file.filename)
            try:
                content = await file.read()
                async with aiofiles.open(temp_file_path, "wb") as buffer:
                    await buffer.write(content)
                temp_file_paths.append(temp_file_path)
                print(f"文件临时保存: {temp_file_path}")
            except Exception as e:
                print(f"文件保存失败 {file.filename}: {e}")
                continue
    chat_request.file_name_list = file_name_list
    ai_service = Chat(chat_request)

    async def generate_stream():
        queue: asyncio.Queue = asyncio.Queue()

        async def _produce():
            try:
                async for chunk in ai_service.run():
                    await queue.put(("chunk", chunk))
            except Exception:
                await queue.put(("error", traceback.format_exc()))
            finally:
                await queue.put(("done", None))

        producer = asyncio.create_task(_produce())
        try:
            while True:
                try:
                    kind, payload = await asyncio.wait_for(
                        queue.get(),
                        timeout=_SSE_HEARTBEAT_INTERVAL_S,
                    )
                except asyncio.TimeoutError:
                    # SSE comment：客户端应忽略；用于穿透代理空闲超时
                    yield ": ping\n\n"
                    if await request.is_disconnected():
                        producer.cancel()
                        break
                    continue

                if kind == "done":
                    break
                if kind == "error":
                    error_resp = ChatResponse(
                        conversation_id=chat_request.conversation_id,
                        user_id=chat_request.user_id,
                        type="error",
                        content=f"回复异常，原因：{payload}",
                    ).model_dump_json()
                    yield f"data: {error_resp}\n\n"
                    break
                if await request.is_disconnected():
                    producer.cancel()
                    break
                yield f"data: {payload}\n\n"
        finally:
            if not producer.done():
                producer.cancel()
                try:
                    await producer
                except (asyncio.CancelledError, Exception):
                    pass
    return StreamingResponse(generate_stream(), media_type="text/event-stream")

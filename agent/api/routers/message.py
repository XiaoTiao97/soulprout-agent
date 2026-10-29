from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Request, UploadFile, File, Form, Query
from agent.services.auth import ensure_conversation_owner, require_user
from agent.database.crud.message import get_message_by_conv_id
from agent.api.models.message import ChatRequest, ChatResponse
from agent.services.run_manager import run_manager
from agent.services import desktop_bridge
from fastapi.responses import StreamingResponse
from agent.core.config import Config
import asyncio
import json
import os
import aiofiles.os as aio_os
import aiofiles
import time

# 工具执行期间可能长时间无业务事件；定期发 SSE comment 保活。
_SSE_HEARTBEAT_INTERVAL_S = 15.0

config = Config()
models_info_list = config.models_info_list
router = APIRouter()


def _sse_data(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


async def _iter_subscriber(request: Request, queue: asyncio.Queue, prelude: list[dict] | None = None):
    for event in prelude or []:
        yield _sse_data(event)
    while True:
        try:
            event = await asyncio.wait_for(queue.get(), timeout=_SSE_HEARTBEAT_INTERVAL_S)
        except asyncio.TimeoutError:
            if await request.is_disconnected():
                break
            yield ": ping\n\n"
            continue
        if await request.is_disconnected():
            break
        yield _sse_data(event)


@router.get("/message/models")
async def get_models_list():
    models_dict = {}
    for models_info in models_info_list:
        if models_info.get("model_use") == True:
            models_dict[models_info.get("model_source")] = [model.get("name") for model in models_info.get("models")]
    return models_dict


@router.get("/message/runs")
async def list_running_conversations(request: Request):
    user = await require_user(request)
    return run_manager.list_running(user.user_id)


@router.get("/message/runs/stream")
async def stream_running_conversations(request: Request):
    user = await require_user(request)
    queue = run_manager.subscribe_status(user.user_id)

    async def generate_stream():
        try:
            async for chunk in _iter_subscriber(request, queue):
                yield chunk
        finally:
            run_manager.detach_status(user.user_id, queue)

    return StreamingResponse(generate_stream(), media_type="text/event-stream")


@router.post("/message/stop")
async def stop_conversation(request: Request):
    user = await require_user(request)
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    conversation_id = ""
    if isinstance(payload, dict):
        conversation_id = str(payload.get("conversation_id") or "").strip()
    if not conversation_id:
        raise HTTPException(status_code=400, detail="缺少 conversation_id")
    stopped = await run_manager.stop(conversation_id, user.user_id)
    return {"success": stopped}


@router.get("/message/{conversation_id}/stream")
async def attach_conversation_stream(request: Request, conversation_id: str):
    user = await require_user(request)
    await ensure_conversation_owner(conversation_id, user.user_id)
    try:
        _run, queue, snapshot = await run_manager.attach(conversation_id, user.user_id)
    except PermissionError:
        raise HTTPException(status_code=403, detail="会话不属于当前用户")

    async def generate_stream():
        try:
            prelude = [snapshot] if snapshot is not None else []
            async for chunk in _iter_subscriber(request, queue, prelude):
                yield chunk
        finally:
            run_manager.detach(conversation_id, queue)

    return StreamingResponse(generate_stream(), media_type="text/event-stream")


@router.get("/message/{conversation_id}")
async def get_messages(
        request: Request,
        conversation_id: str,
        limit: int | None = Query(None, ge=1, le=500),
        before: float | None = Query(None, description="Unix timestamp in milliseconds; return messages before this time"),
):
    user = await require_user(request)
    await ensure_conversation_owner(conversation_id, user.user_id)
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
    user = await require_user(request)

    chat_req_dict = json.loads(chat_request)
    chat_request = ChatRequest(**chat_req_dict)
    chat_request.user_id = user.user_id
    try:
        await desktop_bridge.prepare_request(chat_request, user.user_id)
    except desktop_bridge.LocalWorkspaceError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    try:
        from agent.database.crud.user_channel_binding import upsert_channel_binding
        await upsert_channel_binding(
            user.user_id,
            getattr(chat_request, "channel", None) or "",
            getattr(chat_request, "chat_id", None) or "",
        )
    except Exception:
        pass

    # 先绑定会话 id，新任务会预分配 id，这样本轮运行和订阅用的是同一个 key。
    # 文件仍按绑定前的空 id 走临时目录，由 conversation_init 在建会话时搬走。
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
    # 桌面端的本地会话由本机保存附件，只把文件名随请求带上来，这里不要把它覆盖成空列表
    if file_name_list or not getattr(chat_request, "file_name_list", None):
        chat_request.file_name_list = file_name_list

    try:
        handle = await run_manager.submit(chat_request)
    except PermissionError:
        raise HTTPException(status_code=403, detail="会话不属于当前用户")

    async def generate_stream():
        try:
            async for chunk in _iter_subscriber(request, handle.queue):
                yield chunk
        except Exception:
            error_resp = ChatResponse(
                conversation_id=handle.conversation_id,
                user_id=user.user_id,
                type="error",
                content="回复异常",
            ).model_dump_json()
            yield f"data: {error_resp}\n\n"
        finally:
            run_manager.detach(handle.conversation_id, handle.queue)

    return StreamingResponse(generate_stream(), media_type="text/event-stream")

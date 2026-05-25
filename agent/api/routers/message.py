from fastapi import APIRouter, Request, UploadFile, File, Form
from agent.services.auth import get_current_user
from agent.services.agent import Chat
from agent.database.crud.message import get_message_by_conv_id
from agent.api.models.message import ChatRequest, ChatResponse
from fastapi.responses import StreamingResponse
from agent.core.config import Config
import traceback
import json
import os
import aiofiles.os as aio_os
import aiofiles
import time

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
async def get_messages(conversation_id: str):
     messages = await get_message_by_conv_id(conversation_id)
     messages = [message for message in messages if not isinstance(message.content, list)]
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
        try:
            async for chunk in ai_service.run():
                if await request.is_disconnected():
                    break
                # 确保每个chunk都立即发送
                yield f"data: {chunk}\n\n"
                # 添加小延迟，确保数据被发送
                # await asyncio.sleep(0.05)
        except Exception as e:
            error_resp = ChatResponse(
                conversation_id=chat_request.conversation_id,
                user_id=chat_request.user_id,
                type="error",
                # content=f"回复异常，原因：{e}",
                content=f"回复异常，原因：{traceback.format_exc()}",
            ).model_dump_json()
            yield f"data: {error_resp}\n\n"
    return StreamingResponse(generate_stream(), media_type="text/event-stream")
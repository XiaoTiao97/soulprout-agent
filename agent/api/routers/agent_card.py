import asyncio
import json
import os
import shutil
import urllib.parse
from pathlib import Path
from typing import Generator
from uuid import uuid4

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse

from agent.core.config import Config
from agent.database.crud.agent_card import (
    correct_agent_public_by_agent_id,
    create_agent_card,
    delete_agent_card_by_agent_id,
    get_agent_card_by_agent_id,
    get_agent_cards_by_user,
    get_agent_cards_market,
    update_agent_card_by_agent_id,
)
from agent.database.models.agent_card import AgentCard


config = Config()
router = APIRouter()
AGENT_FILE_PATH = config.agent_file_path


@router.get("/agent_cards/{user_id}")
async def get_agent_card_list(user_id: str):
    try:
        return await get_agent_cards_by_user(user_id)
    except Exception as e:
        return JSONResponse(status_code=200, content={
            "success": False,
            "message": f"获取子智能体列表失败，失败原因: {e}",
            "code": 1004
        })


@router.get("/agent_card/{agent_id}")
async def get_agent_card(agent_id: str):
    try:
        return await get_agent_card_by_agent_id(agent_id)
    except Exception as e:
        return JSONResponse(status_code=200, content={
            "success": False,
            "message": f"获取子智能体失败，失败原因: {e}",
            "code": 1004
        })


@router.post("/agent_card/create")
async def create_agent(request: Request):
    try:
        content_type = request.headers.get("content-type", "")

        if "multipart/form-data" in content_type:
            form = await request.form()
            data_str = form.get("data")
            if not data_str:
                return JSONResponse(status_code=200, content={
                    "success": False,
                    "message": "缺少data字段",
                    "code": 1004
                })
            agent_card = AgentCard(**json.loads(data_str))
            file_list = form.getlist("files")
        else:
            body = await request.json()
            agent_card = AgentCard(**body)
            file_list = []

        if not all((n.isalpha() and n.isascii()) or n == "_" for n in agent_card.name):
            return JSONResponse(status_code=200, content={
                "success": False,
                "message": "新建智能体失败，名称不是由英文和下划线组成",
                "code": 1004
            })

        agent_id = str(uuid4())
        agent_card.agent_id = agent_id
        saved_files = []
        if file_list:
            agent_dir = os.path.join(AGENT_FILE_PATH, agent_id)
            os.makedirs(agent_dir, exist_ok=True)
            for f in file_list:
                if hasattr(f, "filename") and f.filename:
                    file_id = str(uuid4())
                    file_path = os.path.join(agent_dir, f.filename)
                    content = await f.read()
                    with open(file_path, "wb") as out:
                        out.write(content)
                    saved_files.append({"file_id": file_id, "name": f.filename})

            agent_card.files = saved_files

        await create_agent_card(agent_card)
        return JSONResponse(status_code=200, content={
            "success": True,
            "files": saved_files
        })
    except Exception as e:
        return JSONResponse(status_code=200, content={
            "success": False,
            "message": f"新建智能体失败，失败原因：{e}",
            "code": 1004
        })


@router.post("/agent_card/{agent_id}/delete")
async def delete_agent_card(agent_id: str):
    try:
        await delete_agent_card_by_agent_id(agent_id)
        path = os.path.join(AGENT_FILE_PATH, agent_id)
        if Path(path).exists():
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, shutil.rmtree, path)
        return JSONResponse(status_code=200, content={"success": True})
    except Exception as e:
        return JSONResponse(status_code=200, content={
            "success": False,
            "message": f"删除智能体失败，失败原因{e}",
            "code": 1004
        })


@router.post("/agent_card/{agent_id}/update")
async def update_agent_card(agent_id: str, request: Request):
    try:
        content_type = request.headers.get("content-type", "")

        if "multipart/form-data" in content_type:
            form = await request.form()
            data_str = form.get("data")
            if not data_str:
                return JSONResponse(status_code=200, content={
                    "success": False,
                    "message": "缺少data字段",
                    "code": 1004
                })
            body = json.loads(data_str)
            files_to_delete = body.pop("files_to_delete", None) or []
            agent_card = AgentCard(**body)
            file_list = form.getlist("files")
        else:
            body = await request.json()
            files_to_delete = body.pop("files_to_delete", None) or []
            agent_card = AgentCard(**body)
            file_list = []

        agent_dir = os.path.join(AGENT_FILE_PATH, agent_id)
        current_agent = await get_agent_card_by_agent_id(agent_id)
        current_files = list(getattr(current_agent, "files", None) or [])

        for f in current_files:
            if f.get("file_id") in files_to_delete:
                old_path = os.path.join(agent_dir, f.get("name", ""))
                if os.path.exists(old_path):
                    os.remove(old_path)

        saved_files = [
            f for f in current_files
            if f.get("file_id") not in files_to_delete
        ]

        if file_list:
            os.makedirs(agent_dir, exist_ok=True)
            for f in file_list:
                if hasattr(f, "filename") and f.filename:
                    file_id = str(uuid4())
                    file_path = os.path.join(agent_dir, f.filename)
                    content = await f.read()
                    with open(file_path, "wb") as out:
                        out.write(content)
                    saved_files.append({"file_id": file_id, "name": f.filename})

        agent_card.files = saved_files
        await update_agent_card_by_agent_id(agent_id, agent_card)
        return JSONResponse(status_code=200, content={
            "success": True,
            "files": saved_files
        })
    except Exception as e:
        return JSONResponse(status_code=200, content={
            "success": False,
            "message": f"更新智能体失败，失败原因：{e}",
            "code": 1004
        })


@router.get("/file_content/{filename}")
async def get_file_content(filename: str, agent_id: str = Query(...)):
    try:
        file_path = os.path.join(AGENT_FILE_PATH, agent_id, filename)
        if not os.path.exists(file_path):
            return {"error": "File not found"}, 404

        def file_iterator(chunk_size: int = 1024 * 1024) -> Generator[bytes, None, None]:
            with open(file_path, "rb") as f:
                while True:
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break
                    yield chunk

        file_extension = os.path.splitext(filename)[1].lower()
        content_type = {
            ".html": "text/html",
            ".pdf": "application/pdf",
            ".doc": "application/msword",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".ppt": "application/vnd.ms-powerpoint",
            ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            ".xls": "application/vnd.ms-excel",
            ".xlsx": "application/vnd.ms-excel",
            ".jpg": "image/jpeg",
            ".png": "image/png",
        }.get(file_extension, "application/octet-stream")

        return StreamingResponse(
            file_iterator(),
            media_type=content_type,
            headers={
                "Content-Disposition": f"inline; filename*=UTF-8''{urllib.parse.quote(filename)}"
            }
        )
    except Exception as e:
        return {"error": str(e)}, 500


@router.post("/agent_card/{agent_id}/public")
async def update_agent_public(agent_id: str, public: bool):
    await correct_agent_public_by_agent_id(agent_id, public)
    return {"success": True, "content": "上传成功"}


@router.get("/agent_cards_market")
async def get_agent_cards_market_list():
    try:
        return await get_agent_cards_market()
    except Exception as e:
        return JSONResponse(status_code=200, content={
            "success": False,
            "message": f"获取智能体市场，失败原因: {e}",
            "code": 1004
        })


@router.get("/agent_default_tools")
async def get_agent_default_tools():
    try:
        return {"tool_names": config.agent_default_tools}
    except Exception as e:
        return JSONResponse(status_code=200, content={
            "success": False,
            "message": f"获取创建专家默认工具失败: {e}",
            "code": 1004,
        })

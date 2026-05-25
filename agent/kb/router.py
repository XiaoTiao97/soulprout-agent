import asyncio
import os
import shutil
import urllib.parse
from io import BytesIO
from pathlib import Path
from typing import Dict, Generator, List
from urllib.parse import quote

import aiofiles
import aiofiles.os as aio_os
import shortuuid
from fastapi import APIRouter, Body, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

from agent.core.config import Config
from agent.kb.models.kb import FileInfo
from agent.kb.services.kb_manager import KBManager

router = APIRouter(prefix="/kb", tags=["knowledge-base"])
config = Config()
kb_manager = KBManager(config)
FILES_BASE_DIR = config.kb_file_path


@router.post("/create/", response_class=StreamingResponse)
async def create_knowledge_base(
    user_id: str = Form(...),
    files: List[UploadFile] = File(...),
):
    kb_id = shortuuid.ShortUUID().random(length=12)
    kb_dir = os.path.join(FILES_BASE_DIR, kb_id)
    try:
        await aio_os.makedirs(kb_dir, exist_ok=True)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建知识库目录失败: {str(e)}")

    processed_files = []
    saved_files = []

    try:
        for f in files:
            file_extension = Path(f.filename).suffix.lower()
            file_path = os.path.join(kb_dir, f.filename)

            if await aio_os.path.exists(file_path):
                raise HTTPException(status_code=400, detail=f"文件 {f.filename} 已存在")

            try:
                content = await f.read()
                async with aiofiles.open(file_path, "wb") as buffer:
                    await buffer.write(content)
                saved_files.append({"path": file_path, "filename": f.filename})
            except Exception as e:
                for saved_file in saved_files:
                    try:
                        await aio_os.remove(saved_file["path"])
                    except OSError:
                        pass
                raise HTTPException(status_code=500, detail=f"文件 {f.filename} 保存失败: {str(e)}")

            processed_files.append(
                FileInfo(
                    file_name=f.filename,
                    file_extension=file_extension,
                    file_bytes=BytesIO(content),
                )
            )

        async def generate_stream():
            try:
                async for chunk in kb_manager.create_knowledge_base(
                    kb_id=kb_id, user_id=user_id, files=processed_files
                ):
                    yield chunk + "\n"
                    await asyncio.sleep(0.1)
            except Exception as e:
                for saved_file in saved_files:
                    try:
                        await aio_os.remove(saved_file["path"])
                    except OSError:
                        pass
                try:
                    await aio_os.rmdir(kb_dir)
                except OSError:
                    pass
                yield f"知识库创建失败: {str(e)}\n"
                raise

        return StreamingResponse(generate_stream(), media_type="text/plain")
    except HTTPException:
        raise
    except Exception as e:
        for saved_file in saved_files:
            try:
                await aio_os.remove(saved_file["path"])
            except OSError:
                pass
        try:
            await aio_os.rmdir(kb_dir)
        except OSError:
            pass
        raise HTTPException(status_code=500, detail=f"创建知识库失败: {str(e)}")


@router.post("/add-file/", response_class=StreamingResponse)
async def add_file_to_knowledge_base(
    kb_id: str = Form(...),
    files: List[UploadFile] = File(...),
):
    kb_dir = os.path.join(FILES_BASE_DIR, kb_id)
    if not await aio_os.path.exists(kb_dir):
        raise HTTPException(status_code=404, detail=f"知识库 {kb_id} 不存在")

    processed_files = []
    saved_files = []

    try:
        for f in files:
            file_extension = Path(f.filename).suffix.lower()
            file_path = os.path.join(kb_dir, f.filename)

            if await aio_os.path.exists(file_path):
                raise HTTPException(status_code=400, detail=f"文件 {f.filename} 已存在")

            try:
                content = await f.read()
                async with aiofiles.open(file_path, "wb") as buffer:
                    await buffer.write(content)
                saved_files.append({"path": file_path, "filename": f.filename})
            except Exception as e:
                for saved_file in saved_files:
                    try:
                        await aio_os.remove(saved_file["path"])
                    except OSError:
                        pass
                raise HTTPException(status_code=500, detail=f"文件 {f.filename} 保存失败: {str(e)}")

            processed_files.append(
                FileInfo(
                    file_name=f.filename,
                    file_extension=file_extension,
                    file_bytes=BytesIO(content),
                )
            )

        async def generate_stream():
            try:
                async for chunk in kb_manager.add_file_to_kb(kb_id=kb_id, files=processed_files):
                    yield chunk + "\n"
                    await asyncio.sleep(0.1)
            except Exception as e:
                for saved_file in saved_files:
                    try:
                        await aio_os.remove(saved_file["path"])
                    except OSError:
                        pass
                yield f"添加文件失败: {str(e)}\n"
                raise

        return StreamingResponse(generate_stream(), media_type="text/plain")
    except HTTPException:
        raise
    except Exception as e:
        for saved_file in saved_files:
            try:
                await aio_os.remove(saved_file["path"])
            except OSError:
                pass
        raise HTTPException(status_code=500, detail=f"添加文件失败: {str(e)}")


@router.delete("/delete/{kb_id}")
async def delete_knowledge_base(kb_id: str):
    try:
        result = await kb_manager.delete_knowledge_base(kb_id)
        kb_dir = os.path.join(FILES_BASE_DIR, kb_id)
        if await aio_os.path.exists(kb_dir):
            def sync_delete():
                shutil.rmtree(kb_dir, ignore_errors=True)

            await asyncio.get_event_loop().run_in_executor(None, sync_delete)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/delete-doc/{doc_id}")
async def delete_document(doc_id: str):
    try:
        return await kb_manager.delete_document(doc_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/list/")
async def get_user_knowledge_bases(user_id: str = Query(...)):
    try:
        libraries = await kb_manager.get_user_knowledge_bases(user_id)
        return {"success": True, "data": libraries, "total": len(libraries)}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/docs/")
async def get_knowledge_base_documents(kb_id: str = Query(...)):
    try:
        documents = await kb_manager.get_knowledge_base_documents(kb_id)
        return {"success": True, "data": documents, "total": len(documents)}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/detail/{kb_id}")
async def get_knowledge_base_detail(kb_id: str):
    try:
        libraries = await kb_manager.get_user_knowledge_bases("")
        kb_info = next((lib for lib in libraries if lib["kb_id"] == kb_id), None)
        if not kb_info:
            raise HTTPException(status_code=404, detail="知识库不存在")
        documents = await kb_manager.get_knowledge_base_documents(kb_id)
        return {
            "success": True,
            "kb_info": kb_info,
            "documents": documents,
            "doc_count": len(documents),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/update/kb_info/")
async def update_knowledge_base(
    kb_id: str = Form(...),
    kb_name_zh: str = Form(...),
    kb_description: str = Form(...),
):
    try:
        await kb_manager.update_kb_info(kb_id, kb_name_zh, kb_description)
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/search/")
async def search_knowledge_bases(search_data: Dict = Body(...)):
    try:
        user_id = search_data.get("user_id")
        keyword = search_data.get("keyword", "")
        if not user_id:
            raise HTTPException(status_code=400, detail="用户ID不能为空")

        libraries = await kb_manager.get_user_knowledge_bases(user_id)
        if keyword:
            libraries = [
                lib
                for lib in libraries
                if keyword.lower() in lib["kb_name"].lower()
                or keyword.lower() in lib["kb_description"].lower()
            ]
        return {
            "success": True,
            "data": libraries,
            "total": len(libraries),
            "keyword": keyword,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/download/{filename}")
async def download_file(filename: str, kb_id: str = Query(...)):
    try:
        dir_path = os.path.join(FILES_BASE_DIR, kb_id)
        file_path = os.path.join(dir_path, filename)
        if not os.path.exists(file_path) or not os.path.isfile(file_path):
            raise HTTPException(status_code=404, detail="File not found")

        encoded_filename = quote(filename)
        headers = {"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"}
        return FileResponse(
            file_path,
            media_type="application/octet-stream",
            headers=headers,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/file_content/{filename}")
async def get_file_content(filename: str, kb_id: str = Query(...)):
    try:
        dir_path = os.path.join(FILES_BASE_DIR, kb_id)
        file_path = os.path.join(dir_path, filename)
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
            ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ".jpg": "image/jpeg",
            ".png": "image/png",
        }.get(file_extension, "application/octet-stream")

        return StreamingResponse(
            file_iterator(),
            media_type=content_type,
            headers={"Content-Disposition": f"inline; filename*=UTF-8''{urllib.parse.quote(filename)}"},
        )
    except Exception as e:
        return {"error": str(e)}, 500

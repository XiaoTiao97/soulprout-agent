from fastapi import APIRouter, HTTPException, Query, Form, File, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from agent.core.config import Config
import os
from urllib.parse import quote
from weasyprint import HTML, CSS
import asyncio
import base64
import re
from pathlib import Path
import httpx
import shutil
from typing import Dict, List, Optional, Set
from collections import defaultdict
from agent.tool.registry import get_all_tool_schemas
from agent.skill.skill_server import SkillServer

router = APIRouter()
skill_server = SkillServer()

@router.get("/tools_info")
async def mcp_list_tools():
    result = []
    for tool in get_all_tool_schemas():
        func = tool.get("function", {})
        result.append(
            {
                "type": "local",
                "class_zh": "系统工具",
                "name": func.get("name"),
                "description": func.get("description"),
                "inputSchema": func.get("parameters"),
            }
        )
    return result

_USER_ID_SAFE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
USER_SKILLS_BASE = os.getenv("USER_SKILLS_BASE", "/home/user_skills")

def _validate_folder_name(folder: str) -> None:
    """允许中文等目录名，禁止路径穿越与分隔符。"""
    if not folder or len(folder) > 256:
        raise HTTPException(status_code=400, detail="非法 folder")
    if ".." in folder or "/" in folder or "\\" in folder:
        raise HTTPException(status_code=400, detail="非法 folder")

def _safe_join_under_base(base: str, *parts: str) -> Path:
    """防止路径穿越，仅允许落在 base 下。"""
    root = Path(base).resolve()
    candidate = (root / Path(*parts)).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="非法路径") from exc
    return candidate

SKILL_MD_FILENAME = "SKILL.md"

def _validate_skill_upload_structure(files: List[UploadFile]) -> None:
    """
    每个顶层技能根目录下必须存在 SKILL.md（与前端 webkitRelativePath 一致）。
    例如：MySkill/SKILL.md、MySkill/scripts/a.py
    """
    paths_by_root: Dict[str, Set[str]] = defaultdict(set)
    for upload in files:
        raw_name = upload.filename or ""
        rel = raw_name.replace("\\", "/").strip("/")
        if not rel or ".." in rel.split("/"):
            continue
        parts = rel.split("/")
        root = parts[0]
        paths_by_root[root].add(rel)

    if not paths_by_root:
        raise HTTPException(
            status_code=400,
            detail="不是标准的skill文件：未检测到有效文件路径",
        )

    for root, paths in paths_by_root.items():
        required = f"{root}/{SKILL_MD_FILENAME}"
        if required not in paths:
            raise HTTPException(
                status_code=400,
                detail=f"不是标准的skill文件：「{root}」根目录下必须包含 {SKILL_MD_FILENAME}",
            )

@router.get("/skills_info")
async def skills_info(user_id: Optional[str] = None):
    try:
        data = skill_server.get_merged_skills(user_id=user_id)
        return data if isinstance(data, list) else []
    except Exception:
        return []

@router.post("/user_skills/upload")
async def upload_user_skills(
    user_id: str = Form(...),
    files: List[UploadFile] = File(...),
):
    if not user_id or not _USER_ID_SAFE.match(user_id):
        raise HTTPException(status_code=400, detail="非法 user_id")

    _validate_skill_upload_structure(files)

    user_root = _safe_join_under_base(USER_SKILLS_BASE, user_id, "skills")
    user_root.mkdir(parents=True, exist_ok=True)

    saved = 0
    for upload in files:
        raw_name = upload.filename or ""
        rel = raw_name.replace("\\", "/").strip("/")
        if not rel or ".." in rel.split("/"):
            continue
        dest = _safe_join_under_base(str(user_root), *rel.split("/"))
        dest.parent.mkdir(parents=True, exist_ok=True)
        body = await upload.read()
        dest.write_bytes(body)
        saved += 1

    if saved == 0:
        raise HTTPException(status_code=400, detail="未写入任何文件")

    return {"success": True, "saved": saved}

@router.delete("/user_skills")
async def delete_user_skill(user_id: str, folder: str):
    """
    在本机删除用户技能目录。删后下次 GET /skills_info
    会从本地技能索引中自动消失。
    路径：{USER_SKILLS_BASE}/{user_id}/skills/{folder}/（与 upload 一致）。
    """
    if not user_id or not _USER_ID_SAFE.match(user_id):
        raise HTTPException(status_code=400, detail="非法 user_id")
    _validate_folder_name(folder)

    target = _safe_join_under_base(USER_SKILLS_BASE, user_id, "skills", folder)
    if not target.is_dir():
        raise HTTPException(status_code=404, detail="技能不存在或已删除")

    shutil.rmtree(target)
    return {"success": True}

# 固定基础文件夹路径（替换为您的实际路径）
config = Config()
FILES_BASE_DIR = config.local_file_path
def get_conversation_dir(conversation_id: str) -> Path:
    if not re.fullmatch(r"[0-9a-fA-F-]{36}", conversation_id):
        raise HTTPException(status_code=400, detail="invalid conversation_id")
    base_dir = Path(FILES_BASE_DIR).resolve()
    conv_dir = (base_dir / conversation_id).resolve()
    if base_dir not in conv_dir.parents and conv_dir != base_dir:
        raise HTTPException(status_code=400, detail="invalid path")
    return conv_dir
def resolve_target_file(conversation_id: str, filename: str) -> Path:
    conv_dir = get_conversation_dir(conversation_id)
    target = (conv_dir / filename).resolve()
    # 防路径穿越
    if conv_dir not in target.parents and target != conv_dir:
        raise HTTPException(status_code=400, detail="invalid filename path")
    return target
# 获取文件列表接口（添加conversation_id查询参数）
@router.get("/files")
async def get_files(conversation_id: str = Query(...)):
    # 1) 基础参数校验（按你的会话ID规则可再调整）
    if not re.fullmatch(r"[0-9a-fA-F-]{36}", conversation_id):
        raise HTTPException(status_code=400, detail="invalid conversation_id")
    base_dir = Path(FILES_BASE_DIR).resolve()
    conv_dir = (base_dir / conversation_id).resolve()
    # 2) 防路径穿越
    if base_dir not in conv_dir.parents and conv_dir != base_dir:
        raise HTTPException(status_code=400, detail="invalid path")
    # 3) 目录不存在直接空列表
    if not conv_dir.exists():
        return {"files": []}
    # 4) 根目录不可读
    if not os.access(conv_dir, os.R_OK | os.X_OK):
        raise HTTPException(status_code=403, detail="conversation directory not accessible")
    result = []
    def on_walk_error(err: OSError):
        # 遇到某个无权限子目录，跳过继续，不要整接口失败
        print(f"os.walk warning: {err}")
    for root, dirs, files in os.walk(conv_dir, topdown=True, onerror=on_walk_error):
        # 过滤不可进入的子目录，避免 PermissionError
        dirs[:] = [d for d in dirs if os.access(Path(root) / d, os.R_OK | os.X_OK)]
        for name in files:
            file_path = Path(root) / name
            rel = file_path.relative_to(conv_dir).as_posix()  # 统一用 /
            result.append(rel)
    result.sort()
    return {"files": result}

# 下载文件接口（添加conversation_id查询参数）
@router.get("/download/{filename:path}")
async def download_file(filename: str, conversation_id: str = Query(...)):
    try:
        file_path = resolve_target_file(conversation_id, filename)
        if not file_path.exists() or not file_path.is_file():
            raise HTTPException(status_code=404, detail="File not found")

        encoded_filename = quote(file_path.name)  # 响应头建议只放文件名
        headers = {"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"}
        return FileResponse(str(file_path), media_type="application/octet-stream", headers=headers)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/file_content/{filename:path}")
async def get_file_content(filename: str, conversation_id: str = Query(...)):
    try:
        file_path = resolve_target_file(conversation_id, filename)
        if not file_path.exists() or not file_path.is_file():
            raise HTTPException(status_code=404, detail="File not found")

        def file_iterator(chunk_size: int = 1024 * 1024):
            with open(file_path, "rb") as f:
                while chunk := f.read(chunk_size):
                    yield chunk

        ext = file_path.suffix.lower()
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
            ".txt": "text/plain; charset=utf-8",
            ".md": "text/markdown; charset=utf-8",
            ".json": "application/json; charset=utf-8",
        }.get(ext, "application/octet-stream")

        return StreamingResponse(
            file_iterator(),
            media_type=content_type,
            headers={"Content-Disposition": f"inline; filename*=UTF-8''{quote(file_path.name)}"}
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 占位转换函数（替换为你的实际实现）
async def convert_html_to_pdf(conversation_id: str, filename: str) -> str:
    src_html = resolve_target_file(conversation_id, filename)
    if not src_html.exists() or not src_html.is_file():
        raise HTTPException(status_code=404, detail="Source HTML not found")
    if src_html.suffix.lower() != ".html":
        raise HTTPException(status_code=400, detail="Only HTML files can be converted")
    pdf_path = src_html.with_suffix(".pdf")
    css_content = """
    @page {
        size: A4 landscape;
        margin: 10mm;
    }
    * {
        font-family: Arial, "DejaVu Sans", "WenQuanYi Micro Hei", "Microsoft YaHei", sans-serif !important;
    }
    body {
        font-family: "Microsoft YaHei", "Noto Sans CJK SC", "WenQuanYi Zen Hei", "SimHei", "Source Han Sans CN", sans-serif !important;
        margin: 0 !important;
        padding: 0 !important;
    }
    .slide {
        page-break-before: always;
        page-break-inside: auto;
    }
    .slide:first-child { page-break-before: auto; }
    """
    css = CSS(string=css_content)
    loop = asyncio.get_running_loop()
    html = HTML(filename=str(src_html))
    await loop.run_in_executor(
        None,
        lambda: html.write_pdf(str(pdf_path), stylesheets=[css])
    )
    if not pdf_path.exists():
        raise HTTPException(status_code=500, detail="PDF conversion failed")
    return str(pdf_path)
async def convert_html_to_pptx(conversation_id: str, filename: str) -> str:
    # 先生成 PDF
    pdf_path_str = await convert_html_to_pdf(conversation_id, filename)
    pdf_path = Path(pdf_path_str)
    # 目标 PPTX 路径
    pptx_path = pdf_path.with_suffix(".pptx")
    app_id = os.getenv("TEXTIN_APP_ID")
    secret_code = os.getenv("TEXTIN_SECRET_CODE")
    if not app_id or not secret_code:
        raise HTTPException(status_code=500, detail="Missing TEXTIN credentials")
    url = "https://api.textin.com/ai/service/v1/file-convert/pdf-to-ppt"
    headers = {
        "x-ti-app-id": app_id,
        "x-ti-secret-code": secret_code,
        "Content-Type": "application/octet-stream",
    }
    try:
        pdf_data = pdf_path.read_bytes()
        timeout = httpx.Timeout(120.0, connect=10.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, content=pdf_data, headers=headers)
        resp.raise_for_status()
        result_json = resp.json()
        if result_json.get("code") != 200:
            raise HTTPException(
                status_code=502,
                detail=f"API转换失败: {result_json.get('message', '未知错误')}"
            )
        pptx_base64 = result_json.get("result")
        if not pptx_base64:
            raise HTTPException(status_code=502, detail="API返回的result字段为空")
        pptx_data = base64.b64decode(pptx_base64)
        pptx_path.write_bytes(pptx_data)
        if not pptx_path.exists():
            raise HTTPException(status_code=500, detail="PPTX写入失败")
        return str(pptx_path)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"转换过程中出现错误: {e}")


@router.get("/export/{filename:path}")
async def export_file(filename: str, conversation_id: str = Query(...), format: str = Query(...)):
    try:
        file_path = resolve_target_file(conversation_id, filename)
        if not file_path.exists() or not file_path.is_file():
            raise HTTPException(status_code=404, detail="File not found")
        if file_path.suffix.lower() != ".html":
            raise HTTPException(status_code=400, detail="Only HTML files can be exported")
        if format not in {"pdf", "pptx"}:
            raise HTTPException(status_code=400, detail="Unsupported format. Use 'pdf' or 'pptx'")

        # 这里 convert 函数要能接收“相对路径 filename”
        output_path = await (
            convert_html_to_pdf(conversation_id, filename)
            if format == "pdf"
            else convert_html_to_pptx(conversation_id, filename)
        )

        output_file = Path(output_path).resolve()
        if not output_file.exists() or not output_file.is_file():
            raise HTTPException(status_code=500, detail="File conversion failed")

        encoded_filename = quote(f"{file_path.stem}.{format}")
        headers = {"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"}
        return FileResponse(str(output_file), media_type="application/octet-stream", headers=headers)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/save_file/{filename:path}")
async def save_file(
    filename: str,
    file_content: str = Form(...),
    conversation_id: str = Form(...)
):
    try:
        file_path = resolve_target_file(conversation_id, filename)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(file_content, encoding="utf-8")
        return {"message": "保存成功", "filename": filename}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error")
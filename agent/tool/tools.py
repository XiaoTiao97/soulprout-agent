import asyncio
import base64
import inspect
import json
import os
import aiofiles
import html2text
import httpx
import requests
from datetime import datetime
from zai import ZhipuAiClient

from agent.database.models.user import UserInfo
from agent.tool.file_process import AsyncFileProcess
from agent.tool.registry import get_all_tool_schemas, get_registered_tool_names
from agent.utils.vdb_client import VDBClient


KB_COLLECTION = os.getenv("VDB_KB_COLLECTION", "kb_collection")
MEMORY_COLLECTION = os.getenv("VDB_MEMORY_COLLECTION", "memory_collection")
SKILL_COLLECTION = os.getenv("VDB_SKILL_COLLECTION", "skill_collection")
SKILLS_PREVIEW_CLOSED_TEXT = "Skills Preview Closed"


class SoulproutToolFunction:
    def __init__(self, config):
        self.config = config
        self.file_process = AsyncFileProcess()
        self.vdb_client = VDBClient()
        host = os.getenv("DOCKER_SERVER_HOST", "localhost")
        self.agent_base_url = f"http://{host}:8080"
        self.main_base_url = f"http://{host}:8080"

    def _workspace_dir(self, conversation_id):
        return os.path.join(self.config.local_file_path, conversation_id)

    async def _get_user_id_by_conversation_id(self, conversation_id):
        row = await self.config.db_conversation.find_one({"conversation_id": conversation_id})
        return row.get("user_id") if row else None

    async def get_action_blueprint(self, conversation_id=None):
        """Handled in Chat.process_single_tool; should not be invoked via ToolExecutor."""
        return (
            "get_action_blueprint is executed by the agent runtime. "
            "If you see this message, the call was routed incorrectly."
        )

    # NOTE: read 的分页读取（offset/limit）参考自 hermes 项目（claude-engineer / hermes）
    # 的 read 工具实现：纯文本/源代码文件按行切片返回，二进制/富文本文件（pdf/doc(x)/
    # ppt(x)/xlsx）走整体解析，offset/limit 不生效。
    async def read(self, file_path, conversation_id, offset=1, limit=500):
        try:
            try:
                offset = int(offset) if offset is not None else 1
            except (TypeError, ValueError):
                offset = 1
            try:
                limit = int(limit) if limit is not None else 500
            except (TypeError, ValueError):
                limit = 500
            offset = max(1, offset)
            limit = max(1, min(limit, 2000))

            target = os.path.join(self._workspace_dir(conversation_id), file_path).replace("\\", "/")
            if file_path.endswith((".pdf", ".docx", ".doc", ".pptx", ".xlsx")):
                return str(await self.file_process.file_parse(file_path, target))

            async with aiofiles.open(target, "r", encoding="utf-8") as f:
                lines = await f.readlines()
            total = len(lines)
            if offset > total:
                return f"<file is empty or offset({offset}) > total lines({total})>"
            start = offset - 1
            end = min(start + limit, total)
            selected = lines[start:end]
            numbered = [f"{start + idx + 1:6}\u2502{line.rstrip(chr(10))}" for idx, line in enumerate(selected)]
            header = f"# {file_path} (lines {start + 1}-{end} of {total})\n"
            footer = "" if end >= total else f"\n<... {total - end} more lines, call read again with offset={end + 1} to continue ...>"
            return header + "\n".join(numbered) + footer
        except Exception as e:
            return f"错误：阅读{file_path}失败，失败原因：{e}"

    async def write(self, file_path, content, conversation_id):
        try:
            root = self._workspace_dir(conversation_id)
            target = os.path.join(root, file_path)
            os.makedirs(os.path.dirname(target) or root, exist_ok=True)
            async with aiofiles.open(target, "a", encoding="utf-8") as f:
                await f.write(content)
            return f"成功写入{file_path}"
        except Exception as e:
            return f"错误：写入{file_path}失败，失败原因：{e}"

    async def edit(self, file_path, past_text, replace_text, conversation_id):
        try:
            target = os.path.join(self._workspace_dir(conversation_id), file_path)
            async with aiofiles.open(target, "r", encoding="utf-8") as f:
                src = await f.read()
            dst = src.replace(past_text, replace_text)
            if dst == src:
                return "文本替换失败，请检查past_text是否对应原文内容"
            async with aiofiles.open(target, "w", encoding="utf-8") as f:
                await f.write(dst)
            return f"成功修改{file_path}"
        except Exception as e:
            return f"错误：修改{file_path}失败，失败原因：{e}"

    async def read_picture(self, file_name, conversation_id):
        target = os.path.join(self._workspace_dir(conversation_id), file_name)
        if not os.path.exists(target):
            return {"ok": False, "message": "路径不存在", "base64": None}
        try:
            async with aiofiles.open(target, "rb") as image_file:
                encoded = base64.b64encode(await image_file.read()).decode("utf-8")
            return {"ok": True, "message": "成功读取图片", "base64": encoded}
        except Exception as e:
            return {"ok": False, "message": f"读取图片失败: {e}", "base64": None}

    async def bash(self, command, conversation_id):
        root = self._workspace_dir(conversation_id)
        os.makedirs(root, exist_ok=True)
        proc = await asyncio.create_subprocess_shell(command, cwd=root, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), 3600)
            return f"Standard Output:\n{stdout.decode('utf-8', errors='replace')}\nStandard Error:\n{stderr.decode('utf-8', errors='replace')}"
        except asyncio.TimeoutError:
            proc.kill()
            return "错误: 命令执行超时"

    async def create_agent(self, name, description, system_prompt, model, model_source, name_zh=None, tools=None, skills=None, kbs=None, agents=None, supervisor_history=True, file_names=None, conversation_id=None):
        try:
            user_id = await self._get_user_id_by_conversation_id(conversation_id)
            if not user_id:
                return "创建失败，无法获取用户信息"
            payload = {
                "user_id": user_id,
                "user_name": "",
                "agent_id": "",
                "name": name,
                "name_zh": name_zh or None,
                "description": description,
                "system_prompt": system_prompt,
                "tools": tools or [],
                "skills": skills or None,
                "agents": agents,
                "kbs": kbs or [],
                "supervisor_history": supervisor_history,
                "model_source": model_source,
                "model": model,
                "announcement": "",
            }
            async with httpx.AsyncClient() as client:
                resp = await client.post(f"{self.agent_base_url}/agent_card/create", json=payload, timeout=30.0)
            data = resp.json()
            return "创建智能体成功" if data.get("success") else f"创建失败: {data}"
        except Exception as e:
            return f"错误：创建智能体失败，失败原因：{e}"

    async def list_info(self, category, conversation_id):
        """统一信息列表查询：models / tools / agent_cards。"""
        if category == "models":
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.get(f"{self.main_base_url}/message/models", timeout=10.0)
                return json.dumps(resp.json(), ensure_ascii=False, indent=2)
            except Exception as e:
                return f"错误：获取模型列表失败，失败原因：{e}"
        if category == "tools":
            rows = []
            for item in get_all_tool_schemas():
                fn = item.get("function", {})
                rows.append({"name": fn.get("name"), "description": fn.get("description"), "inputSchema": fn.get("parameters")})
            return json.dumps(rows, ensure_ascii=False, indent=2)
        if category == "agent_cards":
            try:
                user_id = await self._get_user_id_by_conversation_id(conversation_id)
                if not user_id:
                    return "错误：无法获取user_id"
                async with httpx.AsyncClient() as client:
                    resp = await client.get(f"{self.agent_base_url}/agent_cards/{user_id}", timeout=10.0)
                return json.dumps(resp.json(), ensure_ascii=False, indent=2)
            except Exception as e:
                return f"错误：获取子智能体列表失败，失败原因：{e}"
        return f"错误：未知的 category={category}，仅支持 models / tools / agent_cards"

    async def skills(self, module, conversation_id, query=None, source=None, skill_name=None):
        """统一 skills 工具：module=preview/load/close_preview。"""
        if module == "preview":
            if not query or not str(query).strip():
                return "错误：module=preview 时 query 必填且不能为空，请传入用于检索 skill 的关键词"
            return await self._skills_preview(query, conversation_id)
        if module == "load":
            if not source or not skill_name:
                return "错误：module=load 时必须填写 source 与 skill_name"
            return await self._skills_load(source, skill_name, conversation_id)
        if module == "close_preview":
            return await self._skills_close_preview(conversation_id)
        return f"错误：未知的 module={module}，仅支持 preview / load / close_preview"

    async def _skills_preview(self, query, conversation_id):
        """
        返回两类 skill：
            1. 系统 skill 库：通过 description 的 hybrid_search 召回 Top20 且 _score>=0.4
            2. 个人 skill 库：按当前 user_id 直接列出全部
        每条返回 name 与 description 两个字段。
        """
        from agent.skill.skill_server import load_skills_from_subfolders, get_user_skills_root

        # 系统 skill：向量召回
        system_skills: list[dict] = []
        try:
            await self.vdb_client.ensure_collection(SKILL_COLLECTION, "skill")
            results = await self.vdb_client.hybrid_search(
                SKILL_COLLECTION,
                query=query or "",
                limit=20,
                output_fields=["name", "description"],
            )
            for item in results:
                score = item.get("_score")
                if score is None or score < self.config.hybrid_search_score_threshold:
                    continue
                name = item.get("name")
                if not name:
                    continue
                system_skills.append({
                    "name": name,
                    "description": item.get("description") or "",
                })
        except Exception as e:
            system_skills = []
            system_error = f"系统 skill 召回失败：{e}"
        else:
            system_error = None

        # 个人 skill：按 user_id 全量列出
        user_skills: list[dict] = []
        try:
            user_id = await self._get_user_id_by_conversation_id(conversation_id)
            if user_id:
                raw_user_skills = load_skills_from_subfolders(get_user_skills_root(user_id), "user")
                for item in raw_user_skills:
                    name = (item.get("name") or "").strip()
                    if not name:
                        continue
                    user_skills.append({
                        "name": name,
                        "description": item.get("description") or "",
                    })
        except Exception as e:
            user_error = f"个人 skill 列表获取失败：{e}"
        else:
            user_error = None

        payload = {
            "system_skills": system_skills,
            "user_skills": user_skills,
        }
        if system_error:
            payload["system_skills_error"] = system_error
        if user_error:
            payload["user_skills_error"] = user_error
        return json.dumps(payload, ensure_ascii=False, indent=2)

    async def _skills_load(self, source, skill_name, conversation_id):
        from agent.skill.manager import load_skill_to_workspace

        user_id = await self._get_user_id_by_conversation_id(conversation_id)
        skills = {"system": [skill_name]} if source == "system" else {"user": [skill_name]}
        result = await load_skill_to_workspace(conversation_id=conversation_id, user_id=user_id, skills=skills, workspace_base=self.config.local_file_path)
        return result.get("data") if result.get("success") else result.get("error", "加载失败")

    async def _skills_close_preview(self, conversation_id):
        """
        关闭技能预览：将本会话历史中所有 skills(module=preview) 工具结果替换为占位字符串，
        以节省后续轮次的上下文占用。
        """
        from agent.database.crud.message import replace_tool_results_by_function_name

        try:
            updated = await replace_tool_results_by_function_name(
                conversation_id=conversation_id,
                function_name="skills",
                new_content=SKILLS_PREVIEW_CLOSED_TEXT,
            )
            return SKILLS_PREVIEW_CLOSED_TEXT if updated else "未找到可关闭的 skills 预览结果"
        except Exception as e:
            return f"错误：关闭技能预览失败，失败原因：{e}"

    async def web_search(self, query, count=10, conversation_id=None):
        def search():
            client = ZhipuAiClient(api_key=os.environ.get("ZAI_KEY"))
            response = client.web_search.web_search(search_engine="search_pro", search_query=query, count=count, search_recency_filter="noLimit", content_size="high")
            return response.search_result

        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, search)
            return str([{"title": i.title, "link": i.link, "content": i.content, "media": i.media, "publish_date": i.publish_date} for i in result])
        except Exception as e:
            return f"搜索出错: {e}"

    async def web_fetch(self, url, conversation_id=None):
        loop = asyncio.get_event_loop()

        def fetch():
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            resp.encoding = resp.apparent_encoding
            parser = html2text.HTML2Text()
            parser.ignore_links = False
            parser.body_width = 0
            return parser.handle(resp.text)

        try:
            return await loop.run_in_executor(None, fetch)
        except Exception as e:
            return f"错误: {e}"

    async def soulprout_kb_tool(self, purpose, kb_id):
        try:
            await self.vdb_client.ensure_collection(KB_COLLECTION, "kb")
            results = await self.vdb_client.hybrid_search(
                KB_COLLECTION,
                query=purpose,
                limit=5,
                filter=f'kb_id == "{kb_id}"',
                output_fields=["chunk_id", "content"],
            )
            return str(results)
        except Exception as e:
            return f"错误：知识库检索失败，失败原因：{e}"

    async def kb_chunk_abstract(self, kb_id):
        rows = self.config.db_documents.find({"kb_id": kb_id})
        return str([row async for row in rows])

    async def chunk_content(self, chunk_id):
        rows = self.config.db_chunks.find({"chunk_id": chunk_id})
        return str([row.get("content") async for row in rows])

    # ─────────────────────────────────────────────────────────────────────────
    # 记忆相关工具：
    #   - base_memory：基础操作 load / search / remove
    #   - create_memory：独立的创建工具
    #   - edit_memory：独立的编辑工具
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _escape_filter_value(value: str) -> str:
        """转义 Milvus filter 表达式中的双引号与反斜杠。"""
        return value.replace("\\", "\\\\").replace('"', '\\"')

    async def _add_memory_loaded(self, conversation_id, name):
        """将 name 写入 Conversation.memory_loaded（已存在则跳过）。"""
        if not conversation_id or not name:
            return
        conv = await self.config.db_conversation.find_one({"conversation_id": conversation_id})
        if not conv:
            return
        memory_loaded = list(conv.get("memory_loaded") or [])
        if name in memory_loaded:
            return
        memory_loaded.append(name)
        await self.config.db_conversation.update_one(
            {"conversation_id": conversation_id},
            {"$set": {"memory_loaded": memory_loaded, "updated_at": datetime.utcnow()}},
        )

    async def _remove_memory_loaded(self, conversation_id, name):
        """从 Conversation.memory_loaded 中移除 name（不存在则跳过）。"""
        if not conversation_id or not name:
            return
        conv = await self.config.db_conversation.find_one({"conversation_id": conversation_id})
        if not conv:
            return
        memory_loaded = list(conv.get("memory_loaded") or [])
        if name not in memory_loaded:
            return
        memory_loaded = [n for n in memory_loaded if n != name]
        await self.config.db_conversation.update_one(
            {"conversation_id": conversation_id},
            {"$set": {"memory_loaded": memory_loaded, "updated_at": datetime.utcnow()}},
        )

    async def _query_memory_by_name(self, name, user_id):
        """按 (user_id, name) 精确查询一条记忆。"""
        name_esc = self._escape_filter_value(name)
        user_esc = self._escape_filter_value(user_id)
        results = await self.vdb_client.query(
            MEMORY_COLLECTION,
            filter=f'name == "{name_esc}" and user_id == "{user_esc}"',
            limit=1,
            output_fields=["id", "name", "description", "content", "memory_type"],
        )
        return results[0] if results else None

    async def base_memory(self, module, conversation_id, name=None, query=None):
        """统一 memory 工具：module=load/search/remove。"""
        if module == "load":
            if not name:
                return "错误：module=load 时 name 必填"
            return await self._memory_load(name, conversation_id)
        if module == "search":
            if not query or not str(query).strip():
                return "错误：module=search 时 query 必填且不能为空，请传入用于检索记忆的关键短句"
            return await self._memory_search(query, conversation_id)
        if module == "remove":
            if not name:
                return "错误：module=remove 时 name 必填"
            return await self._memory_remove(name, conversation_id)
        return f"错误：未知的 module={module}，仅支持 load / search / remove"

    async def _memory_load(self, name, conversation_id):
        user_id = await self._get_user_id_by_conversation_id(conversation_id)
        if not user_id:
            return "错误：无法获取用户信息"
        try:
            await self.vdb_client.ensure_collection(MEMORY_COLLECTION, "memory")
            memory = await self._query_memory_by_name(name, user_id)
            if not memory:
                return f"错误：未找到名为 {name} 的记忆"
            await self._add_memory_loaded(conversation_id, name)
            return {
                "name": memory.get("name"),
                "description": memory.get("description"),
                "content": memory.get("content"),
            }
        except Exception as e:
            return f"错误：加载记忆失败，失败原因：{e}"

    async def _memory_search(self, query, conversation_id):
        """
        基于 query 在当前 user_id 的记忆库做向量召回，返回相关记忆的 name 与 description 列表。
        仅返回元数据；如需 content，请再调用 module=load。
        """
        user_id = await self._get_user_id_by_conversation_id(conversation_id)
        if not user_id:
            return "错误：无法获取用户信息"
        try:
            await self.vdb_client.ensure_collection(MEMORY_COLLECTION, "memory")
            user_esc = self._escape_filter_value(user_id)
            results = await self.vdb_client.hybrid_search(
                MEMORY_COLLECTION,
                query=query,
                limit=self.config.memory_recall_top_k,
                filter=f'user_id == "{user_esc}"',
                output_fields=["name", "description"],
            )
            threshold = self.config.memory_recall_score_threshold
            hits: list[dict] = []
            for item in results:
                score = item.get("_score")
                if score is None or score < threshold:
                    continue
                name = item.get("name")
                if not name:
                    continue
                hits.append({
                    "name": name,
                    "description": item.get("description") or "",
                    "score": score,
                })
            if not hits:
                return json.dumps(
                    {"memories": [], "message": "未召回任何相关记忆"},
                    ensure_ascii=False,
                    indent=2,
                )
            return json.dumps({"memories": hits}, ensure_ascii=False, indent=2)
        except Exception as e:
            return f"错误：检索记忆失败，失败原因：{e}"

    async def _memory_remove(self, name, conversation_id):
        user_id = await self._get_user_id_by_conversation_id(conversation_id)
        if not user_id:
            return "错误：无法获取用户信息"
        try:
            await self.vdb_client.ensure_collection(MEMORY_COLLECTION, "memory")
            memory = await self._query_memory_by_name(name, user_id)
            if not memory:
                return f"错误：未找到名为 {name} 的记忆"
            name_esc = self._escape_filter_value(name)
            user_esc = self._escape_filter_value(user_id)
            await self.vdb_client.delete(
                MEMORY_COLLECTION,
                filter=f'name == "{name_esc}" and user_id == "{user_esc}"',
            )
            await self._remove_memory_loaded(conversation_id, name)
            return f"成功删除记忆 {name}"
        except Exception as e:
            return f"错误：删除记忆失败，失败原因：{e}"

    async def create_memory(self, name, description, content, conversation_id):
        user_id = await self._get_user_id_by_conversation_id(conversation_id)
        if not user_id:
            return "错误：无法获取用户信息"
        try:
            await self.vdb_client.ensure_collection(MEMORY_COLLECTION, "memory")
            existing = await self._query_memory_by_name(name, user_id)
            if existing:
                return f"错误：记忆 {name} 已存在，请改用 edit_memory"
            await self.vdb_client.insert(
                MEMORY_COLLECTION,
                {
                    "name": name,
                    "description": description,
                    "content": content,
                    "user_id": user_id,
                    "memory_type": "user",
                },
            )
            await self._add_memory_loaded(conversation_id, name)
            return f"成功创建记忆 {name}"
        except Exception as e:
            return f"错误：创建记忆失败，失败原因：{e}"

    async def edit_memory(self, name, edit_type, edit_module, text, conversation_id, old_text=None):
        if edit_type not in ("description", "content"):
            return "错误：edit_type 仅支持 description 或 content"
        if edit_module not in ("update", "replace"):
            return "错误：edit_module 仅支持 update 或 replace"
        if edit_module == "replace" and not old_text:
            return "错误：replace 模式必须填写 old_text"

        user_id = await self._get_user_id_by_conversation_id(conversation_id)
        if not user_id:
            return "错误：无法获取用户信息"
        try:
            await self.vdb_client.ensure_collection(MEMORY_COLLECTION, "memory")
            memory = await self._query_memory_by_name(name, user_id)
            if not memory:
                return f"错误：未找到名为 {name} 的记忆"

            current = memory.get(edit_type) or ""
            if edit_module == "update":
                new_value = f"{current}{text}"
            else:
                if old_text not in current:
                    return f"错误：未在原 {edit_type} 中找到 old_text"
                new_value = current.replace(old_text, text)

            payload = {
                "name": memory.get("name") or name,
                "description": memory.get("description") or "",
                "content": memory.get("content") or "",
                "user_id": user_id,
                "memory_type": memory.get("memory_type") or "user",
            }
            payload[edit_type] = new_value

            # Milvus 不支持基于 dynamic field 的就地 update；先按 (user_id, name) 删除再插入
            name_esc = self._escape_filter_value(name)
            user_esc = self._escape_filter_value(user_id)
            await self.vdb_client.delete(
                MEMORY_COLLECTION,
                filter=f'name == "{name_esc}" and user_id == "{user_esc}"',
            )
            await self.vdb_client.insert(MEMORY_COLLECTION, payload)
            return f"成功编辑记忆 {name}"
        except Exception as e:
            return f"错误：编辑记忆失败，失败原因：{e}"

    # ─────────────────────────────────────────────────────────────────────────
    # 用户个性化配置工具：user_option
    #   - info_type=userinfo / agentinfo
    #   - module=view（查看当前内容）/ add（末尾追加）/ edit（按 old_text 精确替换）
    # ─────────────────────────────────────────────────────────────────────────

    USER_OPTION_MAX_LEN = 1024

    async def user_option(self, info_type, module, conversation_id, content=None, old_text=None):
        if info_type not in ("userinfo", "agentinfo"):
            return "错误：info_type 仅支持 userinfo 或 agentinfo"
        if module not in ("view", "add", "edit"):
            return "错误：module 仅支持 view、add 或 edit"
        if module == "edit" and not old_text:
            return "错误：module=edit 时必须填写 old_text"
        if module != "view" and content is None:
            return "错误：module=add 或 edit 时 content 不能为空"

        user_id = await self._get_user_id_by_conversation_id(conversation_id)
        if not user_id:
            return "错误：无法获取用户信息"
        try:
            user = await UserInfo.find_one(UserInfo.user_id == user_id)
            if not user:
                return f"错误：未找到用户 {user_id}"

            current = getattr(user, info_type, "") or ""
            if module == "view":
                return current
            if module == "add":
                new_value = f"{current}\n{content}" if current else content
            else:
                if old_text not in current:
                    return f"错误：未在原 {info_type} 中找到 old_text，无法替换"
                new_value = current.replace(old_text, content)

            if len(new_value) > self.USER_OPTION_MAX_LEN:
                return (
                    f"错误：{info_type} 写入后将超过 {self.USER_OPTION_MAX_LEN} 字符上限"
                    f"（当前长度 {len(new_value)}），请精简后再写入"
                )

            setattr(user, info_type, new_value)
            await user.save()
            return f"成功更新用户的 {info_type}（当前长度 {len(new_value)}）"
        except Exception as e:
            return f"错误：更新用户 {info_type} 失败，失败原因：{e}"


class ToolExecutor:
    def __init__(self, config):
        self.tools = SoulproutToolFunction(config)

    def list_tools(self):
        return get_all_tool_schemas()

    async def call_tool(self, name, arguments):
        if name not in get_registered_tool_names():
            raise ValueError(f"Tool {name} is not exist")
        fn = getattr(self.tools, name, None)
        if not callable(fn) or name.startswith("_"):
            raise ValueError(
                f"Tool {name}is not in SoulproutToolFunction, please add the async method"
            )
        if not inspect.iscoroutinefunction(fn):
            raise TypeError(f"Tool {name} must be async method")
        return await fn(**arguments)


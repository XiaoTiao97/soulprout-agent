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

from agent.tool.file_process import AsyncFileProcess
from agent.tool.registry import get_all_tool_schemas, get_registered_tool_names
from agent.utils.vdb_client import VDBClient


KB_COLLECTION = os.getenv("VDB_KB_COLLECTION", "kb_collection")
MEMORY_COLLECTION = os.getenv("VDB_MEMORY_COLLECTION", "memory_collection")


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

    async def read(self, file_name, conversation_id):
        target = os.path.join(self._workspace_dir(conversation_id), file_name).replace("\\", "/")
        try:
            if file_name.endswith((".pdf", ".docx", ".doc", ".json", ".txt", ".pptx", ".xlsx")):
                return str(await self.file_process.file_parse(file_name, target))
            async with aiofiles.open(target, "r", encoding="utf-8") as f:
                return await f.read()
        except Exception as e:
            return f"错误：阅读{file_name}失败，失败原因：{e}"

    async def write(self, file_name, content, conversation_id):
        try:
            root = self._workspace_dir(conversation_id)
            os.makedirs(root, exist_ok=True)
            target = os.path.join(root, file_name)
            async with aiofiles.open(target, "a", encoding="utf-8") as f:
                await f.write(content)
            return f"成功写入{file_name}"
        except Exception as e:
            return f"错误：写入{file_name}失败，失败原因：{e}"

    async def edit(self, file_name, past_text, replace_text, conversation_id):
        try:
            target = os.path.join(self._workspace_dir(conversation_id), file_name)
            async with aiofiles.open(target, "r", encoding="utf-8") as f:
                src = await f.read()
            dst = src.replace(past_text, replace_text)
            if dst == src:
                return "文本替换失败，请检查past_text是否对应原文内容"
            async with aiofiles.open(target, "w", encoding="utf-8") as f:
                await f.write(dst)
            return f"成功修改{file_name}"
        except Exception as e:
            return f"错误：修改{file_name}失败，失败原因：{e}"

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

    async def create_agent(self, name, description, system_prompt, model, model_source, name_zh=None, tools=None, kbs=None, agents=None, supervisor_history=True, file_names=None, conversation_id=None):
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

    async def get_models_list(self, conversation_id):
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{self.main_base_url}/message/models", timeout=10.0)
            return json.dumps(resp.json(), ensure_ascii=False, indent=2)
        except Exception as e:
            return f"错误：获取模型列表失败，失败原因：{e}"

    async def get_tools_list(self, conversation_id):
        rows = []
        for item in get_all_tool_schemas():
            fn = item.get("function", {})
            rows.append({"name": fn.get("name"), "description": fn.get("description"), "inputSchema": fn.get("parameters")})
        return json.dumps(rows, ensure_ascii=False, indent=2)

    async def get_agent_cards_list(self, conversation_id):
        try:
            user_id = await self._get_user_id_by_conversation_id(conversation_id)
            if not user_id:
                return "错误：无法获取user_id"
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{self.agent_base_url}/agent_cards/{user_id}", timeout=10.0)
            return json.dumps(resp.json(), ensure_ascii=False, indent=2)
        except Exception as e:
            return f"错误：获取子智能体列表失败，失败原因：{e}"

    async def load_skill(self, source, skill_name, conversation_id):
        from agent.skill.manager import load_skill_to_workspace

        user_id = await self._get_user_id_by_conversation_id(conversation_id)
        skills = {"system": [skill_name]} if source == "system" else {"user": [skill_name]}
        result = await load_skill_to_workspace(conversation_id=conversation_id, user_id=user_id, skills=skills, workspace_base=self.config.local_file_path)
        return result.get("data") if result.get("success") else result.get("error", "加载失败")

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
    # 记忆相关工具：load_memory / create_memory / edit_memory
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

    async def load_memory(self, name, conversation_id):
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


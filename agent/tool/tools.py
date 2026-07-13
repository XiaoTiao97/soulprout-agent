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
VIEW_OUTPUT_MAX_LEN = 10000
VIEW_TRUNCATED_SUFFIX = (
    "\n\n...(content truncated: remaining output is too long and is not shown)"
)
SKILLS_SEARCH_CLOSED_TEXT = "Skills Search Closed"


class SoulproutToolFunction:
    def __init__(self, config):
        self.config = config
        self.file_process = AsyncFileProcess()
        self.vdb_client = VDBClient(
            dense_weight=config.hybrid_search_dense_weight,
            sparse_weight=config.hybrid_search_sparse_weight,
        )
        host = os.getenv("DOCKER_SERVER_HOST", "localhost")
        self.agent_base_url = f"http://{host}:8080"
        self.main_base_url = f"http://{host}:8080"

    def _workspace_dir(self, conversation_id):
        return os.path.join(self.config.local_file_path, conversation_id)

    def _build_saas_bwrap_args(self, workspace: str) -> list[str]:
        """Build bubblewrap args: shared Python/Node ro, conversation workspace rw.

        Network is intentionally kept (no --unshare-net). Host /etc/resolv.conf is often
        a symlink into /run/...; those targets must be bound or DNS (and thus pip/npm) fails.
        """
        sandbox_root = getattr(self.config, "saas_sandbox_root", None) or os.getenv(
            "SAAS_SANDBOX_ROOT", "/opt/soulprout/sandbox"
        )
        shared_py = os.path.join(sandbox_root, "python")
        shared_node = os.path.join(sandbox_root, "node")
        shared_nm = os.path.join(sandbox_root, "node_modules")

        args = [
            "--ro-bind", "/bin", "/bin",
            "--ro-bind", "/usr/bin", "/usr/bin",
            "--ro-bind", "/usr/lib", "/usr/lib",
            "--ro-bind", "/lib", "/lib",
            "--ro-bind", "/lib64", "/lib64",
            "--ro-bind", "/etc", "/etc",
        ]
        if os.path.isdir("/usr/share"):
            args.extend(["--ro-bind", "/usr/share", "/usr/share"])
        if os.path.isdir("/usr/local/bin"):
            args.extend(["--ro-bind", "/usr/local/bin", "/usr/local/bin"])
        if os.path.isdir("/usr/local/lib"):
            args.extend(["--ro-bind", "/usr/local/lib", "/usr/local/lib"])
        if os.path.isdir("/usr/local/python3.12"):
            args.extend(["--ro-bind", "/usr/local/python3.12", "/usr/local/python3.12"])
        # /etc/resolv.conf -> /run/resolvconf/... or /run/systemd/resolve/...
        for dns_dir in ("/run/resolvconf", "/run/systemd/resolve"):
            if os.path.isdir(dns_dir):
                args.extend(["--ro-bind", dns_dir, dns_dir])
        if os.path.isdir(shared_py):
            args.extend(["--ro-bind", shared_py, "/opt/py"])
        if os.path.isdir(shared_node):
            args.extend(["--ro-bind", shared_node, "/opt/node"])
        if os.path.isdir(shared_nm):
            args.extend(["--ro-bind", shared_nm, "/opt/node_modules"])

        # PIP_TARGET (not PIP_USER): avoids PEP 668 + venv --user conflict; packages land in workspace.
        args.extend([
            "--dev", "/dev",
            "--proc", "/proc",
            "--bind", workspace, "/workspace",
            "--tmpfs", "/tmp",
            "--unshare-user",
            "--unshare-pid",
            "--unshare-ipc",
            "--unshare-uts",
            "--uid", "65534",
            "--gid", "65534",
            "--chdir", "/workspace",
            "--clearenv",
            "--setenv", "HOME", "/workspace",
            "--setenv", "PATH",
            "/workspace/.npm-global/bin:/opt/node/bin:/opt/py/bin:"
            "/usr/local/python3.12/bin:/usr/local/bin:/bin:/usr/bin",
            "--setenv", "PIP_CACHE_DIR", "/tmp/pip-cache",
            "--setenv", "PIP_TARGET", "/workspace/site-packages",
            "--setenv", "PIP_DISABLE_PIP_VERSION_CHECK", "1",
            "--setenv", "PYTHONPATH",
            "/workspace/site-packages:/opt/py/lib/python3.12/site-packages:"
            "/usr/local/python3.12/lib/python3.12/site-packages",
            "--setenv", "npm_config_cache", "/tmp/npm-cache",
            "--setenv", "npm_config_prefix", "/workspace/.npm-global",
            "--setenv", "NODE_PATH",
            "/workspace/node_modules:/workspace/.npm-global/lib/node_modules:/opt/node_modules",
        ])
        pip_index = os.getenv("PIP_INDEX_URL")
        if pip_index:
            args.extend(["--setenv", "PIP_INDEX_URL", pip_index])
        npm_registry = os.getenv("NPM_CONFIG_REGISTRY") or os.getenv("npm_config_registry")
        if npm_registry:
            args.extend(["--setenv", "npm_config_registry", npm_registry])
        return args

    async def _get_user_id_by_conversation_id(self, conversation_id):
        row = await self.config.db_conversation.find_one({"conversation_id": conversation_id})
        return row.get("user_id") if row else None

    @staticmethod
    def _truncate_view_output(text: str, max_len: int = VIEW_OUTPUT_MAX_LEN) -> str:
        if len(text) <= max_len:
            return text
        return text[:max_len] + VIEW_TRUNCATED_SUFFIX

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
        try:
            if self.config.deployment_mode == "saas":
                workspace = os.path.abspath(root)
                bwrap_args = self._build_saas_bwrap_args(workspace)
                proc = await asyncio.create_subprocess_exec(
                    "bwrap",
                    *bwrap_args,
                    "/bin/sh", "-c", command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                # pip/npm installs need more than a few seconds once network works
                stdout, stderr = await asyncio.wait_for(proc.communicate(), 600)
            else:
                proc = await asyncio.create_subprocess_shell(
                    command,
                    cwd=root,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await asyncio.wait_for(proc.communicate(), 3600)
            response_text = f"Command executed with return code: {proc.returncode}\n\n"
            stdout_text = stdout.decode("utf-8", errors="replace")
            stderr_text = stderr.decode("utf-8", errors="replace")
            if stdout:
                response_text += f"Standard Output:\n{stdout_text}"
            if stderr:
                response_text += f"Standard Error:\n{stderr_text}"
            return response_text
        except asyncio.TimeoutError:
            proc.kill()
            return "错误: 命令执行超时"
        except FileNotFoundError:
            return "错误: 未找到 bwrap，SaaS 模式下 bash 需要 bubblewrap"
        except Exception as e:
            return f"错误: bash 执行失败，原因：{e}"

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
        """统一 skills 工具：module=search/view/load/close_search。"""
        if module == "search":
            if not query or not str(query).strip():
                return "错误：module=search 时 query 必填且不能为空，请传入用于检索 skill 的关键词"
            return await self._skills_search(query, conversation_id)
        if module == "view":
            return await self._skills_view(conversation_id)
        if module == "load":
            if not source or not skill_name:
                return "错误：module=load 时必须填写 source 与 skill_name"
            return await self._skills_load(source, skill_name, conversation_id)
        if module == "close_search":
            return await self._skills_close_search(conversation_id)
        return f"错误：未知的 module={module}，仅支持 search / view / load / close_search"

    async def _skills_search(self, query, conversation_id):
        """
        返回两类 skill：
            1. 系统 skill 库：通过 description 的 hybrid_search 召回 Top20 且 _score>=0.6
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

    async def _skills_view(self, conversation_id):
        """列出当前用户可用的全部 skill（系统 + 个人），不做 query 检索。"""
        from agent.skill.skill_server import (
            get_system_skills_dir,
            get_user_skills_root,
            load_skills_from_subfolders,
        )

        system_skills: list[dict] = []
        try:
            for item in load_skills_from_subfolders(get_system_skills_dir(), "system"):
                name = (item.get("name") or "").strip()
                if not name:
                    continue
                system_skills.append({
                    "name": name,
                    "description": item.get("description") or "",
                })
        except Exception as e:
            system_error = f"系统 skill 列表获取失败：{e}"
        else:
            system_error = None

        user_skills: list[dict] = []
        try:
            user_id = await self._get_user_id_by_conversation_id(conversation_id)
            if user_id:
                for item in load_skills_from_subfolders(get_user_skills_root(user_id), "user"):
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
        text = json.dumps(payload, ensure_ascii=False, indent=2)
        return self._truncate_view_output(text)

    async def _skills_load(self, source, skill_name, conversation_id):
        from agent.skill.manager import load_skill_to_workspace

        user_id = await self._get_user_id_by_conversation_id(conversation_id)
        skills = {"system": [skill_name]} if source == "system" else {"user": [skill_name]}
        result = await load_skill_to_workspace(conversation_id=conversation_id, user_id=user_id, skills=skills, workspace_base=self.config.local_file_path)
        return result.get("data") if result.get("success") else result.get("error", "加载失败")

    async def _skills_close_search(self, conversation_id):
        """
        关闭技能检索结果：将本会话历史中所有 skills 工具结果替换为占位字符串，
        以节省后续轮次的上下文占用。
        """
        from agent.database.crud.message import replace_tool_results_by_function_name

        try:
            updated = await replace_tool_results_by_function_name(
                conversation_id=conversation_id,
                function_name="skills",
                new_content=SKILLS_SEARCH_CLOSED_TEXT,
            )
            return SKILLS_SEARCH_CLOSED_TEXT if updated else "未找到可关闭的 skills 检索结果"
        except Exception as e:
            return f"错误：关闭技能检索结果失败，失败原因：{e}"

    @staticmethod
    def _ddgs_websearch(query, count=10):
        from ddgs import DDGS

        backends = ("duckduckgo", "brave", "mojeek", "startpage")
        last_error = None

        with DDGS() as ddgs:
            for backend in backends:
                try:
                    raw = ddgs.text(query, max_results=count, backend=backend)
                    if raw:
                        return [
                            {
                                "title": item.get("title") or "",
                                "link": item.get("href") or item.get("link") or "",
                                "content": item.get("body") or item.get("snippet") or "",
                                "media": item.get("source") or "",
                                "publish_date": item.get("date") or "",
                            }
                            for item in raw
                        ]
                except Exception as exc:
                    last_error = exc
                    continue

        if last_error:
            raise RuntimeError(f"所有搜索后端均无结果或失败: {last_error}")
        return []

    async def web_search(self, query, count=10, conversation_id=None):
        zai_key = (os.environ.get("ZAI_KEY") or "").strip()

        def zhipu_search():
            client = ZhipuAiClient(api_key=zai_key)
            response = client.web_search.web_search(
                search_engine="search_pro",
                search_query=query,
                count=count,
                search_recency_filter="noLimit",
                content_size="high",
            )
            return response.search_result

        try:
            loop = asyncio.get_event_loop()
            if zai_key:
                result = await loop.run_in_executor(None, zhipu_search)
                return str([{"title": i.title, "link": i.link, "content": i.content, "media": i.media, "publish_date": i.publish_date} for i in result])
            result = await loop.run_in_executor(None, lambda: self._ddgs_websearch(query, count=count))
            return str(result)
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

    async def knowledge_base(
        self,
        module,
        conversation_id=None,
        purpose=None,
        kb_id=None,
        chunk_id=None,
    ):
        """统一知识库工具：module=search / chunk_abstract / chunk_content / kb_info。"""
        if module == "search":
            if not purpose or not kb_id:
                return "错误：module=search 时 purpose 与 kb_id 必填"
            return await self._kb_search(purpose, kb_id)
        if module == "chunk_abstract":
            if not kb_id:
                return "错误：module=chunk_abstract 时 kb_id 必填"
            return await self._kb_chunk_abstract(kb_id)
        if module == "chunk_content":
            if not chunk_id:
                return "错误：module=chunk_content 时 chunk_id 必填"
            return await self._kb_chunk_content(chunk_id)
        if module == "kb_info":
            return await self._kb_info(conversation_id)
        return (
            f"错误：未知的 module={module}，"
            "仅支持 search / chunk_abstract / chunk_content / kb_info"
        )

    async def _kb_search(self, purpose, kb_id):
        try:
            await self.vdb_client.ensure_collection(KB_COLLECTION, "kb")
            kb_id_esc = self._escape_filter_value(kb_id)
            results = await self.vdb_client.hybrid_search(
                KB_COLLECTION,
                query=purpose,
                limit=5,
                filter=f'kb_id == "{kb_id_esc}"',
                output_fields=["chunk_id", "content"],
            )
            return str(results)
        except Exception as e:
            return f"错误：知识库检索失败，失败原因：{e}"

    async def _kb_chunk_abstract(self, kb_id):
        rows = self.config.db_documents.find({"kb_id": kb_id})
        return str([row async for row in rows])

    async def _kb_chunk_content(self, chunk_id):
        rows = self.config.db_chunks.find({"chunk_id": chunk_id})
        return str([row.get("content") async for row in rows])

    async def _kb_info(self, conversation_id):
        user_id = await self._get_user_id_by_conversation_id(conversation_id)
        if not user_id:
            return "错误：无法获取用户信息"
        try:
            rows = self.config.db_libraries.find({"user_id": user_id})
            libraries = [
                {
                    "kb_id": row.get("kb_id"),
                    "kb_name": row.get("kb_name"),
                    "kb_name_zh": row.get("kb_name_zh"),
                    "kb_description": row.get("kb_description"),
                    "kb_file_count": row.get("kb_file_count", 0),
                }
                async for row in rows
            ]
            return str(libraries)
        except Exception as e:
            return f"错误：获取知识库信息失败，失败原因：{e}"

    # ─────────────────────────────────────────────────────────────────────────
    # 记忆相关工具：
    #   - base_memory：基础操作 load / search / view / remove
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
        """统一 memory 工具：module=load/search/view/remove。"""
        if module == "load":
            if not name:
                return "错误：module=load 时 name 必填"
            return await self._memory_load(name, conversation_id)
        if module == "search":
            if not query or not str(query).strip():
                return "错误：module=search 时 query 必填且不能为空，请传入用于检索记忆的关键短句"
            return await self._memory_search(query, conversation_id)
        if module == "view":
            return await self._memory_view(conversation_id)
        if module == "remove":
            if not name:
                return "错误：module=remove 时 name 必填"
            return await self._memory_remove(name, conversation_id)
        return f"错误：未知的 module={module}，仅支持 load / search / view / remove"

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

    async def _memory_view(self, conversation_id):
        """列出当前 user_id 下的全部记忆（含 content），不做 query 检索。"""
        user_id = await self._get_user_id_by_conversation_id(conversation_id)
        if not user_id:
            return "错误：无法获取用户信息"
        try:
            await self.vdb_client.ensure_collection(MEMORY_COLLECTION, "memory")
            user_esc = self._escape_filter_value(user_id)
            results = await self.vdb_client.query(
                MEMORY_COLLECTION,
                filter=f'user_id == "{user_esc}"',
                limit=500,
                output_fields=["name", "description", "content", "memory_type"],
            )
            memories = []
            for item in results:
                name = item.get("name")
                if not name:
                    continue
                memories.append({
                    "name": name,
                    "description": item.get("description") or "",
                    "content": item.get("content") or "",
                    "memory_type": item.get("memory_type"),
                })
            text = json.dumps({"memories": memories}, ensure_ascii=False, indent=2)
            return self._truncate_view_output(text)
        except Exception as e:
            return f"错误：查看记忆失败，失败原因：{e}"

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

    def _normalize_feedback_options(self, raw_options):
        normalized_options = []
        option_keys = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        for index, opt in enumerate(raw_options or []):
            if isinstance(opt, str):
                key = option_keys[index] if index < len(option_keys) else str(index + 1)
                normalized_options.append({"key": key, "label": opt, "value": opt})
            elif isinstance(opt, dict):
                key = opt.get("key") or (option_keys[index] if index < len(option_keys) else str(index + 1))
                label = (opt.get("label") or opt.get("value") or "").strip()
                value = (opt.get("value") or label).strip()
                if not label and not value:
                    continue
                normalized_options.append(
                    {"key": str(key), "label": label or value, "value": value or label}
                )
        return normalized_options

    def _normalize_feedback_question(self, raw_question, index):
        if not isinstance(raw_question, dict):
            return None, f"Invalid format for question #{index + 1}"

        interaction_type = (raw_question.get("interaction_type") or "").strip().lower()
        if interaction_type not in ("choice", "input"):
            return None, f"Question #{index + 1}: interaction_type must be choice or input"

        prompt = (raw_question.get("prompt") or "").strip()
        if not prompt:
            return None, f"Question #{index + 1}: prompt is required"

        question_id = (raw_question.get("id") or raw_question.get("key") or str(index + 1)).strip()
        normalized = {
            "id": question_id,
            "interaction_type": interaction_type,
            "prompt": prompt,
        }

        if interaction_type == "choice":
            choice_mode = (raw_question.get("choice_mode") or "single").strip().lower()
            if choice_mode not in ("single", "multiple"):
                return None, f"Question #{index + 1}: choice_mode must be single or multiple"

            normalized_options = self._normalize_feedback_options(raw_question.get("options"))
            if not normalized_options:
                return None, f"Question #{index + 1}: valid options are required"

            normalized["choice_mode"] = choice_mode
            normalized["options"] = normalized_options
            normalized["allow_custom_input"] = bool(raw_question.get("allow_custom_input"))
            normalized["custom_input_placeholder"] = (
                raw_question.get("custom_input_placeholder") or "Other (please specify)"
            )
        else:
            normalized["placeholder"] = raw_question.get("placeholder") or "Enter your answer…"

        return normalized, None

    def _build_feedback_question_content(self, question, index):
        lines = [f"{index + 1}. {question['prompt']}"]
        if question["interaction_type"] == "choice":
            for opt in question["options"]:
                lines.append(f"   {opt['key']}. {opt['label']} (submit value: {opt['value']})")
            if question.get("allow_custom_input"):
                lines.append(f"   Custom input allowed: {question.get('custom_input_placeholder')}")
        else:
            lines.append(f"   Expect free-text input (placeholder: {question.get('placeholder')})")
        return lines

    async def ask_user_feedback(
        self,
        conversation_id,
        questions=None,
        description=None,
        interaction_type=None,
        prompt=None,
        options=None,
        choice_mode="single",
        allow_custom_input=False,
        custom_input_placeholder="Other (please specify)",
        placeholder="Enter your answer…",
    ):
        """Launch batched interactive user feedback (choice / input) for frontend rendering."""
        del conversation_id  # Injected by runtime; this tool only builds the interaction payload

        raw_questions = questions or []
        if not raw_questions and prompt:
            raw_questions = [
                {
                    "interaction_type": interaction_type,
                    "prompt": prompt,
                    "options": options,
                    "choice_mode": choice_mode,
                    "allow_custom_input": allow_custom_input,
                    "custom_input_placeholder": custom_input_placeholder,
                    "placeholder": placeholder,
                }
            ]

        if not raw_questions:
            return {
                "ok": False,
                "message": "Error: questions is required; list every question in a single call",
            }

        normalized_questions = []
        for index, raw_question in enumerate(raw_questions):
            normalized, error = self._normalize_feedback_question(raw_question, index)
            if error:
                return {"ok": False, "message": f"Error: {error}"}
            normalized_questions.append(normalized)

        desc = (description or "").strip()
        if not desc:
            desc = "User input required for the following items"

        content_parts = [desc]
        for index, question in enumerate(normalized_questions):
            content_parts.extend(self._build_feedback_question_content(question, index))

        content_parts.append(
            "[System] Interactive feedback request sent to the user. "
            "Wait until they submit all answers in the UI before continuing."
        )
        content_str = "\n".join(content_parts)
        json_table = {
            "description": desc,
            "submitted": False,
            "questions": normalized_questions,
        }
        return {"ok": True, "content": content_str, "json_table": json_table}

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


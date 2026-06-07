import json
import os
from pathlib import Path

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from agent.api.models.agent_card import AgentCard
load_dotenv()

class Config:
    def __init__(self):
        self.docker_server_host = os.getenv("DOCKER_SERVER_HOST", "localhost")
        self._load_model()
        self.mongodb_url = f"mongodb://{self.docker_server_host}:27017"
        self.mongodb_database = "soulprout"
        self.client = AsyncIOMotorClient(self.mongodb_url)
        self.database = self.client[self.mongodb_database]
        self.db_conversation = self.database["conversations"]
        self.db_users = self.database["users"]
        self.db_messages = self.database["messages"]

        self.db_agent_card = self.database["agent_card"]
        self.db_agent_subscription = self.database["agent_subscription"]

        self.tool_database = self.client["mcp_server"]
        self.db_tools = self.tool_database["tools_info"]

        self.mongodb_database_kb = "kb_server"
        self.database_kb = self.client[self.mongodb_database_kb]
        self.db_chunks = self.database_kb["chunks"]
        self.db_documents = self.database_kb["documents"]
        self.db_libraries = self.database_kb["libraries"]

        self.pro_model_source = os.getenv("PRO_MODEL_SOURCE")
        self.pro_model = os.getenv("PRO_MODEL")
        self.flash_model_source = os.getenv("FLASH_MODEL_SOURCE")
        self.flash_model = os.getenv("FLASH_MODEL")

        self.abstract_model_source = self.flash_model_source
        self.abstract_model = self.flash_model
        self.skills_abstract_model_source = self.flash_model_source
        self.skills_abstract_model = self.flash_model
        self.plan_model_source = self.pro_model_source
        self.plan_model = self.pro_model
        self.compact_model_source = self.flash_model_source
        self.compact_model = self.flash_model
        self.collapse_model_source = self.flash_model_source
        self.collapse_model = self.flash_model
        self.soulprout_model_source = os.getenv("SOULPROUT_MODEL_SOURCE")
        self.soulprout_model = os.getenv("SOULPROUT_MODEL")
        self.local_file_path = "/home/soulprout_data/"
        self.deployment_mode = os.getenv("DEPLOYMENT_MODE")
        self.kb_file_path = os.getenv("KB_FILE_PATH", "/home/soulprout_data/knowledge/")
        self.kb_collection = os.getenv("VDB_KB_COLLECTION", "kb_collection")
        self.agent_file_path = "/home/soulprout_agent_files/"
        self.agent_default_tools = ["read", "write", "edit", "bash", "read_picture"]

        # ─── 记忆模块（vdb memory_collection + 召回参数）──────────────────────
        self.memory_collection = os.getenv("VDB_MEMORY_COLLECTION", "memory_collection")
        self.memory_recall_top_k = 10
        # hybrid_search 融合权重：dense=embedding，sparse=BM25
        self.hybrid_search_dense_weight = 0.8
        self.hybrid_search_sparse_weight = 0.2
        # hybrid_search 融合分阈值：score >= 该值视为可匹配
        self.hybrid_search_score_threshold = 0.6
        self.memory_recall_score_threshold = 0.6

    def _load_model(self):
        model_json = Path(__file__).resolve().parent.parent / ".model.json"
        if not model_json.is_file():
            raise FileNotFoundError(f"缺少 {model_json}，请复制 agent/.model.json.example 为 agent/.model.json 并配置")
        with open(model_json, encoding="utf-8") as f:
            model_providers = json.load(f)
        default_key = "sk-xxx"
        self.models_info_list = []
        for p in model_providers:
            model_source = p["model_source"]
            api_key = p.get("api_key")
            base_url = p.get("base_url")
            setattr(self, f"{model_source}_key", api_key)
            if base_url:
                setattr(self, f"{model_source}_base_url", base_url)
            models = p.get("models")
            if models:
                self.models_info_list.append({
                    "model_source": model_source,
                    "display_name": p.get("display_name", model_source),
                    "model_use": False if api_key in [default_key, None, ""] else True,
                    "models": models,
                })

    def kb_agent_card(self):
        return AgentCard(
            user_id="soulprout",
            user_name="Soulprout",
            agent_id="soulprout_kb_agent",
            name="soulprout_kb_agent",
            name_zh="知识库智能体",
            public=False,
            description="用于复杂知识库检索的子智能体。简单检索优先使用 soulprout_kb_tool。",
            model_source=os.getenv("SOULPROUT_KB_AGENT_MODEL_SOURCE", "deepseek"),
            model=os.getenv("SOULPROUT_KB_AGENT_MODEL", "deepseek-chat"),
            system_prompt="""# Role
你是一个知识库查询智能体，目标是对用户绑定的知识库进行深度检索。

# Task
你可以使用 soulprout_kb_tool 做基础检索，也可以结合 kb_chunk_abstract 和 chunk_content 先了解知识库结构再读取原文。
请先分析用户检索意图，制定检索计划，必要时多轮检索和反思，最终返回可靠答案。""",
            supervisor_history=False,
            files=[],
            tools=["soulprout_kb_tool", "kb_chunk_abstract", "chunk_content"],
            skills=None,
            kbs=[],
            agents=None,
            announcement=None,
        )

    def default_agent_cards(self):
        return [
            AgentCard(
                user_id="soulprout",
                user_name="Soulprout",
                agent_id="soulprout_deepsearch",
                name="soulprout_deepsearch",
                name_zh="深度检索",
                public=False,
                description="用于复杂互联网调研的子智能体，具备独立上下文，可搜索、抓取、整理资料并写入本地文件。",
                model_source=os.getenv("SOULPROUT_DEEPSEARCH_MODEL_SOURCE", "ark"),
                model=os.getenv("SOULPROUT_DEEPSEARCH_MODEL", "doubao-seed-2-0-lite-260215"),
                system_prompt="""# Role
你是一个互联网深度检索智能体。

# Workflow
1. 规划：分析用户目标，制定多个检索关键词。
2. 搜索：使用 web_search 收集信息。
3. 查询：使用 web_fetch 阅读高相关网页。
4. 评估：判断资料是否足够，必要时继续检索。
5. 汇总：输出结论，必要时用 write 保存报告。""",
                supervisor_history=False,
                files=[],
                tools=["web_search", "web_fetch", "write", "edit", "read"],
                skills=None,
                kbs=[],
                agents=None,
                announcement=None,
            ),
            AgentCard(
                user_id="soulprout",
                user_name="Soulprout",
                agent_id="soulprout_pptx",
                name="soulprout_pptx",
                name_zh="PPT 智能体",
                public=False,
                description="用于根据用户资料和需求生成或编辑 PPTX 的子智能体。",
                model_source=os.getenv("SOULPROUT_PPTX_MODEL_SOURCE", "ark"),
                model=os.getenv("SOULPROUT_PPTX_MODEL", "doubao-seed-2-0-pro-260215-thinking"),
                system_prompt="""# Task
根据用户需求生成或编辑 PPTX。首次使用前加载 pptx skill，阅读技能说明后再执行。
如果缺少关键信息，先说明需要补充的内容。""",
                supervisor_history=True,
                files=[],
                tools=["skills", "bash", "read", "write", "edit"],
                skills={"system": ["pptx"]},
                kbs=[],
                agents=None,
                announcement=None,
            ),
        ]
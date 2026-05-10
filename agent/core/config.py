import os

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from agent.api.models.agent_card import AgentCard
load_dotenv()

class Config:
    def __init__(self):
        self.docker_server_host = os.getenv("DOCKER_SERVER_HOST", "localhost")
        self.deepseek_key = os.getenv("DEEPSEEK_KEY")
        self.ernie_key = os.getenv("ERNIE_KEY")
        self.ark_key = os.getenv("ARK_KEY")
        self.qwen_key = os.getenv("QWEN_KEY")
        self.minimax_key = os.getenv("MINIMAX_KEY")
        self.kimi_key = os.getenv("KIMI_KEY")
        self.glm_key = os.getenv("GLM_KEY")
        self.qianfan_key = os.getenv("QIANFAN_KEY")
        self.mimo_key = os.getenv("MIMO_KEY")
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

        self.abstract_model_source = os.getenv("ABSTRACT_MODEL_SOURCE")
        self.abstract_model = os.getenv("ABSTRACT_MODEL")
        self.skills_abstract_model_source = os.getenv("SKILLS_ABSTRACT_MODEL_SOURCE")
        self.skills_abstract_model = os.getenv("SKILLS_ABSTRACT_MODEL")
        self.deepthink_model_source = os.getenv("DEEPTHINK_MODEL_SOURCE")
        self.deepthink_model = os.getenv("DEEPTHINK_MODEL")
        self.plan_model_source = os.getenv("PLAN_MODEL_SOURCE")
        self.plan_model = os.getenv("PLAN_MODEL")
        self.short_memory_model_source = os.getenv("SHORT_MEMORY_MODEL_SOURCE")
        self.short_memory_model = os.getenv("SHORT_MEMORY_MODEL")

        default_key = "sk-xxx"
        self.models_info_list = [
            {
                "model_source": "ark",
                "model_use": False if self.ark_key in [default_key, None] else True,
                "models": [
                    {"name": "doubao-seed-2-0-pro-260215", "context_window": 256000},
                    {"name": "doubao-seed-2-0-lite-260215", "context_window": 256000},
                    {"name": "doubao-seed-2-0-mini-260215", "context_window": 256000},
                    {"name": "doubao-seed-2-0-pro-260215-thinking", "context_window": 256000},
                    {"name": "doubao-seed-2-0-lite-260215-thinking", "context_window": 256000},
                    {"name": "doubao-seed-2-0-mini-260215-thinking", "context_window": 256000},
                ]
            },
            {
                "model_source": "kimi",
                "model_use": False if self.kimi_key in [default_key, None] else True,
                "models": [
                    {"name": "kimi-k2.5-thinking", "context_window": 256000},
                    {"name": "kimi-k2.5", "context_window": 256000}
                ]
            },
            {
                "model_source": "deepseek",
                "model_use": False if self.deepseek_key in [default_key, None] else True,
                "models": [
                    {"name": "deepseek-chat", "context_window": 128000},
                    {"name": "deepseek-reasoner", "context_window": 128000},
                ]
            },
            {
                "model_source": "mimo",
                "model_use": False if self.mimo_key in [default_key, None] else True,
                "models": [
                    {"name": "mimo-v2-pro-thinking", "context_window": 1000000},
                    {"name": "mimo-v2-pro", "context_window": 1000000},
                    {"name": "mimo-v2-omni-thinking", "context_window": 256000},
                    {"name": "mimo-v2-omni", "context_window": 256000},
                ]
            },
            {
                "model_source": "glm",
                "model_use": False if self.glm_key in [default_key, None] else True,
                "models": [
                    {"name": "glm-5", "context_window": 200000},
                    {"name": "glm-5-thinking", "context_window": 200000},
                ]
            },
            {
                "model_source": "minimax",
                "model_use": False if self.minimax_key in [default_key, None] else True,
                "models": [
                    {"name": "MiniMax-M2.5", "context_window": 204800}
                ]
            },
            {
                "model_source": "qianfan",
                "model_use": False if self.qianfan_key in [default_key, None] else True,
                "models": [
                    {"name": "kimi-k2.5-thinking", "context_window": 256000},
                    {"name": "kimi-k2.5", "context_window": 256000},
                    {"name": "glm-5-thinking", "context_window": 198000},
                    {"name": "glm-5", "context_window": 198000}
                ]
            }
        ]
        self.local_file_path = "/home/soulprout_data/"
        self.agent_file_path = "/home/soulprout_agent_files/"
        self.agent_default_tools = ["read", "write", "edit", "bash", "read_picture"]

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
                tools=["load_skill", "bash", "read", "write", "edit"],
                skills={"system": ["pptx"]},
                kbs=[],
                agents=None,
                announcement=None,
            ),
        ]
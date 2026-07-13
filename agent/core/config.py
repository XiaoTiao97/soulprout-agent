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
        self.saas_sandbox_root = os.getenv("SAAS_SANDBOX_ROOT", "/opt/soulprout/sandbox")
        self.nls_app_key = os.getenv("NLS_APP_KEY")
        self.nls_token = os.getenv("NLS_TOKEN")
        self.aliyun_access_key_id = os.getenv("ALIYUN_ACCESS_KEY_ID")
        self.aliyun_access_key_secret = os.getenv("ALIYUN_ACCESS_KEY_SECRET")
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
            description="用于复杂知识库检索的子智能体。简单检索优先使用 knowledge_base。",
            model_source=os.getenv("SOULPROUT_KB_AGENT_MODEL_SOURCE", "deepseek"),
            model=os.getenv("SOULPROUT_KB_AGENT_MODEL", "deepseek-chat"),
            system_prompt="""# Role
你是一个知识库查询智能体，目标是对用户绑定的知识库进行深度检索。

# Task
你可以使用 knowledge_base（module=search）做基础检索，也可以结合 module=chunk_abstract 和 module=chunk_content 先了解知识库结构再读取原文，或用 module=kb_info 查看当前用户的知识库列表。
请先分析用户检索意图，制定检索计划，必要时多轮检索和反思，最终返回可靠答案。""",
            supervisor_history=False,
            files=[],
            tools=["knowledge_base"],
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
                model_source=self.pro_model_source,
                model=self.pro_model,
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
                tools=["web_search", "web_fetch", "write", "edit", "read", "bash", "ask_user_feedback"],
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
                model_source=self.pro_model_source,
                model=self.pro_model,
                system_prompt="""# Task
根据用户需求生成或编辑 PPTX。首次使用前加载 pptx skill，阅读技能说明后再执行。
如果缺少关键信息，先说明需要补充的内容。""",
                supervisor_history=True,
                files=[],
                tools=["skills", "bash", "read", "write", "edit", "ask_user_feedback", "knowledge_base"],
                skills={"system": ["powerpoint-pptx"]},
                kbs=[],
                agents=None,
                announcement=None,
            ),
            AgentCard(
                user_id="soulprout",
                user_name="Soulprout",
                agent_id="soulprout_create_agent",
                agent_use="single-agent",
                name="soulprout_create_agent",
                name_zh="创建Agent专家/团队",
                public=False,
                description="这是一个可以根据用户需求创建Agent员工/团队的智能体",
                model_source=self.pro_model_source,
                model=self.pro_model,
                system_prompt="""
                        # 角色设定
        
                        你是一位专业的AI员工/团队设计专家。你的使命是帮助用户将任务需求转化为高效的AI员工/团队方案。
        
                        你具备以下专业能力：
                        - 深度需求分析：能挖掘用户真实意图，识别显性和隐性需求
                        - 架构设计能力：能判断任务复杂度，设计最优的智能体配置方案
                        - 资源整合能力：熟练使用工具查看可用模型、工具和子智能体资源
                        - 方案可视化：能清晰描述每个AI员工的职责和团队协作流程
        
                        注意：
                        尽量避免使用专业化语言，而是使用口语化语言与用户进行交流
                        ---
        
                        # 工作流程
        
                        请严格按照以下8个步骤执行，其中步骤1和步骤2可能需反复多次完成：
        
                        ## 开场白
                        正式开始任务前，先主动用口语化的语言完成精简的开场白。
        
                        ## 步骤1：深度需求调研
                        主动与用户进行多轮交互沟通，逐步获取全面的任务信息，直到完全明确需求：
                        ### 任务信息获取和用户意图分析
                        - 确认任务的核心目标和具体需求内容，这一步需要多次和用户交互以完全了解用户的需求
                        ### 额外信息获取
                        - 询问用户是否有文件作为输入：如果文件内容较大（如总文件页数达1000页以上），建议用户手动上传至知识库并为即将创建的智能体绑定知识库；如果文件内容不大，可以直接上传文件
                        - 询问用户期望的输出形式：是直接回复结果，还是以指定格式的文件输出
                        - 了解用户对任务的其他特殊要求、业务规则、成本/速度等相关约束
                        - 不要询问用户任务复杂度，复杂度由你接收完所有需求后自行判断
        
                        ---
        
                        ## 步骤2：用户意图剖析、任务理解与需求反思
                        1. 思考是否已经对用户的意图有了全面明确的认知，包括用户希望使用的方法、执行的复杂程度和达到的效果等
                        2. 思考对任务的理解是否全面，包括是否有疏漏的细节部分、信息是否完整、完成方式是否正确。
                        3. 如果认为对用户、任务和需求的理解不足，需重新返回步骤1继续交互式调研，直到确认理解充足再进入步骤3。
        
                        ## 步骤3：复述确认
                        用全面自然的语言完整复述你对用户需求的理解，确保覆盖所有获取到的信息，然后询问用户："以上我对需求的理解是否正确？有没有遗漏或者需要调整的地方？"
        
                        ---
        
                        ## 步骤4：复杂度判断与架构决策
                        基于需求分析，判断采用哪种架构：
        
                        | 架构类型 | 适用场景 | 特征 |
                        |---------|---------|------|
                        | **单AI员工** | 任务边界清晰、逻辑简单、步骤明确、不需要多领域协作 | 一个智能体独立完成 |
                        | **AI团队** | 任务复杂、涉及多领域、需要分工协作、有明确流程 | 主智能体（调度员）+ 多个子智能体 |
        
                        ---
        
                        ## 步骤5：资源调研（工具调用）
                        一旦架构确定，立即调用list_info工具获取可用资源：
        
                        ### 5.1 获取模型列表
                        用途：查看可用的模型名称(model)和来源(model_source)，为每个AI员工选择合适的模型
        
                        ### 5.2 获取工具列表
                        用途：查看可用工具的类型、描述和参数，确定每个AI员工需要配置哪些工具能力
        
                        ### 5.3 获取专家库列表
                        用途：查看用户已有的专家，评估是否可以复用为子智能体
        
                        ⚠️ 必须等待工具返回结果后再进行方案设计！
        
                        ---
        
                        ## 步骤6：方案设计与呈现
                        基于资源调研结果，严格参考`create_agent`工具的参数格式要求，拟定对应的智能体/团队配置方案并呈现给用户。
        
                        ---
        
                        ## 步骤7：用户确认
                        向用户展示完整方案后，询问：
                        "以上方案是否符合你的预期？如果有调整意见请告诉我，确认后我将立即创建智能体。"
        
                        等待用户补充信息或确认信息
        
                        ---
        
                        ## 步骤8：执行创建与通知
        
                        ### 8.1 创建智能体
                        用户确认后，调用 `create_agent` 工具创建智能体/团队。
        
                        ⚠️ 创建参数说明：
                        - 如果是单AI员工：创建1个智能体，填写完整配置
                        - 如果是AI团队：先创建各个子智能体，再创建主智能体，并将创建子智能体返回的agent_id填入主智能体的agents
        
                        ### 8.2 完成通知
                        创建成功后，向用户发送通知：
        
                        ---
                        ✅ **创建完成！**
        
                        你的AI员工/团队已成功创建，信息如下：
                        - 📌 名称：[智能体名称]
                        - 🔢 数量：[X]个智能体
                        - 📂 查看位置：员工库
                        - 🚀 使用方式：新建对话后在下方员工库中选择
        
                        🎉 现在你可以开始使用了！如有需要调整的地方，随时告诉我。
                        ---
                        """,
                supervisor_history=True,
                files=[],
                tools=["create_agent", "list_info", "exec", "call_sub_agent", "skills", "knowledge_base", "ask_user_feedback"],
                skills=None,
                kbs=[],
                agents=None,
                announcement=None
            )
        ]
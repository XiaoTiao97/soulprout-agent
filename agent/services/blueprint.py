"""
Blueprint 模块：负责行动蓝图（action blueprint）规划，以及为规划所需的 skill 信息召回。

- get_skill_info: 与 skills(module=search) 工具同模式
    1. 系统 skill 库：通过 description 的 hybrid_search 召回 Top20 且 _score>=0.6
    2. 个人 skill 库：按当前 user_id 直接列出全部
- stream_action_blueprint: 通过三个智能体协作生成蓝图后流式输出；蓝图作为
  get_action_blueprint 工具结果由 agent 运行时与其他工具一样持久化（tool_calls + role=tool）。

三智能体协作架构：
1. 蓝图智能体（Generator）：沿用 PLAN_PROMPT，负责生成/修订完整蓝图。
   会预先注入用户信息、记忆简要、Skill 简要、知识库 kb_info 级元数据；
   优先基于这些内部资源规划，仅在不足时可通过 web_search 补外部信息。
   在其消息视角中，自己的输出为 assistant，批判意见作为 user 输入。
2. 批判/优化智能体（Critic）：找出蓝图的不周全之处并给出具体修改意见。
   在其消息视角中，蓝图草稿为 user，自己的批判为 assistant。
   判定蓝图合格时只输出结束标识符 CRITIC_PASS_TOKEN。
3. 最终审核智能体（Reviewer）：识别到结束标识符（或讨论轮次耗尽）后介入，
   基于蓝图模式的要求做严格终审。通过则输出 REVIEWER_PASS_TOKEN；
   否则输出整改意见，该意见以批判方身份注入讨论记录，驱动前两个智能体
   继续沟通，之后再次送审，直到通过或达到终审次数上限。

终止保障：内层讨论最多 MAX_DISCUSSION_ROUNDS 轮，外层终审最多驳回
MAX_REVIEW_CYCLES 次，上限耗尽后取最新蓝图作为最终结果，循环必然结束。
"""

import json
import os

from agent.api.models.message import ChatResponse, ModelConfig
from agent.database.crud.message import (
    get_runtime_history,
    replace_tool_results_by_function_name,
)
from agent.database.models.user import UserInfo
from agent.services import prompt
from agent.skill.skill_server import (
    get_user_skills_root,
    load_skills_from_subfolders,
)
from agent.utils.llm import LLM
from agent.utils.vdb_client import VDBClient

SKILL_COLLECTION = os.getenv("VDB_SKILL_COLLECTION", "skill_collection")
BLUEPRINT_DISCARDED_TEXT = (
    "A new blueprint has been generated. This blueprint is discarded by default."
)

# ─────────────────────────────────────────────────────────────────────────────
# 多智能体协作配置
# ─────────────────────────────────────────────────────────────────────────────

# 每一个终审周期内，批判/优化智能体与蓝图智能体最多沟通的轮数（一轮 = 批判 + 修订）
MAX_DISCUSSION_ROUNDS = 3
# 最终审核智能体最多驳回的次数，超过后直接采用当前最新蓝图，保证流程必然终止
MAX_REVIEW_CYCLES = 2
# 蓝图智能体单次生成/修订轮次内，最多允许的 web_search 工具调用轮数
MAX_GENERATOR_WEB_SEARCH_ROUNDS = 2
# 批判/优化智能体判定蓝图合格时输出的结束标识符
CRITIC_PASS_TOKEN = "[DISCUSSION_COMPLETE]"
# 最终审核智能体判定蓝图通过终审时输出的标识符
REVIEWER_PASS_TOKEN = "[BLUEPRINT_APPROVED]"
# 流式下发最终蓝图时每个分片的字符数
BLUEPRINT_STREAM_CHUNK_SIZE = 120
# 讨论过程进度流：攒满多少字符后向下游推送一段 plan_progress
BLUEPRINT_PROGRESS_CHUNK_SIZE = 120
# 前端识别的讨论进度流类型（非最终蓝图）
PLAN_PROGRESS_TYPE = "plan_progress"
# 前端识别的最终蓝图流类型
PLAN_FINAL_TYPE = "plan"

# RESOURCE_PRIORITY_PROMPT_CHINESE:
# # 规划资源优先级
# 1. 优先使用下方已提供的用户信息、记忆简要、Skills、知识库信息做规划
# 2. 仅当这些内部资源不足以支撑高质量规划时（如需要时效性外部事实），才调用 web_search
# 3. 不要用 web_search 重复验证内部资源里已经有的信息
# 4. 规划中引用工具/技能时，名称必须来自可用工具列表或 Skills 列表

BLUEPRINT_RESOURCE_PRIORITY_PROMPT = """# Planning Resource Priority
1. Prioritize the User Profile, Memory briefs, Skills, and Knowledge Base information already provided below when planning.
2. Only call web_search when these internal resources are insufficient for high-quality planning (e.g. you need timely external facts that are not covered above).
3. Do NOT use web_search merely to reconfirm information already present in the internal resources.
4. When the blueprint references Tools or Skills, their names must come from the available tool list or Skills list."""

# RESOURCE_PROMPT_CHINESE:
# # 可用内部资源（规划时优先使用）
# ## 用户信息
# {user_info}
# ## 相关记忆（仅 name + description）
# {memories}
# ## 知识库列表（kb_info 层级）
# {kb_info}

BLUEPRINT_RESOURCE_PROMPT = """# Available Internal Resources (prioritize these over web search)
## User Profile
{user_info}

## Relevant Memories (name + description only)
{memories}

## Knowledge Bases (kb_info level only)
{kb_info}"""

# CRITIC_PROMPT_CHINESE:
# # 角色
# 你是一名严苛的蓝图评审专家。另一名规划专家（蓝图智能体）会把行动蓝图草稿发给你
# （以 user 消息出现），你此前的批判意见会以你自己的 assistant 消息出现。
# 你的职责是找出蓝图中所有不周全之处，推动其达到可直接执行的高质量标准。
#
# # 评审维度
# 1. 是否真正还原了用户处境、拆解出字面问题背后的真实需求
# 2. 是否识别了隐含约束与前置依赖（时间、预算、地域、能力、需先确认的信息等）
# 3. 步骤中引用的工具(Tools)与技能(Skills)名称是否真实存在于任务上下文中、用法是否合理
# 4. 执行步骤是否具体可执行、有优先级排序、依赖关系是否清晰
# 5. 是否违反铁律：不替主Agent执行任务；不输出给用户看的内容；简单问题不过度规划
#
# # 输出规则
# - 存在实质性问题时：输出编号列出的、具体且可操作的修改意见，不要替对方重写蓝图
# - 不存在实质性问题时：只输出 [DISCUSSION_COMPLETE]，不要附加任何其他文字
# - 不要为了挑刺而挑刺：若剩余分歧仅是措辞或风格偏好，应判定为合格

BLUEPRINT_CRITIC_PROMPT = """# Role
You are a rigorous blueprint review expert. A planning expert (the blueprint agent) will send you drafts of an action blueprint (appearing as user messages), and your previous critiques appear as your own assistant messages. Your responsibility is to find every inadequacy in the blueprint and push it to a high-quality, directly executable standard.

# Task Context (the same information the blueprint agent received)
{task_context}

# Review Dimensions
1. Does the blueprint truly restore the user's situation and deconstruct the real needs behind the literal question?
2. Are implicit constraints and pre-dependencies identified (time, budget, region, capability, information that must be confirmed first, etc.)?
3. Do the Tools and Skills referenced in the steps actually exist in the task context, and are they used reasonably?
4. Are the execution steps concrete and executable, prioritized, with clear dependencies?
5. Are the iron rules violated: never execute tasks on behalf of the main Agent; never output content intended for the user; never over-plan a simple question?

# Output Rules
- If substantive problems exist: output numbered, specific, and actionable improvement feedback. Do NOT rewrite the blueprint yourself.
- If no substantive problems exist: output ONLY {critic_pass_token} with no other text.
- Do not nitpick for the sake of nitpicking: if the remaining disagreements are merely wording or style preferences, the blueprint should be judged as qualified."""

# REVISE_WRAPPER_CHINESE:
# 以下是针对你上一版蓝图的评审意见：
# {critique}
# 请结合以上意见与最初的任务要求，输出完整的修订版行动蓝图。
# 只输出蓝图本身，不要输出致谢、解释或任何与蓝图无关的内容。

BLUEPRINT_REVISE_WRAPPER = """The following is review feedback on your previous blueprint:
{critique}

Based on this feedback and the original task requirements, output the complete revised action blueprint. Output ONLY the blueprint itself — no acknowledgements, no explanations, and no content unrelated to the blueprint."""

# REVIEWER_PROMPT_CHINESE:
# # 角色
# 你是行动蓝图的最终审核专家，是蓝图交付给主Agent之前的最后一道关卡。
# 一份蓝图已经过蓝图智能体与批判智能体多轮讨论打磨，现在由你做最终严格审查。
#
# # 审查标准（基于蓝图模式的要求，全部满足才能通过）
# 1. 还原用户处境：分析用户为何提问、认知水平与预设答案形态
# 2. 拆解真实需求：区分字面问题与真正要解决的问题
# 3. 识别隐含约束与前置依赖，并指出需要主Agent先与用户确认的信息差
# 4. 基于第一性原理论述解决路径，交付水准精准
# 5. 执行步骤结构化：有优先级、依赖关系，且准确写出真实存在的工具(Tools)与技能(Skills)名称
# 6. 遵守铁律：不替主Agent执行任务；只输出给主Agent看的执行蓝图；
#    简单问题应直接声明无需额外规划；每个判断都有依据
#
# # 输出规则
# - 完全符合要求：只输出 [BLUEPRINT_APPROVED]，不要附加任何其他文字
# - 不符合要求：输出编号列出的、必须整改的具体意见，要求前两个智能体继续沟通修订

BLUEPRINT_REVIEWER_PROMPT = """# Role
You are the final review expert for action blueprints — the last gate before the blueprint is delivered to the main Agent. A blueprint has been polished through multiple rounds of discussion between the blueprint agent and the critic agent. You now perform the final strict review.

# Review Criteria (based on the requirements of the blueprint mode; ALL must be satisfied to pass)
1. Restores the user's situation: analyzes why the user asked, their knowledge level, and the answer format they presuppose.
2. Deconstructs the real needs: distinguishes the literal question from the problem that really needs solving.
3. Identifies implicit constraints and pre-dependencies, and points out information gaps the main Agent must confirm with the user first.
4. Discusses the resolution path from first principles with research-level precision.
5. Structured execution steps: prioritized, with dependencies, and accurately naming Tools and Skills that actually exist in the task context.
6. Obeys the iron rules: never executes tasks on behalf of the main Agent; only outputs an execution blueprint for the main Agent (never user-facing content); a simple question should directly state that no extra planning is needed; every judgment has a basis.

# Output Rules
- If the blueprint fully meets the requirements: output ONLY {reviewer_pass_token} with no other text.
- If it does not meet the requirements: output numbered, specific, and mandatory revision feedback, requiring the two agents above to continue their discussion and revise."""

# REVIEWER_INPUT_CHINESE:
# # 任务上下文
# {task_context}
#
# # 待终审的行动蓝图
# {blueprint}
#
# 请按要求进行最终审查。

BLUEPRINT_REVIEWER_INPUT = """# Task Context
{task_context}

# Action Blueprint Awaiting Final Review
{blueprint}

Please perform the final review as required."""

# REVIEWER_FEEDBACK_WRAPPER_CHINESE:
# 最终审核未通过。终审专家提出了以下必须整改的意见：
# {feedback}

BLUEPRINT_REVIEWER_FEEDBACK_WRAPPER = """The final review did NOT pass. The final review expert raised the following mandatory revision feedback:
{feedback}"""


class Blueprint:
    def __init__(
        self,
        config,
        is_sub_agent,
        session_id,
        user_id,
        conversation_id,
        input_text,
        kb_use,
        time_now,
        soulprout_tools,
        tool_executor,
    ):
        self.config = config
        self.is_sub_agent = is_sub_agent
        self.session_id = session_id
        self.user_id = user_id
        self.conversation_id = conversation_id
        self.input_text = input_text
        self.kb_use = kb_use or []
        self.time_now = time_now
        self.soulprout_tools = soulprout_tools or []
        self.tool_executor = tool_executor

        self.vdb_client = VDBClient(
            dense_weight=config.hybrid_search_dense_weight,
            sparse_weight=config.hybrid_search_sparse_weight,
        )
        self.llm = LLM(config)
        self.last_blueprint_text = ""

    # ─────────────────────────────────────────────────────────────────────────
    # 内部工具方法
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _escape_filter_value(value: str) -> str:
        return value.replace("\\", "\\\\").replace('"', '\\"')

    @staticmethod
    async def _summary_history(input_text, history_list):
        history_summarize_info = ""
        for per_history in history_list:
            if per_history["role"] == "user":
                user_message = per_history["content"]
                history_summarize_info += f"USER：{user_message}\n"
            elif per_history["role"] == "assistant":
                assistant_message = per_history["content"]
                history_summarize_info += (
                    f"ASSISTANT：{assistant_message}\n" if assistant_message else ""
                )
        history_summarize_info += f"USER：{input_text}\n\n"
        return history_summarize_info

    async def _get_user_info_brief(self):
        """读取用户画像简要信息（username / userinfo / agentinfo）。"""
        if not self.user_id:
            return "No user profile available."
        try:
            user = await UserInfo.find_one(UserInfo.user_id == self.user_id)
            if not user:
                return "No user profile available."
            return (
                f"User-name: {(getattr(user, 'username', '') or '').strip()}\n"
                f"User-info: {(getattr(user, 'userinfo', '') or '').strip()}\n"
                f"Agent-info: {(getattr(user, 'agentinfo', '') or '').strip()}"
            )
        except Exception as e:
            print(f"Blueprint user info error: {e}")
            return "Failed to load user profile."

    async def _get_memory_briefs(self):
        """
        只读召回与当前输入相关的记忆简要（name + description），不写库、不污染会话。
        """
        if not self.input_text or not self.user_id:
            return []
        memories: list[dict] = []
        try:
            collection = self.config.memory_collection
            await self.vdb_client.ensure_collection(collection, "memory")
            user_esc = self._escape_filter_value(self.user_id)
            results = await self.vdb_client.hybrid_search(
                collection,
                query=self.input_text,
                limit=self.config.memory_recall_top_k,
                filter=f'user_id == "{user_esc}"',
                output_fields=["name", "description"],
            )
            for item in results:
                name = item.get("name")
                if not name:
                    continue
                score = item.get("_score")
                if (
                    score is None
                    or score < self.config.memory_recall_score_threshold
                ):
                    continue
                memories.append({
                    "name": name,
                    "description": item.get("description") or "",
                    "score": score,
                })
        except Exception as e:
            print(f"Blueprint memory recall error: {e}")
        return memories

    async def _get_kb_info_brief(self):
        """
        获取当前用户全部知识库的 kb_info 层级简要信息
       （kb_id / kb_name / kb_name_zh / kb_description / kb_file_count），不含正文片段。
        """
        if not self.user_id:
            return []
        try:
            rows = self.config.db_libraries.find({"user_id": self.user_id})
            return [
                {
                    "kb_id": row.get("kb_id"),
                    "kb_name": row.get("kb_name"),
                    "kb_name_zh": row.get("kb_name_zh"),
                    "kb_description": row.get("kb_description"),
                    "kb_file_count": row.get("kb_file_count", 0),
                }
                async for row in rows
            ]
        except Exception as e:
            print(f"Blueprint kb_info error: {e}")
            return []

    def _format_resource_prompt(self, user_info, memories, kb_list):
        memory_text = (
            "\n".join(
                f"- name: {m['name']}\ndescription: {m['description']}"
                for m in memories
            )
            if memories
            else "No relevant memories found."
        )
        if kb_list:
            kb_text = "\n".join(str(item) for item in kb_list)
        else:
            kb_text = "No knowledge bases found."
        return BLUEPRINT_RESOURCE_PROMPT.format(
            user_info=user_info,
            memories=memory_text,
            kb_info=kb_text,
        )

    def _get_web_search_tool_schema(self):
        for tool in self.tool_executor.list_tools():
            if tool.get("function", {}).get("name") == "web_search":
                return [tool]
        return []

    # ─────────────────────────────────────────────────────────────────────────
    # Skill 召回
    # ─────────────────────────────────────────────────────────────────────────

    async def get_skill_info(self):
        """
        返回供规划专家参考的 skill 列表：
        1. 系统 skill：通过 description 的 hybrid_search 召回 Top20 且 _score>=0.6
        2. 个人 skill：按当前 user_id 全量列出
        """
        system_skills: list[dict] = []
        try:
            await self.vdb_client.ensure_collection(SKILL_COLLECTION, "skill")
            results = await self.vdb_client.hybrid_search(
                SKILL_COLLECTION,
                query=self.input_text or "",
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
                    "type": "system",
                    "name": name,
                    "description": item.get("description") or "",
                })
        except Exception as e:
            print(f"Blueprint system skill recall error: {e}")

        user_skills: list[dict] = []
        if self.user_id:
            try:
                raw_user_skills = load_skills_from_subfolders(
                    get_user_skills_root(self.user_id), "user"
                )
                for item in raw_user_skills:
                    name = (item.get("name") or "").strip()
                    if not name:
                        continue
                    user_skills.append({
                        "type": "user",
                        "name": name,
                        "description": item.get("description") or "",
                    })
            except Exception as e:
                print(f"Blueprint user skill list error: {e}")

        return system_skills + user_skills

    # ─────────────────────────────────────────────────────────────────────────
    # 多智能体协作：基础设施
    # ─────────────────────────────────────────────────────────────────────────

    def _make_model_config(self, tools=None):
        # llm.chat 会原地修改 model 字段（剥离 -thinking 后缀），因此每次调用都新建一份
        return ModelConfig(
            model_source=self.config.plan_model_source,
            model=self.config.plan_model,
            tools=tools or [],
            stream=False,
        )

    def _sse_chunk(self, msg_type: str, content: str) -> str:
        return ChatResponse(
            conversation_id=self.conversation_id,
            user_id=self.user_id,
            type=msg_type,
            role="assistant",
            content=content,
        ).model_dump_json()

    async def _pump_llm(self, messages, tools=None, result_holder=None):
        """
        流式调用模型：边生成边 yield plan_progress SSE 分片；
        结束后把 (text, tool_calls) 写入 result_holder[0]（若提供）。
        """
        text = ""
        tool_calls_acc: dict[int, dict] = {}
        progress_buffer = ""
        stream = self.llm.chat(messages, self._make_model_config(tools=tools))
        async for chunk in stream:
            if len(chunk.choices) == 0:
                continue
            delta = chunk.choices[0].delta
            if isinstance(getattr(delta, "content", None), str) and delta.content:
                text += delta.content
                progress_buffer += delta.content
                while len(progress_buffer) >= BLUEPRINT_PROGRESS_CHUNK_SIZE:
                    piece = progress_buffer[:BLUEPRINT_PROGRESS_CHUNK_SIZE]
                    progress_buffer = progress_buffer[BLUEPRINT_PROGRESS_CHUNK_SIZE:]
                    yield self._sse_chunk(PLAN_PROGRESS_TYPE, piece)
            if isinstance(getattr(delta, "tool_calls", None), list):
                for tc in delta.tool_calls:
                    idx = tc.index if getattr(tc, "index", None) is not None else 0
                    entry = tool_calls_acc.setdefault(
                        idx, {"id": "", "name": "", "arguments": ""}
                    )
                    if getattr(tc, "id", None):
                        entry["id"] = tc.id
                    function = getattr(tc, "function", None)
                    if function is None:
                        continue
                    if getattr(function, "name", None):
                        entry["name"] = function.name
                    if getattr(function, "arguments", None):
                        entry["arguments"] += function.arguments
        if progress_buffer:
            yield self._sse_chunk(PLAN_PROGRESS_TYPE, progress_buffer)
        tool_calls = [tool_calls_acc[i] for i in sorted(tool_calls_acc)]
        if result_holder is not None:
            result_holder.append((text.strip(), tool_calls))

    async def _stream_plain_agent(self, messages, result_holder=None):
        """无工具智能体（批判/终审）：yield 进度分片，文本写入 result_holder[0]。"""
        holder: list = []
        async for chunk in self._pump_llm(messages, tools=None, result_holder=holder):
            yield chunk
        text = holder[0][0] if holder else ""
        if result_holder is not None:
            result_holder.append(text)

    async def _stream_generator_agent(self, messages, result_holder=None):
        """
        蓝图智能体：可按需 web_search；yield 进度分片，最终文本写入 result_holder[0]。
        """
        web_search_tools = self._get_web_search_tool_schema()
        working = list(messages)
        final_text = ""
        for round_index in range(MAX_GENERATOR_WEB_SEARCH_ROUNDS + 1):
            allow_tools = (
                web_search_tools
                if web_search_tools and round_index < MAX_GENERATOR_WEB_SEARCH_ROUNDS
                else None
            )
            holder: list = []
            async for chunk in self._pump_llm(
                working, tools=allow_tools, result_holder=holder
            ):
                yield chunk
            text, tool_calls = holder[0] if holder else ("", [])
            if not tool_calls:
                final_text = text
                break

            assistant_tool_calls = []
            for tc in tool_calls:
                assistant_tool_calls.append({
                    "id": tc["id"] or f"blueprint_web_search_{round_index}",
                    "type": "function",
                    "function": {
                        "name": tc["name"] or "web_search",
                        "arguments": tc["arguments"] or "{}",
                    },
                })
            working.append({
                "role": "assistant",
                "content": text or None,
                "tool_calls": assistant_tool_calls,
            })

            for tc in assistant_tool_calls:
                name = tc["function"]["name"]
                tool_call_id = tc["id"]
                if name != "web_search":
                    result = (
                        f"Tool `{name}` is not available to the blueprint agent. "
                        "Only web_search is allowed, and only when internal resources are insufficient."
                    )
                else:
                    try:
                        args = json.loads(tc["function"]["arguments"] or "{}")
                    except Exception:
                        args = {}
                    query = (args.get("query") or self.input_text or "").strip()
                    try:
                        count = min(int(args.get("count") or 5), 5)
                    except Exception:
                        count = 5
                    print(f"blueprint generator web_search: query={query!r}, count={count}")
                    result = await self.tool_executor.call_tool(
                        "web_search",
                        {
                            "query": query,
                            "count": count,
                            "conversation_id": self.conversation_id,
                        },
                    )
                working.append({
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": str(result),
                })
        else:
            holder = []
            async for chunk in self._pump_llm(working, tools=None, result_holder=holder):
                yield chunk
            final_text = holder[0][0] if holder else ""

        if result_holder is not None:
            result_holder.append(final_text)
    async def _build_task_context(self):
        """构建三个智能体共享的任务上下文（用户/记忆/技能/知识库/工具/历史）。"""
        tools = self.tool_executor.list_tools()
        skills = await self.get_skill_info()
        tools_use_final = []
        for tool in tools:
            tool_name = tool.get("function", {}).get("name")
            if tool_name in self.soulprout_tools:
                tools_use_final.append(tool)
            elif tool_name in ["soulprout_kb_agent", "knowledge_base"]:
                tools_use_final.append(tool)

        history = await get_runtime_history(
            self.is_sub_agent, self.session_id, self.conversation_id
        )
        history_list = [
            {"role": item.role, "content": item.content}
            for item in history
            if item.role not in ["agent"]
        ]
        summary_info = await self._summary_history(self.input_text, history_list)

        user_info = await self._get_user_info_brief()
        memories = await self._get_memory_briefs()
        kb_list = await self._get_kb_info_brief()
        resource_prompt = self._format_resource_prompt(
            user_info=user_info,
            memories=memories,
            kb_list=kb_list,
        )

        info_prompt = prompt.PLAN_INFO_PROMPT.format(
            time_now=self.time_now,
            tools_use_final=tools_use_final,
            skills=skills,
        )
        history_prompt = prompt.PLAN_HISTORY_PROMPT.format(summary_info=summary_info)
        return {
            "resource_prompt": resource_prompt,
            "priority_prompt": BLUEPRINT_RESOURCE_PRIORITY_PROMPT,
            "info_prompt": info_prompt,
            "history_prompt": history_prompt,
        }

    @staticmethod
    def _context_as_text(context):
        parts = [
            context["priority_prompt"],
            context["resource_prompt"],
            context["info_prompt"],
            context["history_prompt"],
        ]
        return "\n\n".join(parts)

    # ─────────────────────────────────────────────────────────────────────────
    # 多智能体协作：三个智能体的消息视角
    # ─────────────────────────────────────────────────────────────────────────

    def _build_generator_messages(self, context, discussion):
        """
        蓝图智能体视角：自己的蓝图输出为 assistant，批判/整改意见作为 user 输入。
        """
        messages = [{"role": "system", "content": prompt.PLAN_PROMPT}]
        messages.append({"role": "user", "content": context["priority_prompt"]})
        messages.append({"role": "user", "content": context["resource_prompt"]})
        messages.append({"role": "user", "content": context["info_prompt"]})
        messages.append({"role": "user", "content": context["history_prompt"]})
        for entry in discussion:
            if entry["agent"] == "generator":
                messages.append({"role": "assistant", "content": entry["content"]})
            else:
                messages.append({
                    "role": "user",
                    "content": BLUEPRINT_REVISE_WRAPPER.format(
                        critique=entry["content"]
                    ),
                })
        return messages

    def _build_critic_messages(self, context, discussion):
        """
        批判/优化智能体视角：蓝图草稿为 user，自己的批判为 assistant。
        """
        messages = [{
            "role": "system",
            "content": BLUEPRINT_CRITIC_PROMPT.format(
                task_context=self._context_as_text(context),
                critic_pass_token=CRITIC_PASS_TOKEN,
            ),
        }]
        for entry in discussion:
            role = "user" if entry["agent"] == "generator" else "assistant"
            messages.append({"role": role, "content": entry["content"]})
        return messages

    def _build_reviewer_messages(self, context, blueprint_text):
        """最终审核智能体：单轮严格审查，不参与讨论历史。"""
        return [
            {
                "role": "system",
                "content": BLUEPRINT_REVIEWER_PROMPT.format(
                    reviewer_pass_token=REVIEWER_PASS_TOKEN
                ),
            },
            {
                "role": "user",
                "content": BLUEPRINT_REVIEWER_INPUT.format(
                    task_context=self._context_as_text(context),
                    blueprint=blueprint_text,
                ),
            },
        ]

    # ─────────────────────────────────────────────────────────────────────────
    # 多智能体协作：讨论循环
    # ─────────────────────────────────────────────────────────────────────────

    async def _generator_turn(self, context, discussion, result_holder=None):
        """yield 进度 SSE；本轮蓝图文本写入 result_holder[0]。"""
        holder: list = []
        async for chunk in self._stream_generator_agent(
            self._build_generator_messages(context, discussion),
            result_holder=holder,
        ):
            yield chunk
        blueprint_text = holder[0] if holder else ""
        discussion.append({"agent": "generator", "content": blueprint_text})
        if result_holder is not None:
            result_holder.append(blueprint_text)

    async def _run_discussion(self, context, discussion, blueprint_text, result_holder=None):
        """
        蓝图智能体与批判/优化智能体的沟通循环（流式）：
        批判智能体输出 CRITIC_PASS_TOKEN 或轮次耗尽时结束；最新蓝图写入 result_holder[0]。
        """
        for round_index in range(MAX_DISCUSSION_ROUNDS):
            if discussion and discussion[-1]["agent"] == "critic":
                holder: list = []
                async for chunk in self._generator_turn(
                    context, discussion, result_holder=holder
                ):
                    yield chunk
                blueprint_text = holder[0] if holder else blueprint_text
                print(f"blueprint revised (round {round_index + 1})")

            critic_holder: list = []
            async for chunk in self._stream_plain_agent(
                self._build_critic_messages(context, discussion),
                result_holder=critic_holder,
            ):
                yield chunk
            critique = critic_holder[0] if critic_holder else ""

            if CRITIC_PASS_TOKEN in critique:
                print(f"critic passed at round {round_index + 1}")
                if result_holder is not None:
                    result_holder.append(blueprint_text)
                return
            discussion.append({"agent": "critic", "content": critique})
            print(f"critic feedback (round {round_index + 1}):", critique)

        if discussion and discussion[-1]["agent"] == "critic":
            holder = []
            async for chunk in self._generator_turn(
                context, discussion, result_holder=holder
            ):
                yield chunk
            blueprint_text = holder[0] if holder else blueprint_text
            print("discussion rounds exhausted, final revision applied")
        if result_holder is not None:
            result_holder.append(blueprint_text)

    @staticmethod
    def _sanitize_blueprint(text):
        for token in (CRITIC_PASS_TOKEN, REVIEWER_PASS_TOKEN):
            text = text.replace(token, "")
        return text.strip()

    # ─────────────────────────────────────────────────────────────────────────
    # 行动蓝图生成
    # ─────────────────────────────────────────────────────────────────────────

    async def stream_action_blueprint(self):
        try:
            await replace_tool_results_by_function_name(
                conversation_id=self.conversation_id,
                function_name="get_action_blueprint",
                new_content=BLUEPRINT_DISCARDED_TEXT,
            )
            context = await self._build_task_context()

            # 阶段一：蓝图智能体生成初稿（流式进度）
            discussion: list[dict] = []
            holder: list = []
            async for chunk in self._generator_turn(
                context, discussion, result_holder=holder
            ):
                yield chunk
            blueprint_text = holder[0] if holder else ""
            print("blueprint initial draft generated")

            # 阶段二/三：讨论循环 + 最终审核循环
            for review_cycle in range(MAX_REVIEW_CYCLES + 1):
                disc_holder: list = []
                async for chunk in self._run_discussion(
                    context, discussion, blueprint_text, result_holder=disc_holder
                ):
                    yield chunk
                blueprint_text = disc_holder[0] if disc_holder else blueprint_text

                if review_cycle == MAX_REVIEW_CYCLES:
                    print("review cycles exhausted, using latest blueprint")
                    break

                review_holder: list = []
                async for chunk in self._stream_plain_agent(
                    self._build_reviewer_messages(context, blueprint_text),
                    result_holder=review_holder,
                ):
                    yield chunk
                verdict = review_holder[0] if review_holder else ""

                if REVIEWER_PASS_TOKEN in verdict:
                    print(f"final reviewer approved at cycle {review_cycle + 1}")
                    break
                print(f"final reviewer rejected (cycle {review_cycle + 1}):", verdict)
                discussion.append({
                    "agent": "critic",
                    "content": BLUEPRINT_REVIEWER_FEEDBACK_WRAPPER.format(
                        feedback=verdict
                    ),
                })

            plan = self._sanitize_blueprint(blueprint_text)

            # 最终蓝图以 type=plan 下发，供前端正式蓝图框展示
            for i in range(0, len(plan), BLUEPRINT_STREAM_CHUNK_SIZE):
                yield self._sse_chunk(
                    PLAN_FINAL_TYPE, plan[i : i + BLUEPRINT_STREAM_CHUNK_SIZE]
                )

            self.last_blueprint_text = plan
            print("action_blueprint generated:", plan)

        except Exception as e:
            self.last_blueprint_text = ""
            yield self._sse_chunk(PLAN_FINAL_TYPE, "")
            print(f"Blueprint Error: {e}")

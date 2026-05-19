"""
Blueprint 模块：负责行动蓝图（action blueprint）规划，以及为规划所需的 skill 信息召回。

- get_skill_info: 与 skills(module=preview) 工具同模式
    1. 系统 skill 库：通过 description 的 hybrid_search 召回 Top20 且 _score>=0.4
    2. 个人 skill 库：按当前 user_id 直接列出全部
- stream_action_blueprint: 调用规划专家模型，基于历史对话、可用工具与召回的 skill
  流式输出主 Agent 可直接执行的结构化蓝图，并将蓝图持久化到会话历史与 Conversation 表。
"""

import os
from datetime import datetime

from agent.api.models.message import ChatResponse, ModelConfig
from agent.database.crud.conversation import get_conversation_by_id
from agent.database.crud.message import (
    delete_runtime_messages,
    get_runtime_history,
    save_message,
)
from agent.database.models.message import AgentMessage
from agent.services import prompt
from agent.skill.skill_server import (
    get_user_skills_root,
    load_skills_from_subfolders,
)
from agent.utils.llm import LLM
from agent.utils.vdb_client import VDBClient

SKILL_COLLECTION = os.getenv("VDB_SKILL_COLLECTION", "skill_collection")


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

        self.vdb_client = VDBClient()
        self.llm = LLM(config)
        self.last_blueprint_text = ""

    # ─────────────────────────────────────────────────────────────────────────
    # 内部工具方法
    # ─────────────────────────────────────────────────────────────────────────

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

    async def _get_kb_prompt(self):
        kb_query = {"user_id": self.user_id, "kb_id": {"$in": self.kb_use}}
        result = self.config.db_libraries.find(kb_query)
        result_total = ""
        async for res in result:
            res_total = {
                "kb_id": res.get("kb_id"),
                "kb_name_zh": res.get("kb_name_zh"),
                "kb_description": res.get("kb_description"),
            }
            result_total += str(res_total) + "\n"
        return prompt.KB_PROMPT.format(result_total=result_total)

    # ─────────────────────────────────────────────────────────────────────────
    # Skill 召回
    # ─────────────────────────────────────────────────────────────────────────

    async def get_skill_info(self):
        """
        返回供规划专家参考的 skill 列表：
        1. 系统 skill：通过 description 的 hybrid_search 召回 Top20 且 _score>=0.4
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
    # 行动蓝图生成
    # ─────────────────────────────────────────────────────────────────────────

    async def stream_action_blueprint(self):
        try:
            model_config = ModelConfig(
                model_source=self.config.plan_model_source,
                model=self.config.plan_model,
                tools=[],
                stream=False,
            )
            tools = self.tool_executor.list_tools()
            skills = await self.get_skill_info()
            tools_use_final = []
            for tool in tools:
                tool_name = tool.get("function", {}).get("name")
                if tool_name in self.soulprout_tools:
                    tools_use_final.append(tool)
                elif tool_name in ["soulprout_kb_agent", "soulprout_kb_tool"]:
                    tools_use_final.append(tool)

            message = [{"role": "system", "content": prompt.PLAN_PROMPT}]
            history = await get_runtime_history(
                self.is_sub_agent, self.session_id, self.conversation_id
            )
            history_list = [
                {"role": item.role, "content": item.content}
                for item in history
                if item.role not in ["agent", "plan"]
            ]
            summary_info = await self._summary_history(self.input_text, history_list)

            if len(self.kb_use) > 0:
                message.append({"role": "user", "content": await self._get_kb_prompt()})
            message.append({
                "role": "user",
                "content": prompt.PLAN_INFO_PROMPT.format(
                    time_now=self.time_now,
                    tools_use_final=tools_use_final,
                    skills=skills,
                ),
            })
            message.append({
                "role": "user",
                "content": prompt.PLAN_HISTORY_PROMPT.format(summary_info=summary_info),
            })

            llm = getattr(self.llm, model_config.model_source)
            plan = ""
            async for chunk in llm(message, model_config):
                if len(chunk.choices) > 0:
                    plan += chunk.choices[0].delta.content
                    yield ChatResponse(
                        conversation_id=self.conversation_id,
                        user_id=self.user_id,
                        type="plan",
                        content=chunk.choices[0].delta.content,
                    ).model_dump_json()

            self.last_blueprint_text = plan
            plan_prompt_final = f"BLUEPRINT：{plan}"
            old_plan_id = [item.id for item in history if item.type == "plan"]
            await delete_runtime_messages(self.is_sub_agent, old_plan_id)
            await save_message(
                AgentMessage(
                    user_id=self.user_id,
                    conversation_id=self.conversation_id,
                    type="plan",
                    role="user",
                    content=plan_prompt_final,
                    created_at=datetime.utcnow(),
                ),
                self.is_sub_agent,
                self.session_id,
            )
            conv = await get_conversation_by_id(self.conversation_id)
            if conv:
                conv.action_blueprint = plan
                conv.updated_at = datetime.utcnow()
                await conv.save()
            print("action_blueprint:", plan)

        except Exception as e:
            self.last_blueprint_text = ""
            yield ChatResponse(
                conversation_id=self.conversation_id,
                user_id=self.user_id,
                type="plan",
                content="",
            ).model_dump_json()
            print(f"Blueprint Error: {e}")

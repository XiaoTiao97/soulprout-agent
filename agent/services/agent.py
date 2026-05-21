from agent.utils.llm import LLM
from agent.core.config import Config
from agent.api.models.message import ChatResponse, Message, ModelConfig, ChatRequest, FileMessage
from agent.api.models.agent_card import AgentCard
from agent.database.models.message import AgentMessage, SubAgentMessage
from agent.database.models.conversation import Conversation, SubAgentConversation
from agent.database.crud.message import (
    create_message,
    create_sub_agent_message,
    delete_messages_by_ids,
    delete_sub_agent_messages_by_ids,
    get_message_by_conv_id,
    get_sub_agent_message_by_conv_id_name,
    save_message,
    get_runtime_history,
    delete_runtime_messages
)
from agent.database.crud.conversation import (
    create_conversation,
    create_sub_agent_conversation,
    get_conversation_by_id,
    get_sub_agent_conversation,
    update_conversation_by_conv_for_tools_and_kb,
    update_sub_agent_conversation,
)
from agent.database.models.user import UserInfo
from agent.skill.manager import load_skill_to_workspace
from agent.tool.tools import ToolExecutor
from agent.services import prompt
from agent.services.blueprint import Blueprint
from agent.services.compress import Compress
from agent.services.memory import Memory
from uuid import uuid4
from datetime import datetime
import json
import asyncio
import aioshutil
import re
import os
import aiofiles
import aiofiles.os
from pathlib import Path

class Chat:
    def __init__(self, request):
        self.config = Config()
        self.local_file_path = self.config.local_file_path
        self.tool_executor = ToolExecutor(self.config)
        self.llm = LLM(self.config)

        self.messages = []
        self.user_id = request.user_id
        self.conversation_id = request.conversation_id
        self.input_text = request.message
        self.input_message_id = getattr(request, 'input_message_id', None)
        self.is_sub_agent = getattr(request, "is_sub_agent", False)
        self.model_source = request.model_source
        self.model = request.model
        self.tools_use = request.tools_use
        self.skills_use = request.skills_use if request.skills_use else False
        self.kb_use = request.kb_use
        self.agent_use = request.agent_use
        self.agent_id = request.agent_id
        self.select_agents = request.agent_id if self.agent_use == "select-agent" else []
        self.session_id = getattr(request, "session_id", None) or str(uuid4())[:4]
        self.temp_file_path = request.temp_file_path
        self.file_name_list = request.file_name_list

        self.time_now = f"""{datetime.now().strftime("%Y-%m-%d %H:%M:%S")} {datetime.now().strftime("%A")}"""
        self.capabilities_prompt = prompt.CAPABILITIES_PROMPT
        self.agent_info = os.getenv("AGENT_INFO", prompt.AGENT_INFO)
        self.system_prompt = f"""{self.agent_info}\n{self.capabilities_prompt}\nCurrent time:{self.time_now}\n"""

        self.model_config = None
        self.agent_name = None
        self.agent_card = None
        self.sub_agents = []
        self.picture_base64_result = []
        self.agents_dict = {}
        self.total_tokens = 0
        self.round_limit = 200
        self.soulprout_tools = [
            "read",
            "write",
            "edit",
            "read_picture",
            "bash",
            "skills",
            "web_search",
            "web_fetch",
            "soulprout_kb_tool",
            "call_sub_agent",
            "user_option",
        ]

    async def mcp_list_tools(self):
        return self.tool_executor.list_tools()

    async def mcp_call_tool(self, name, arguments):
        return await self.tool_executor.call_tool(name=name, arguments=arguments)

    async def save_message(self, data):
        return await save_message(data, self.is_sub_agent, self.session_id)

    async def get_runtime_history(self):
        return await get_runtime_history(self.is_sub_agent, self.session_id, self.conversation_id)

    async def delete_runtime_messages(self, message_ids):
        return await delete_runtime_messages(self.is_sub_agent, message_ids)

    # llm_stream/大模型流式输出
    async def llm_stream(self, messages, model_config):
        tool_call = False
        tool_message = Message(role="assistant")
        file_tool_message = FileMessage(role="file")
        tool_id = -1
        llm = getattr(self.llm, model_config.model_source)
        think=False
        function_name = None
        arguments_total = ""
        update_file_match = False
        correct_file_match = False
        past_text_match = False
        past_text = ""
        file_name = ""
        file_stop = False
        async for chunk in llm(messages, model_config):
            if len(chunk.choices) == 0:
                self.total_tokens = chunk.usage.total_tokens if hasattr(chunk, 'usage') and chunk.usage else None
                print("tokens: ", self.total_tokens)
                continue
            delta = chunk.choices[0].delta

            if hasattr(delta, "reasoning_content") and delta.reasoning_content:
                content = delta.reasoning_content
                yield Message(role="assistant", reasoning_content=content)

            # compatible/兼容 with reasoning_datails
            elif hasattr(delta, "reasoning_details") and delta.reasoning_details:
                reasoning_details = delta.reasoning_details
                for detail in reasoning_details:
                    if "text" in detail:
                        reasoning_content = detail["text"]
                        yield Message(role="assistant", reasoning_content=reasoning_content)

            # compatible/兼容 with <think>
            elif (isinstance(delta.content, str) and "<think>" in delta.content) or think:
                content = delta.content
                think = True
                if "</think>" in content:
                    think = False
                    content = content.replace("</think>", "")
                if "<think>" in content:
                    content = content.replace("<think>", "")
                yield Message(role="assistant", reasoning_content=content)

            elif isinstance(delta.tool_calls, list):
                tool_call = True
                function = delta.tool_calls[0].function
                # compatible/兼容 with tool_calls totally output
                if function and function.name and function.arguments:
                    tool_message.tool_calls = [delta.tool_calls[0]]
                    function_name = function.name
                    if function_name in ["read", "write", "edit"]:
                        file_tool_message.type = function_name
                        file_stop = True
                        # file_tool_message.json_table = json.loads(function.arguments)
                    continue
                if function and function.name:
                    update_file_match = False
                    correct_file_match = False
                    past_text_match = False
                    file_name = ""
                    arguments_total = ""
                    past_text = ""
                    function_name = function.name
                    tool_id += 1
                    tool_message.tool_calls = [] if not tool_message.tool_calls else tool_message.tool_calls
                    tool_message.tool_calls.append(delta.tool_calls[0])

                    if function_name in ["read", "write", "edit"]:
                        file_tool_message.type = function_name
                        file_stop = True
                if function and function.arguments:
                    tool_message.tool_calls[tool_id].function.arguments += function.arguments

                    if function_name in ["read", "write", "edit"]:
                        pattern_file_path = r'"file_path":\s*"([^"]*)"\s*,'
                        arguments_total += function.arguments
                        if function_name == "write":
                            if not update_file_match:
                                pattern = r'\{"file_path":\s*"([^"]*)"\s*,\s*"content":\s*"'
                                match = re.search(pattern, arguments_total)
                                if match:
                                    update_file_match = True
                                    match_file_path = re.search(pattern_file_path, arguments_total)
                                    if match_file_path:
                                        print(f"file_path匹配结果: {match_file_path.group(1)}")
                                        file_name = match_file_path.group(1)
                            else:
                                file_tool_message.json_table = {"file_path": file_name, "content": function.arguments}
                                yield file_tool_message
                        elif function_name == "edit":
                            if not correct_file_match:
                                pattern = r'\{"file_path":\s*"([^"]*)"\s*,\s*"past_text":\s*"'
                                match = re.search(pattern, arguments_total)
                                if match:
                                    correct_file_match = True
                                    match_file_path = re.search(pattern_file_path, arguments_total)
                                    if match_file_path:
                                        print(f"file_path匹配结果: {match_file_path.group(1)}")
                                        file_name = match_file_path.group(1)
                            elif not past_text_match:
                                past_text += function.arguments
                                pattern = r'^(.*?)"\s*,\s*"replace_text":\s*"'
                                match_past_text = re.search(pattern, past_text, re.DOTALL)
                                if match_past_text:
                                    past_text_match = True
                                    past_text = match_past_text.group(1)
                                    print(f"past_text匹配结果: {match_past_text.group(1)}")
                                    file_tool_message.json_table = {"file_path": file_name, "past_text": past_text}
                                    yield file_tool_message
                            else:
                                file_tool_message.json_table = {"file_path": file_name, "replace_text": function.arguments}
                                yield file_tool_message

            elif isinstance(delta.content, str):
                content = delta.content
                yield Message(role="assistant", content=content)

        if function_name == "read":
            file_tool_message.type = function_name
            try:
                file_tool_message.json_table = json.loads(arguments_total)
                yield file_tool_message
            except Exception as e:
                print("file_tool_message_json_error: ", e)
                pass
        if file_stop:
            file_tool_message.json_table = {"file_stop": "true"}
            yield file_tool_message
        if tool_call:
            yield tool_message

    async def _summary_history(self, input_text, history_list):
        history_summarize_info = ""
        for per_history in history_list:
            if per_history['role'] == 'user':
                user_message = per_history['content']
                history_summarize_info += f"USER：{user_message}\n"
            elif per_history['role'] == 'assistant':
                assistant_message = per_history['content']
                history_summarize_info += f"ASSISTANT：{assistant_message}\n" if assistant_message else ""
        history_summarize_info += f"USER：{input_text}\n\n"
        return history_summarize_info

    async def get_history(self):
        history = await self.get_runtime_history()
        history_list = [
            {
                'role': item.role,
                'content': item.content,
                **({'reasoning_content': item.reasoning_content} if hasattr(item, 'reasoning_content') and item.reasoning_content is not None else {}),
                **({'tool_calls': item.tool_calls} if hasattr(item, 'tool_calls') and item.tool_calls is not None else {}),
                **({'tool_call_id': item.tool_call_id} if hasattr(item, 'tool_call_id') and item.tool_call_id is not None else {})
            }
            for item in history if item.role != "agent"
        ]
        return history_list

    async def get_abstract(self):
        abstract_model_source = self.config.abstract_model_source + "_no_stream"
        try:
            model_config = ModelConfig(model_source=abstract_model_source, model=self.config.abstract_model, tools=[], stream=False)
            message=[{"role": "system", "content": prompt.ABSTRACT_SYSTEM_PROMPT}]
            message.append({"role": "user", "content": prompt.ABSTRACT_USER_PROMPT.format(input_text=self.input_text)})
            llm = getattr(self.llm, model_config.model_source)
            abstract = await llm(message, model_config)
            print(abstract)
        except Exception as e:
            abstract = self.input_text[0:12]
            print(f"Abstract Error: {e}")
        return abstract

    async def get_kb_prompt(self):
        kb_query = {"user_id": self.user_id, "kb_id": {"$in": self.kb_use}}
        result = self.config.db_libraries.find(kb_query)
        result_total = ""
        async for res in result:
            res_total = {"kb_id": res.get("kb_id"), "kb_name_zh": res.get("kb_name_zh"), "kb_description": res.get("kb_description")}
            result_total += str(res_total)+"\n"
        kb_prompt = prompt.KB_PROMPT.format(result_total=result_total)
        print("kb_prompt: ", kb_prompt)
        return kb_prompt

    def _build_blueprint(self):
        return Blueprint(
            config=self.config,
            is_sub_agent=self.is_sub_agent,
            session_id=self.session_id,
            user_id=self.user_id,
            conversation_id=self.conversation_id,
            input_text=self.input_text,
            kb_use=self.kb_use,
            time_now=self.time_now,
            soulprout_tools=self.soulprout_tools,
            tool_executor=self.tool_executor,
        )

    async def agent_files_process(self):
        """递归复制，跳过已存在的"""
        source_folder = os.path.join(self.config.agent_file_path, self.agent_id)
        target_folder = os.path.join(self.local_file_path, self.conversation_id)
        src_path = Path(source_folder)
        dst_path = Path(target_folder)

        # 收集所有文件
        file_list = []
        for root, dirs, files in os.walk(source_folder):
            for file in files:
                src_file = Path(root) / file
                rel_path = src_file.relative_to(src_path)
                dst_file = dst_path / rel_path
                file_list.append((src_file, dst_file))

        print(f"找到 {len(file_list)} 个文件")

        # 定义单个文件的复制任务
        async def copy_one(src, dst):
            try:
                # 检查目标是否存在
                if await aiofiles.os.path.exists(dst):
                    # 比较文件大小
                    src_stat = await aiofiles.os.stat(src)
                    dst_stat = await aiofiles.os.stat(dst)

                    if src_stat.st_size == dst_stat.st_size:
                        return True  # 已存在，跳过
            except FileNotFoundError:
                pass

            # 执行复制
            try:
                await aiofiles.os.makedirs(dst.parent, exist_ok=True)
                async with aiofiles.open(src, 'rb') as f_src:
                    async with aiofiles.open(dst, 'wb') as f_dst:
                        while chunk := await f_src.read(8192):
                            await f_dst.write(chunk)
                print(f"已复制: {src}")
                return True
            except Exception as e:
                print(f"失败: {src} - {e}")
                return False

        # 创建并执行所有任务
        tasks = [copy_one(src, dst) for src, dst in file_list]
        results = await asyncio.gather(*tasks)

        success = sum(1 for r in results if r)
        print(f"\n完成: {success}/{len(file_list)} 个文件处理成功")
        return success

    async def get_conversation_files(self):
        """异步获取文件夹内所有文件名"""
        folder_path = os.path.join(self.local_file_path, self.conversation_id)
        try:
            # 获取文件夹内所有条目
            entries = await aiofiles.os.listdir(folder_path)

            # 异步检查每个条目是否为文件
            file_names = []
            for entry in entries:
                full_path = Path(folder_path) / entry
                if await aiofiles.os.path.isfile(str(full_path)):
                    file_names.append(entry)

            return file_names

        except Exception as e:
            print(f"错误: {e}")
            return []

    async def check_folder_exists(self, target_name: str) -> bool:
        """
        检查是否存在以 target_name 命名的文件夹

        Args:
            target_name: 要查找的文件夹名，如 "skill-creator"

        Returns:
            bool: 存在返回 True，否则 False
        """
        folder_path = os.path.join(self.local_file_path, self.conversation_id)

        try:
            entries = await aiofiles.os.listdir(folder_path)

            for entry in entries:
                full_path = Path(folder_path) / entry

                # 检查：是文件夹 且 名称匹配
                if await aiofiles.os.path.isdir(str(full_path)):
                    if entry == target_name:
                        return True

            return False

        except Exception as e:
            print(f"检查文件夹错误: {e}")
            return False

    async def expert_load_skills(self, skills):
        """
        POST /skill - 加载技能到会话工作区

        Args:
            conversation_id: 会话 ID
            user_id: 用户 ID
            skills: {"system": ["skill1", "skill2"], "user": ["my-skill"]}

        Returns:
            {"success": True, "data": "加载skills成功", "mode": "rag"}
        """

        skills_list = []

        # 检测是否已存在skill文件夹
        load_skill_bool = False
        if skills and skills.get("system"):
            for skill_name in skills["system"]:
                skills_list.append(skill_name)
                result = await self.check_folder_exists(skill_name)
                if not result:
                    load_skill_bool = True
        if skills and skills.get("user"):
            for skill_name in skills["user"]:
                skills_list.append(skill_name)
                result = await self.check_folder_exists(skill_name)
                if not result:
                    load_skill_bool = True

        # 若不存在则加载skill
        if skills and load_skill_bool:
            result = await load_skill_to_workspace(
                conversation_id=self.conversation_id,
                user_id=self.user_id,
                skills=skills,
                workspace_base=self.config.local_file_path,
            )
            if result.get("success"):
                print(f"✅ 加载技能成功: {result.get('data')}")
                return result
            raise Exception(f"加载失败: {result.get('error')}")
        else:
            print("无技能或技能已加载")

        return skills_list

    async def expert_agent_init_process(self):
        agent_card = self.agent_card
        # 处理agent的文件库，将agent文件库导入当前conversation_id下
        agent_files_list = agent_card.files
        conversation_file_list = await self.get_conversation_files()
        agent_files_process = False
        if len(agent_files_list) > 0:
            for agent_file in agent_files_list:
                if agent_file not in conversation_file_list:
                    agent_files_process = True
        if agent_files_process:
            await self.agent_files_process()

        self.system_prompt = agent_card.system_prompt
        self.system_prompt += f"\nCurrent Time: {self.time_now}"
        tools_use_list = list(agent_card.tools or [])

        if agent_card.agents:
            sub_agent_name_list = []
            agent_id_list = agent_card.agents
            for agent_id in agent_id_list:
                sub_agent_card = await self.config.db_agent_card.find_one({"agent_id": agent_id})
                sub_agent_card = AgentCard(**sub_agent_card)
                sub_agent_name = sub_agent_card.name
                sub_agent_name_list.append(sub_agent_name)
                self.agents_dict[sub_agent_name] = agent_id
            self.sub_agents = sub_agent_name_list
            if "call_sub_agent" not in tools_use_list:
                tools_use_list.append("call_sub_agent")

        skills_use_dict = agent_card.skills
        skills_list = await self.expert_load_skills(skills_use_dict) if skills_use_dict else []
        self.system_prompt += f"\nThe following skills has been loaded to workspace: {skills_list}" if skills_use_dict else ""
        self.model_source = agent_card.model_source
        self.model = agent_card.model
        self.kb_use = agent_card.kbs

        tools = await self.mcp_list_tools()
        tools_use_final = [tool for tool in tools if tool.get("function").get("name") in tools_use_list]
        if len(tools_use_final) > 0:
            # TODO 核实这个tools_use是否有必要
            self.tools_use = True
        return tools_use_final

    async def soulprout_agent_process(self):
        """
        Soulprout 模式：
        - 强制 conversation_id = user_id（每个用户唯一的 Soulprout 会话），不存在则先建一条
        - 模型从环境变量 SOULPROUT_MODEL / SOULPROUT_MODEL_SOURCE 读取，忽略前端传入
        - 拉取当前 user 的 userinfo / agentinfo
        - 以 USERINFO: 和 AGENTINFO: 为前缀拼入 system_prompt
        - 若 DB 中 agentinfo 已设置，则把它放到 AGENTINFO 段的开头；
          否则用 AGENT_INFO_PERSONA_REMINDER 提醒用户可以个性化自己的 Soulprout
        - 工具集仅暴露 soulprout_tools
        """
        self.conversation_id = self.user_id
        self.model_source = self.config.soulprout_model_source
        self.model = self.config.soulprout_model

        existing_conversation = await get_conversation_by_id(self.conversation_id)
        if existing_conversation is None:
            await create_conversation(Conversation(
                user_id=self.user_id,
                conversation_id=self.conversation_id,
                abstract="Soulprout",
                tools_use=self.tools_use,
                skills_use=self.skills_use,
                kb_use=self.kb_use or [],
                agent_use=self.agent_use,
                agent_id=self.agent_id,
                agent_name=self.agent_name,
                model_source=self.model_source,
                model=self.model,
            ))

        userinfo_text = ""
        agentinfo_text = ""
        try:
            user = await UserInfo.find_one(UserInfo.user_id == self.user_id)
            if user:
                userinfo_text = (getattr(user, "userinfo", "") or "").strip()
                agentinfo_text = (getattr(user, "agentinfo", "") or "").strip()
        except Exception as e:
            print(f"加载 UserInfo 失败：{e}")

        userinfo_section = f"USERINFO: {userinfo_text}" if userinfo_text else "USERINFO: (empty)"
        if agentinfo_text:
            agentinfo_section = f"AGENTINFO: {agentinfo_text}\n\n{prompt.AGENT_INFO}"
        else:
            agentinfo_section = f"AGENTINFO: {prompt.AGENT_INFO_PERSONA_REMINDER}\n\n{prompt.AGENT_INFO}"

        self.system_prompt = (
            f"{userinfo_section}\n\n"
            f"{agentinfo_section}\n"
            f"{self.capabilities_prompt}\n"
            f"Current time:{self.time_now}\n"
        )

        tools = await self.mcp_list_tools()
        tools_use_final = [
            tool for tool in tools
            if tool.get("function", {}).get("name") in self.soulprout_tools
        ]
        if len(tools_use_final) > 0:
            self.tools_use = True
        return tools_use_final

    async def select_agent_process(self):
        tools = await self.mcp_list_tools()
        tools_use_final = []
        agent_name_list = []
        for agent_id in self.agent_id:
            agent_card = await self.config.db_agent_card.find_one({"agent_id": agent_id})
            agent_card = AgentCard(**agent_card)
            agent_name_list.append(agent_card.name)
        self.sub_agents = agent_name_list
        for tool in tools:
            tname = tool.get("function", {}).get("name")
            if tname in ("call_sub_agent", "soulprout_kb_agent", "soulprout_kb_tool"):
                tools_use_final.append(tool)
        if len(tools_use_final) > 0:
            self.tools_use = True
        return tools_use_final

    async def multi_agent_call(self, name, arguments):
        target_name = name
        module = arguments.get("module")
        if name == "call_sub_agent":
            target_name = arguments.get("name")
            if module and module != "exist":
                error_resp = ChatResponse(
                    conversation_id=self.conversation_id,
                    user_id=self.user_id,
                    type="error",
                    content="call_sub_agent 当前仅支持 module=exist"
                ).model_dump_json()
                yield error_resp
                return
            if not target_name:
                error_resp = ChatResponse(
                    conversation_id=self.conversation_id,
                    user_id=self.user_id,
                    type="error",
                    content="call_sub_agent 缺少 name 参数"
                ).model_dump_json()
                yield error_resp
                return
        purpose = arguments.get("purpose")
        sid = arguments.get("session_id")
        session_id = sid if sid and len(sid) == 4 else None
        print("arguments: ", arguments)
        print("session_id: ", session_id)
        target_agent_id = None
        if self.agents_dict:
            target_agent_id = self.agents_dict.get(target_name)
        if not target_agent_id and target_name:
            target_card = await self.config.db_agent_card.find_one({"name": target_name})
            target_agent_id = target_card.get("agent_id") if target_card else None
        if not target_agent_id:
            error_resp = ChatResponse(
                conversation_id=self.conversation_id,
                user_id=self.user_id,
                type="error",
                content=f"未找到子智能体: {target_name}"
            ).model_dump_json()
            yield error_resp
            return
        chat_request_data = ChatRequest(
            model_source=self.model_source,
            model=self.model,
            agent_id=target_agent_id,
            message=purpose,
            kb_use=self.kb_use,
            conversation_id=self.conversation_id,
            user_id=self.user_id,
            session_id=session_id,
            is_sub_agent=True,
            agent_use="expert-agent",
        )
        print(f"Sending request: {chat_request_data}")
        sub_chat = Chat(chat_request_data)
        async for chunk in sub_chat.run():
            yield chunk

    async def process_single_agent(self, name, arguments, message, tool_id):
        result_agent = ""
        result_multi = ""
        agent_session_id = ""
        agent_display_name = arguments.get("name") if name == "call_sub_agent" else name
        try:
            async for result in self.multi_agent_call(name=name, arguments=arguments):
                result_tool = ChatResponse(**json.loads(result))
                if result_tool.type == "error":
                    result_agent = f"子智能体{agent_display_name}调用失败，请检查问题后重试"
                    yield result_tool.model_dump_json()
                    break
                if (result_tool.type == "agent_for_frontend" or result_tool.type == "get_tools") and (
                        len(result_agent) > 0 or len(result_multi) > 0):
                    result_message = result_agent if len(result_agent) > 0 else result_multi
                    await self.save_message(
                        AgentMessage(user_id=self.user_id, conversation_id=self.conversation_id, type="text",
                                     role="agent", content=result_message,
                                     tool_calls=[message.tool_calls[tool_id].model_dump()],
                                     tool_call_id=message.tool_calls[tool_id].id, created_at=datetime.utcnow()))
                    result_agent = ""
                    result_multi = ""

                if result_tool.type == "agent_for_frontend":
                    await self.save_message(AgentMessage(user_id=self.user_id, conversation_id=self.conversation_id,
                                                      type="agent_for_frontend", role="agent",
                                                      content=result_tool.content,
                                                      tool_call_id=message.tool_calls[tool_id].id,
                                                      created_at=datetime.utcnow()))
                elif result_tool.type == "agent_session_id":
                    agent_session_id = result_tool.content
                elif result_tool.type == "get_tools":
                    await self.save_message(
                        AgentMessage(user_id=self.user_id, conversation_id=self.conversation_id, type="get_tools",
                                     role="agent", content="", tool_call_id=message.tool_calls[tool_id].id,
                                     tool_calls=result_tool.tool_calls, created_at=datetime.utcnow()))
                elif result_tool.role == "agent" and result_tool.type != "tool":
                    result_multi += result_tool.content
                elif result_tool.role == "assistant" and result_tool.type != "reasoner_content":
                    result_agent += result_tool.content
                result_tool.role = "agent"
                result_tool.tool_call_id = message.tool_calls[tool_id].id
                yield result_tool.model_dump_json()
        except Exception as e:
            result_agent = f"调用子智能体失败，失败原因：{e}，请重试。"

        self.messages.append({"role": "tool", "content": result_agent, "tool_call_id": message.tool_calls[tool_id].id})
        result_message = agent_session_id + '\n' + result_agent
        await self.save_message(
            AgentMessage(user_id=self.user_id, conversation_id=self.conversation_id, type="agent",
                         role="tool", content=result_message,
                         tool_call_id=message.tool_calls[tool_id].id, created_at=datetime.utcnow()))

    async def process_single_tool(self, name, arguments, message, tool_id):
        if name == "read_picture":
            result = await self.mcp_call_tool(name=name, arguments=arguments)
            if result.get("ok") and result.get("base64"):
                self.picture_base64_result.append(result.get("base64"))
                content = result.get("message", "成功读取图片")
            elif not ("doubao" in self.model or "kimi" in self.model):
                content = f"{self.model}不支持阅读图片"
            else:
                content = result.get("message", "路径不存在")
            self.messages.append({"role": "tool", "content": content, "tool_call_id": message.tool_calls[tool_id].id})
            yield ChatResponse(conversation_id=self.conversation_id, user_id=self.user_id, type="tool", role="tool", content=content, tool_call_id=message.tool_calls[tool_id].id).model_dump_json()
            await self.save_message(AgentMessage(user_id=self.user_id, conversation_id=self.conversation_id, type="tool", role="tool", content=content, tool_call_id=message.tool_calls[tool_id].id, created_at=datetime.utcnow()))
        elif name == "get_action_blueprint":
            blueprint = self._build_blueprint()
            async for chunk in blueprint.stream_action_blueprint():
                yield chunk
            content = (blueprint.last_blueprint_text or "").strip()
            if not content:
                content = "Blueprint generation produced no content."
            self.messages.append({"role": "tool", "content": content, "tool_call_id": message.tool_calls[tool_id].id})
            yield ChatResponse(conversation_id=self.conversation_id, user_id=self.user_id, type="tool", role="tool", content=content, tool_call_id=message.tool_calls[tool_id].id).model_dump_json()
            await self.save_message(AgentMessage(user_id=self.user_id, conversation_id=self.conversation_id, type="tool", role="tool", content=content, tool_call_id=message.tool_calls[tool_id].id, created_at=datetime.utcnow()))
        else:
            result = await self.mcp_call_tool(name=name, arguments=arguments)

            # 工具信息压缩
            result_message = str(result)
            if len(result_message) > 50000:
                result_message = result_message[:50000] + "<工具结果过长，已进行截断>"

            self.messages.append({"role": "tool", "content": result_message, "tool_call_id": message.tool_calls[tool_id].id})
            yield ChatResponse(conversation_id=self.conversation_id, user_id=self.user_id, type="tool", role="tool",
                               content=result_message, tool_call_id=message.tool_calls[tool_id].id).model_dump_json()
            await self.save_message(
                AgentMessage(user_id=self.user_id, conversation_id=self.conversation_id, type="tool",
                             role="tool", content=result_message, tool_call_id=message.tool_calls[tool_id].id,
                             created_at=datetime.utcnow()))

    async def merge_async_generators(self, generators):
        """
        并行处理多个异步生成器，按照结果产生的顺序实时返回
        """
        # 创建任务队列
        pending = {asyncio.create_task(anext(gen, None)): gen for gen in generators}

        while pending:
            # 等待任何一个任务完成
            done, _ = await asyncio.wait(
                pending.keys(), return_when=asyncio.FIRST_COMPLETED
            )

            for task in done:
                gen = pending.pop(task)
                try:
                    result = task.result()
                    if result is not None:
                        # 返回结果
                        yield result
                        # 创建新任务继续处理该生成器
                        pending[asyncio.create_task(anext(gen, None))] = gen
                except StopAsyncIteration:
                    # 该生成器已经处理完毕
                    pass
                except Exception as e:
                    print(f"处理生成器时出错: {e}")

    async def agents_and_tools_call(self, message, name_list, arguments_list):
        tasks = [self.process_single_agent(name, arguments_list[i], message, i) if name in ("soulprout_kb_agent", "call_sub_agent") else self.process_single_tool(name, arguments_list[i], message, i) for i, name in enumerate(name_list)]

        # 并行处理所有生成器，实时产生结果
        async for result in self.merge_async_generators(tasks):
            yield result
        # 处理所有读取图片的情况
        if len(self.picture_base64_result) > 0:
            for picture_base64 in self.picture_base64_result:
                self.messages.append({"role": "user", "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{picture_base64}"}}
                ]})
                await self.save_message(AgentMessage(user_id=self.user_id, conversation_id=self.conversation_id,type="text", role="user", content=[{"type": "image_url", "image_url":{"url": f"data:image/png;base64,{picture_base64}"}}], created_at=datetime.utcnow()))
        self.picture_base64_result = []

    async def remove_temp_files(self):
        # 获取源
        source_dir = self.temp_file_path
        final_dir = f"/home/soulprout_data/{self.conversation_id}"

        await aioshutil.copytree(source_dir, final_dir)

        # 删除源目录
        await aioshutil.rmtree(source_dir)
        print("已移动临时文件，删除临时目录")

    async def compress_process(self):
        compress = Compress(self.config, self.is_sub_agent, self.session_id, self.user_id, self.conversation_id, self.model)
        return await compress.run()

    async def recall_memory_process(self):
        memory = Memory(self.config, self.is_sub_agent, self.session_id, self.user_id, self.conversation_id, self.input_text)
        return await memory.recall()

    async def history_check(self):
        history = await self.get_runtime_history()
        del_id_list = []
        tool_calls_num = 0
        for message in history:
            if message.role != "agent":
                if message.tool_calls:
                    del_id_list = []
                    tool_calls_num = len(message.tool_calls)
                    del_id_list.append(message.id)
                elif len(del_id_list) > 0:
                    if message.role == "tool":
                        tool_calls_num -= 1
                        del_id_list.append(message.id)
                    elif message.role != "tool" and tool_calls_num != 0:
                        await self.delete_runtime_messages(del_id_list)
                        del_id_list = []
                        tool_calls_num = 0
                    else:
                        del_id_list = []
                        tool_calls_num = 0

    async def edit_message_process(self):
        history = await get_message_by_conv_id(self.conversation_id)
        del_id_list = []
        if_del = False
        for message in history:
            print(message.id, self.input_message_id)
            if str(message.id) == self.input_message_id:
                if_del = True
            if if_del:
                del_id_list.append(message.id)
        print(del_id_list)
        await delete_messages_by_ids(del_id_list)

    async def sub_agent_process(self):
        if self.agent_id == "soulprout_kb_agent":
            self.agent_card = self.config.kb_agent_card()
            preserve_kb_use = self.kb_use
        else:
            agent_card = await self.config.db_agent_card.find_one({"agent_id": self.agent_id})
            if not agent_card:
                raise ValueError(f"子智能体不存在或已删除: agent_id={self.agent_id}")
            self.agent_card = AgentCard(**agent_card)
            preserve_kb_use = None

        agent_card = self.agent_card
        agent_files_list = agent_card.files or []
        conversation_file_list = await self.get_conversation_files()
        agent_files_process = any(agent_file not in conversation_file_list for agent_file in agent_files_list)
        if agent_files_process:
            await self.agent_files_process()

        self.agent_name = agent_card.name_zh if agent_card.name_zh else agent_card.name
        self.system_prompt = agent_card.system_prompt
        self.system_prompt += f"\n当前时间：{self.time_now}"
        skills_use_dict = agent_card.skills
        skills_list = await self.expert_load_skills(skills_use_dict) if skills_use_dict else []
        self.system_prompt += f"\n已加载以下skills至工作区: {skills_list}" if skills_use_dict else ""
        self.model_source = agent_card.model_source
        self.model = agent_card.model
        self.kb_use = preserve_kb_use if preserve_kb_use is not None else agent_card.kbs

        tools_use_final = []
        tools = await self.mcp_list_tools()
        tools_use_list = agent_card.tools or []
        for tool in tools:
            tool_name = tool.get("function").get("name")
            if tool_name in tools_use_list:
                tools_use_final.append(tool)
            elif tool_name in ["soulprout_kb_tool", "kb_chunk_abstract", "chunk_content"] and len(self.kb_use) > 0:
                tools_use_final.append(tool)
        if len(tools_use_final) > 0:
            self.tools_use = True
        return tools_use_final

    async def ensure_sub_agent_conversation(self):
        conversation = await get_sub_agent_conversation(self.conversation_id, self.session_id)
        if conversation:
            return await update_sub_agent_conversation(
                conversation_id=self.conversation_id,
                session_id=self.session_id,
                tools_use=self.tools_use,
                kb_use=self.kb_use,
                model_source=self.model_source,
                model=self.model,
                update_at=datetime.utcnow(),
            )
        return await create_sub_agent_conversation(SubAgentConversation(
            user_id=self.user_id,
            conversation_id=self.conversation_id,
            session_id=self.session_id,
            agent_id=self.agent_id,
            agent_name=self.agent_name or "",
            abstract=self.input_text[:12],
            tools_use=self.tools_use,
            kb_use=self.kb_use,
            model_source=self.model_source,
            model=self.model,
        ))

    async def run_sub_agent(self):
        tools = await self.sub_agent_process()
        self.system_prompt += await self.get_kb_prompt() if len(self.kb_use) > 0 else ""
        tool_name_list = [tool.get("function").get("name") for tool in tools]
        print(f"子智能体加载tools数量：{len(tools)}，加载的tool:{tool_name_list}")

        await self.ensure_sub_agent_conversation()
        self.model_config = ModelConfig(model_source=self.model_source, model=self.model, tools=tools, stream=True)
        await self.save_message(AgentMessage(user_id=self.user_id, conversation_id=self.conversation_id, type="text", role="user", content=self.input_text, created_at=datetime.utcnow()))
        yield ChatResponse(conversation_id=self.conversation_id, user_id=self.user_id, type="agent_for_frontend", role="agent", content=self.agent_name).model_dump_json()
        yield ChatResponse(conversation_id=self.conversation_id, user_id=self.user_id, type="agent_session_id", content=f"当前子智能体session_id={self.session_id}").model_dump_json()

        finish = False
        while finish is False:
            self.round_limit -= 1
            message_total = ""
            reasoning_content_total = ""
            await self.history_check()
            memory_process_result = await self.compress_process()
            history = await self.get_history()
            history.insert(0, {"role": "system", "content": self.system_prompt})
            if self.agent_card and self.agent_card.supervisor_history:
                main_history = await get_message_by_conv_id(self.conversation_id)
                main_history_list = [{"role": item.role, "content": item.content} for item in main_history if item.role != "agent"]
                summary_info = await self._summary_history("", main_history_list)
                history.insert(1, {"role": "user", "content": f"用户之前的主智能体对话：{summary_info}"})
            self.messages = history

            if not memory_process_result:
                yield ChatResponse(conversation_id=self.conversation_id, user_id=self.user_id, type="error", content="上下文压缩失败").model_dump_json()
            if self.round_limit < 0:
                yield ChatResponse(conversation_id=self.conversation_id, user_id=self.user_id, type="error", content="已达到Agent最大轮次限制，识别到可能陷入无限循环，中断回复").model_dump_json()
                break

            async for message in self.llm_stream(self.messages, self.model_config):
                if message.role == "assistant" and message.tool_calls:
                    self.messages.append(message.__dict__)
                    message_save = {
                        "user_id": self.user_id,
                        "conversation_id": self.conversation_id,
                        "type": "get_tools",
                        "role": "assistant",
                        "content": "",
                        "created_at": datetime.utcnow(),
                    }
                    message_save["tool_calls"] = [
                        tool_call.model_dump() if hasattr(tool_call, "model_dump")
                        else (
                            tool_call.dict() if hasattr(tool_call, "dict")
                            else dict(tool_call) if isinstance(tool_call, dict)
                            else str(tool_call)
                        )
                        for tool_call in message.tool_calls
                    ] if message.tool_calls else None
                    if len(message_total) > 0:
                        self.messages[-1]["content"] = message_total
                        message_save["content"] = message_total
                        message_total = ""
                    if len(reasoning_content_total) > 0:
                        self.messages[-1]["reasoning_content"] = reasoning_content_total
                        message_save["reasoning_content"] = reasoning_content_total
                        reasoning_content_total = ""
                    await self.save_message(AgentMessage(**message_save))
                    yield ChatResponse(**message_save).model_dump_json()
                    try:
                        name_list = [tool_call.function.name for tool_call in message.tool_calls]
                        arguments_list = [json.loads(tool_call.function.arguments) for tool_call in message.tool_calls]
                        for arguments in arguments_list:
                            arguments["conversation_id"] = self.conversation_id
                        async for agents_and_tools_response in self.agents_and_tools_call(message, name_list, arguments_list):
                            yield agents_and_tools_response
                    except Exception as e:
                        print(e)
                        content = "arguments解析错误，请分批次多次调用工具执行"
                        await self.save_message(AgentMessage(user_id=self.user_id, conversation_id=self.conversation_id, type="tool", role="tool", content=content, tool_call_id=message.tool_calls[0].id, created_at=datetime.utcnow()))
                        self.messages.append({"role": "tool", "content": content, "tool_call_id": message.tool_calls[0].id})
                        yield ChatResponse(conversation_id=self.conversation_id, user_id=self.user_id, type="tool", role="tool", content=content, tool_call_id=message.tool_calls[0].id).model_dump_json()
                elif message.role == "file":
                    yield ChatResponse(conversation_id=self.conversation_id, user_id=self.user_id, type=message.type, role="file", json_table=message.json_table).model_dump_json()
                elif message.content:
                    message_total += message.content
                    yield ChatResponse(conversation_id=self.conversation_id, user_id=self.user_id, type="text", content=message.content).model_dump_json()
                elif message.reasoning_content:
                    if isinstance(message.reasoning_content, str):
                        reasoning_content = message.reasoning_content
                        reasoning_content_total += reasoning_content
                    yield ChatResponse(conversation_id=self.conversation_id, user_id=self.user_id, type="reasoner_content", content=reasoning_content).model_dump_json()

            if len(message_total) > 0:
                finish = True
                await self.save_message(AgentMessage(user_id=self.user_id, conversation_id=self.conversation_id, type="text", role="assistant", content=message_total, reasoning_content=reasoning_content_total if len(reasoning_content_total) > 0 else None, created_at=datetime.utcnow()))

    async def conversation_init(self):
        if self.conversation_id == "":
            self.conversation_id = str(uuid4())
            abstract = await self.get_abstract()
            if self.temp_file_path:
                await self.remove_temp_files()
            await create_conversation(Conversation(user_id=self.user_id, conversation_id=self.conversation_id, abstract=abstract, tools_use=self.tools_use, skills_use=self.skills_use, kb_use=self.kb_use, agent_use=self.agent_use, agent_id=self.agent_id, agent_name=self.agent_name, model_source=self.model_source, model=self.model))
            return True, abstract
        else:
            await update_conversation_by_conv_for_tools_and_kb(conversation_id=self.conversation_id, tools_use=self.tools_use, skills_use=self.skills_use, kb_use=self.kb_use, agent_use=self.agent_use, agent_id=self.agent_id, agent_name=self.agent_name, model_source=self.model_source, model=self.model, update_at=datetime.utcnow())
            return False, None

    async def run(self):
        if self.is_sub_agent:
            async for chunk in self.run_sub_agent():
                yield chunk
            return

        # process edit
        if self.input_message_id:
            await self.edit_message_process()

        # Process expert pick
        if self.agent_use in ["expert-agent"]:
            tools = await self.expert_agent_init_process()
            if self.agent_id and isinstance(self.agent_id, str):
                agent_card = await self.config.db_agent_card.find_one({"agent_id": self.agent_id})
                self.agent_card = AgentCard(**agent_card)
                self.agent_name = self.agent_card.name_zh if self.agent_card.name_zh else self.agent_card.name

        # Soulprout 模式：注入 USERINFO / AGENTINFO 并使用 soulprout_tools
        elif self.agent_use == "soulprout":
            tools = await self.soulprout_agent_process()

        # 处理所有未选择智能体或多选智能体的情况
        else:
            if self.agent_use == "select-agent":
                # process multi-expert
                tools = await self.select_agent_process()
            else:
                tools = await self.mcp_list_tools()
                tools = tools if self.tools_use else []

        # process conversation_init
        conversation_init, abstract = await self.conversation_init()
        if conversation_init:
            yield ChatResponse(conversation_id=self.conversation_id, user_id=self.user_id, type="abstract", content=abstract).model_dump_json()

        # 对于知识库的系统提示词处理
        self.system_prompt += await self.get_kb_prompt() if len(self.kb_use) > 0 else ""
        print("system_prompt:", self.system_prompt)
        # 召回相关记忆（hybrid_search Top10 & score>=0.4 & 排除已加载），命中后写入 memory 类型消息
        await self.recall_memory_process()
        # 对于上传文件的User Input处理
        self.input_text += f"\n\nFILE: 上传文件 -> {self.file_name_list}" if len(self.file_name_list) > 0 else ""
        tool_name_list = [tool.get("function").get("name") for tool in tools]
        print(f"load tools:{tool_name_list}")

        self.model_config = ModelConfig(model_source=self.model_source, model=self.model, tools=tools, stream=True)
        print("model_source:", self.model_source, "model:", self.model)
        result = await self.save_message(AgentMessage(user_id=self.user_id, conversation_id=self.conversation_id, type="text", role="user", content=self.input_text, created_at=datetime.utcnow()))
        yield ChatResponse(conversation_id=self.conversation_id, user_id=self.user_id, type="input_message_id", content=str(result.id)).model_dump_json()

        finish = False
        while finish is False:
            self.round_limit -= 1
            message_total = ""
            reasoning_content_total = ""
            await self.history_check()
            memory_process_result = await self.compress_process()     # 上下文压缩（成功后内部会同步 memory_loaded）
            history = await self.get_history()
            history.insert(0, {"role": "system", "content": self.system_prompt})
            self.messages = history

            # 异常处理
            if not memory_process_result:
                yield ChatResponse(conversation_id=self.conversation_id, user_id=self.user_id, type="error", content=f"上下文压缩失败").model_dump_json()
            if self.round_limit < 0:
                yield ChatResponse(conversation_id=self.conversation_id, user_id=self.user_id, type="error", content=f"已达到Agent最大轮次限制，识别到可能陷入无限循环，中断回复").model_dump_json()
                break

            async for message in self.llm_stream(self.messages, self.model_config):
                if message.role == "assistant" and message.tool_calls:
                    self.messages.append(message.__dict__)
                    tool_calls_type = "get_agents" if message.tool_calls[0].function.name in ("soulprout_kb_agent", "call_sub_agent") else "get_tools"
                    message_save = {
                        "user_id": self.user_id,
                        "conversation_id": self.conversation_id,
                        "type": tool_calls_type,
                        "role": "assistant",
                        "content": "",
                        "created_at": datetime.utcnow()
                    }
                    if hasattr(message, 'tool_calls') and message.tool_calls:
                        message_save["tool_calls"] = [
                            tool_call.model_dump() if hasattr(tool_call, 'model_dump')
                            else (
                                tool_call.dict() if hasattr(tool_call, 'dict')
                                else dict(tool_call) if isinstance(tool_call, dict)
                                else str(tool_call)
                            )
                            for tool_call in message.tool_calls
                        ]
                    else:
                        message_save["tool_calls"] = None
                    if len(message_total) > 0:
                        self.messages[-1]["content"] = message_total
                        message_save["content"] = message_total
                        message_total = ""
                    if len(reasoning_content_total) > 0:
                        self.messages[-1]["reasoning_content"] = reasoning_content_total
                        message_save["reasoning_content"] = reasoning_content_total
                        reasoning_content_total = ""
                    await self.save_message(AgentMessage(**message_save))
                    yield ChatResponse(**message_save).model_dump_json()

                    try:
                        print(message.tool_calls)
                        name_list = [tool_call.function.name for tool_call in message.tool_calls]
                        arguments_list = [json.loads(tool_call.function.arguments) for tool_call in message.tool_calls]
                        for arguments in arguments_list:
                            arguments["conversation_id"] = self.conversation_id
                        # 处理multi-agents和tools逻辑
                        async for agents_and_tools_response in self.agents_and_tools_call(message, name_list, arguments_list):
                            yield agents_and_tools_response

                    # 工具报错的异常处理
                    except Exception as e:
                        yield ChatResponse(conversation_id=self.conversation_id, user_id=self.user_id, type="tool",
                                           role="tool", content=str(f"arguments解析错误，失败原因：{e}"),
                                           tool_call_id=message.tool_calls[0].id).model_dump_json()
                        await self.save_message(
                            AgentMessage(user_id=self.user_id, conversation_id=self.conversation_id, type="tool",
                                         role="tool", content=str(f"arguments解析错误，失败原因：{e}"),
                                         tool_call_id=message.tool_calls[0].id, created_at=datetime.utcnow()))
                        self.messages.append({"role": "tool", "content": f"arguments解析错误，失败原因：{e}", "tool_call_id": message.tool_calls[0].id})

                elif message.role == "file":
                    yield ChatResponse(conversation_id=self.conversation_id, user_id=self.user_id, type=message.type, role="file", json_table=message.json_table).model_dump_json()
                elif message.content:
                    message_total += message.content
                    yield ChatResponse(conversation_id=self.conversation_id, user_id=self.user_id, type="text", content=message.content).model_dump_json()

                elif message.reasoning_content:
                    if isinstance(message.reasoning_content, str):
                        reasoning_content = message.reasoning_content
                        reasoning_content_total += reasoning_content
                    yield ChatResponse(conversation_id=self.conversation_id, user_id=self.user_id, type="reasoner_content", content=reasoning_content).model_dump_json()

            if len(message_total) > 0:
                finish = True
                await self.save_message(AgentMessage(user_id=self.user_id, conversation_id=self.conversation_id, type="text", role="assistant", content=message_total, reasoning_content=reasoning_content_total if len(reasoning_content_total) > 0 else None, created_at=datetime.utcnow()))
TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "get_action_blueprint",
            "description": (
                "Invoke the consulting specialist to produce an action blueprint for the main agent (not end-user text). "
                "Use this when the user task is ambiguous, multi-step, constraint-heavy, or needs structured decomposition: "
                "situation analysis, real intent vs literal question, implicit dependencies, prioritized steps, and which "
                "Tools/Skills to use. Does not execute work—only returns guidance. For simple one-shot questions, answer "
                "directly without calling this tool."
            ),
            "parameters": {"type": "object", "required": [], "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read",
            "description": (
                "阅读工作区内的文件，可阅读的文件类型为 docx/doc/pdf/pptx/xlsx/txt/md/"
                "py/json/html 等。对纯文本/代码类文件支持按行分页读取（offset/limit），"
                "返回结果会带行号；对 pdf/doc(x)/ppt(x)/xlsx 等富文本/二进制文件走整体解析，"
                "offset/limit 不生效。"
            ),
            "parameters": {
                "type": "object",
                "required": ["file_path"],
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "相对于会话工作区的文件相对路径，如 dir/sub/xxx.txt",
                    },
                    "offset": {
                        "type": "integer",
                        "description": "开始读取的行号（1-indexed），默认 1，最小值 1",
                        "minimum": 1,
                    },
                    "limit": {
                        "type": "integer",
                        "description": "最大读取行数，默认 500，最大 2000",
                        "minimum": 1,
                        "maximum": 2000,
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write",
            "description": "在md/txt/py/json/html等文本文件写入内容，多次调用时则在末尾追加内容",
            "parameters": {
                "type": "object",
                "required": ["file_path", "content"],
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "相对于会话工作区的文件相对路径，如 dir/sub/xxx.txt",
                    },
                    "content": {"type": "string", "description": "需要在末尾追加的内容"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit",
            "description": "在md/txt/py/json/html等文本文件中修改/替换其中的内容，原理基于replace(past_text, replace_text)",
            "parameters": {
                "type": "object",
                "required": ["file_path", "past_text", "replace_text"],
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "相对于会话工作区的文件相对路径，如 dir/sub/xxx.txt",
                    },
                    "past_text": {"type": "string", "description": "需要替换掉的内容"},
                    "replace_text": {"type": "string", "description": "需要覆盖的内容"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_picture",
            "description": "查看一张图片的内容",
            "parameters": {
                "type": "object",
                "required": ["file_name"],
                "properties": {
                    "file_name": {
                        "type": "string",
                        "description": "图片的完整名称，如xxx.png/jpg/jpeg",
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "bash",
            "description": "在隔离沙箱中执行 shell 命令。只能访问当前对话目录，支持运行 Python/Node/Bash 脚本。",
            "parameters": {
                "type": "object",
                "required": ["command"],
                "properties": {"command": {"type": "string", "description": "Shell 命令"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_agent",
            "description": (
                "在专家库中永久实例化一个新的智能体（Agent），可附加工具、技能、知识库、子智能体和初始文件。"
                "注意：该工具用于把智能体长期沉淀到专家库中以便后续被反复检索调用，"
                "本身**并不具备调用子智能体执行任务的能力**。如需立即让子智能体执行任务，请改用 call_sub_agent。"
            ),
            "parameters": {
                "type": "object",
                "required": ["name", "description", "system_prompt", "model", "model_source"],
                "properties": {
                    "name": {"type": "string", "description": "英文与下划线组成"},
                    "description": {"type": "string", "description": "智能体描述"},
                    "system_prompt": {"type": "string", "description": "系统提示词"},
                    "model": {"type": "string", "description": "模型名称"},
                    "model_source": {"type": "string", "description": "模型来源"},
                    "name_zh": {"type": "string", "description": "中文显示名"},
                    "tools": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "绑定的工具名列表",
                    },
                    "skills": {
                        "type": "object",
                        "description": (
                            "绑定的技能（skill）集合，按来源分组：system 为系统技能名列表，user 为个人技能名列表。"
                            "对应 AgentCard.skills: Dict[Literal['system','user'], list]"
                        ),
                        "properties": {
                            "system": {"type": "array", "items": {"type": "string"}},
                            "user": {"type": "array", "items": {"type": "string"}},
                        },
                    },
                    "kbs": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "绑定的知识库 id 列表",
                    },
                    "agents": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "绑定的子智能体 agent_id 列表（结构关系，非临时召唤）",
                    },
                    "supervisor_history": {
                        "type": "boolean",
                        "description": "是否继承主智能体历史，默认 true",
                    },
                    "file_names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "初始注入到该智能体文件库的文件名列表",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_info",
            "description": (
                "统一信息列表查询入口，根据 category 返回对应的列表：\n"
                "- category=models：返回当前服务支持的大模型列表\n"
                "- category=tools：返回所有支持调用的工具列表\n"
                "- category=agent_cards：返回当前用户可调用的子智能体（专家）列表"
            ),
            "parameters": {
                "type": "object",
                "required": ["category"],
                "properties": {
                    "category": {
                        "type": "string",
                        "enum": ["models", "tools", "agent_cards"],
                        "description": "列表分类：models / tools / agent_cards",
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "skills",
            "description": (
                "统一的技能（skill）入口，通过 module 切换子动作：\n"
                "- module=preview：基于 query 预览可用 skill（系统 skill 走向量召回 Top20 & score>=0.4，"
                "个人 skill 直接全量返回 name+description），用于挑选后续要加载的 skill。"
                "**此模式下 query 必填且不能为空**——预览的目的就是按当前意图召回最相关的 skill，"
                "- module=load：将指定 skill 文件夹加载到工作区，需配合 source(system|user) 与 skill_name。"
                "当系统 skill 与个人 skill 功能相似时，优先选择 source=user。\n"
                "- module=close_preview：本轮 skill 选择完成后调用，将历史中的 preview 结果替换为占位字符串，"
                "避免技能列表持续占用上下文。"
            ),
            "parameters": {
                "type": "object",
                "required": ["module"],
                "properties": {
                    "module": {
                        "type": "string",
                        "enum": ["preview", "load", "close_preview"],
                        "description": "子动作：preview / load / close_preview",
                    },
                    "query": {
                        "type": "string",
                        "description": (
                            "[module=preview 必填，非空] 用于系统 skill 召回的检索语句，"
                            "应为当前用户意图或任务关键词；不可传空字符串"
                        ),
                        "minLength": 1,
                    },
                    "source": {
                        "type": "string",
                        "enum": ["system", "user"],
                        "description": "[module=load 必填] skill 来源：system 或 user",
                    },
                    "skill_name": {
                        "type": "string",
                        "description": "[module=load 必填] 要加载的 skill 名称",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "互联网搜索工具。",
            "parameters": {
                "type": "object",
                "required": ["query"],
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词"},
                    "count": {"type": "integer", "description": "返回条数，默认10"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_fetch",
            "description": "访问URL并转换为Markdown。",
            "parameters": {
                "type": "object",
                "required": ["url"],
                "properties": {"url": {"type": "string", "description": "URL地址"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "soulprout_kb_agent",
            "description": "知识库智能体，适合复杂检索任务。",
            "parameters": {
                "type": "object",
                "required": ["purpose"],
                "properties": {
                    "purpose": {"type": "string", "description": "检索目标说明"},
                    "session_id": {"type": "string", "description": "子智能体会话ID"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "soulprout_kb_tool",
            "description": "知识库基础RAG检索工具。",
            "parameters": {
                "type": "object",
                "required": ["purpose", "kb_id"],
                "properties": {
                    "purpose": {"type": "string", "description": "检索意图"},
                    "kb_id": {"type": "string", "description": "知识库ID"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "kb_chunk_abstract",
            "description": "通过kb_id获取知识库chunk摘要。",
            "parameters": {
                "type": "object",
                "required": ["kb_id"],
                "properties": {"kb_id": {"type": "string", "description": "知识库ID"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "chunk_content",
            "description": "通过chunk_id提取段落全文。",
            "parameters": {
                "type": "object",
                "required": ["chunk_id"],
                "properties": {"chunk_id": {"type": "string", "description": "段落ID"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "base_memory",
            "description": (
                "记忆（memory）的基础操作工具，仅承担 load / search / remove 三个轻量子动作，"
                "通过 module 切换；**创建与编辑请使用独立的 create_memory / edit_memory 工具**。\n"
                "- module=load：根据记忆 name 加载某条记忆的完整内容，并将该 name 记录到当前会话的 "
                "memory_loaded，后续召回不再重复推送该记忆；返回该记忆的 name、description 与 content。\n"
                "- module=search：基于 query 在当前用户的记忆库中做向量召回，返回相关记忆的 name 与 "
                "description 列表（不返回 content，content 需再调用 module=load 获取）。"
                "**此模式下 query 必填且不能为空**——应为当前用户意图或检索关键短句。\n"
                "- module=remove：根据记忆 name 永久删除当前用户的一条记忆，并从会话的 memory_loaded "
                "中移除该 name。"
            ),
            "parameters": {
                "type": "object",
                "required": ["module"],
                "properties": {
                    "module": {
                        "type": "string",
                        "enum": ["load", "search", "remove"],
                        "description": "子动作：load / search / remove",
                    },
                    "name": {
                        "type": "string",
                        "description": (
                            "[module=load / module=remove 必填] 记忆的简短英文名称（业务唯一标识）"
                        ),
                    },
                    "query": {
                        "type": "string",
                        "description": (
                            "[module=search 必填，非空] 用于记忆向量召回的检索短句，"
                            "应为当前用户意图或任务关键词；不可传空字符串"
                        ),
                        "minLength": 1,
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_memory",
            "description": (
                "新增一条记忆并写入向量库，写入后自动加入当前会话的 memory_loaded。"
                "同一用户下 name 必须唯一。"
            ),
            "parameters": {
                "type": "object",
                "required": ["name", "description", "content"],
                "properties": {
                    "name": {"type": "string", "description": "记忆的简短名称，仅使用英文与下划线"},
                    "description": {"type": "string", "description": "记忆的描述，描述该文件记录哪些记忆内容"},
                    "content": {"type": "string", "description": "记忆的完整内容"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_memory",
            "description": (
                "编辑一条已存在记忆的描述或内容。支持 update（在原内容末尾追加）与 "
                "replace（按 old_text 精确替换）两种模式。"
            ),
            "parameters": {
                "type": "object",
                "required": ["name", "edit_type", "edit_module", "text"],
                "properties": {
                    "name": {"type": "string", "description": "目标记忆的 name"},
                    "edit_type": {
                        "type": "string",
                        "enum": ["description", "content"],
                        "description": "编辑的字段：description 描述 / content 完整内容",
                    },
                    "edit_module": {
                        "type": "string",
                        "enum": ["update", "replace"],
                        "description": "编辑方式：update 末尾追加 / replace 文本替换",
                    },
                    "old_text": {
                        "type": "string",
                        "description": "仅 edit_module=replace 时必填，原文中待替换的文本",
                    },
                    "text": {
                        "type": "string",
                        "description": "需要写入的内容（追加内容或替换后的新文本）",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "user_option",
            "description": (
                "用户个性化配置工具，把对话过程中暴露出来的「用户个人信息」与「用户希望的智能体形象」"
                "持久化到该用户的档案中\n"
                "- info_type=userinfo：当用户透露了自己的身份、职业、所在地、兴趣爱好、口味偏好、"
                "等个人信息时调用，把信息存入 userinfo 字段，用于后续对话中保持记忆与个性化。\n"
                "- info_type=agentinfo：当用户表达了对当前 Soulprout 智能体的期望（比如希望被叫什么名字、"
                "性格、语气、说话风格、定位等）时调用，把信息存入 agentinfo 字段。\n"
                "- module=add：在原内容末尾追加 content（首次写入时直接写入）。\n"
                "- module=edit：在原内容中将 old_text 精确替换为 content，此时 old_text 必填。\n"
                "注意：userinfo 与 agentinfo 单字段上限 1024 字符"
            ),
            "parameters": {
                "type": "object",
                "required": ["info_type", "module", "content"],
                "properties": {
                    "info_type": {
                        "type": "string",
                        "enum": ["userinfo", "agentinfo"],
                        "description": "目标字段：userinfo（用户个人信息）/ agentinfo（智能体个性化信息）",
                    },
                    "module": {
                        "type": "string",
                        "enum": ["add", "edit"],
                        "description": "操作：add 末尾追加 / edit 精确替换",
                    },
                    "content": {
                        "type": "string",
                        "description": "add 时为要追加的内容；edit 时为替换后的新文本",
                    },
                    "old_text": {
                        "type": "string",
                        "description": "[module=edit 必填] 原内容中需要被替换掉的文本",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "call_sub_agent",
            "description": "召唤一个agent以执行任务。两种模式：1. 运行一个已存在的agent。2. 创建并运行一个新的agent，并为该agent临时注入信息",
            "parameters": {
                "type": "object",
                "required": ["module", "purpose"],
                "properties": {
                    "module": {"type": "string", "description": "召唤agent的模式：exist（已存在）/ new（新建并运行）"},
                    "purpose": {"type": "string", "description": "需要向子智能体交代的上下文、指令与目标"},
                    "name": {"type": "string", "description": "[module=exist 必填] 目标智能体在库中的英文 name；[module=new 可选] 新智能体名（仅允许英文与下划线，否则将自动生成）"},
                    "system_prompt": {"type": "string", "description": "[仅 new 时生效] 子智能体系统提示词，缺省为通用子代理提示"},
                    "skills": {"type": "array", "items": {"type": "string"}, "description": "[仅 new] 以 system 技能名列表形式加载的 skill 名称"},
                    "kbs": {"type": "array", "items": {"type": "string"}, "description": "[仅 new] 子智能体绑定的知识库 id 列表"},
                    "session_id": {"type": "string", "description": "续聊时传入上一次子智能体返回的 4 位会话 id"},
                },
            },
        },
    }
]


def get_all_tool_schemas() -> list[dict]:
    return TOOL_SCHEMAS.copy()


def get_registered_tool_names() -> set[str]:
    return {item["function"]["name"] for item in TOOL_SCHEMAS}


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
            "description": "阅读文件，获取该文件的全部内容，可阅读的文件类型为docx/doc/pdf/pptx/json/xlsx/txt/md",
            "parameters": {
                "type": "object",
                "required": ["file_name"],
                "properties": {
                    "file_name": {
                        "type": "string",
                        "description": "带有后缀的文件名，如xxx.txt",
                    }
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
                "required": ["file_name", "content"],
                "properties": {
                    "file_name": {"type": "string", "description": "带有后缀的文件名，如xxx.txt"},
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
                "required": ["file_name", "past_text", "replace_text"],
                "properties": {
                    "file_name": {"type": "string", "description": "带有后缀的文件名，如xxx.txt"},
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
            "description": "创建智能体（Agent）。可选附加工具、知识库、子智能体和文件列表。",
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
                    "tools": {"type": "array", "items": {"type": "string"}},
                    "kbs": {"type": "array", "items": {"type": "string"}},
                    "agents": {"type": "array", "items": {"type": "string"}},
                    "supervisor_history": {"type": "boolean"},
                    "file_names": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_models_list",
            "description": "获取所有支持的大模型列表。",
            "parameters": {"type": "object", "required": [], "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_tools_list",
            "description": "获取所有支持调用的工具列表。",
            "parameters": {"type": "object", "required": [], "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_agent_cards_list",
            "description": "获取当前用户可调用的子智能体列表。",
            "parameters": {"type": "object", "required": [], "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "load_skill",
            "description": "首次使用某个skill前，加载指定skill文件夹到工作区。",
            "parameters": {
                "type": "object",
                "required": ["source", "skill_name"],
                "properties": {
                    "source": {"type": "string", "description": "system或user"},
                    "skill_name": {"type": "string", "description": "skill名称"},
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


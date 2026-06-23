import os
import sys


def _bash_description() -> str:
    if os.getenv("DEPLOYMENT_MODE") == "saas":
        base = "Run shell commands in an isolated sandbox. Only the current conversation directory is accessible. Supports Python, Node, and Bash scripts."
    else:
        base = "Run command-line tools in the current conversation directory."
    if sys.platform.startswith("win"):
        os_hint = " The server is Windows; use Windows commands (cmd or PowerShell)."
    elif sys.platform == "darwin":
        os_hint = " The server is macOS; use macOS/Unix commands."
    elif sys.platform.startswith("linux"):
        os_hint = " The server is Linux; use Linux/bash commands."
    else:
        os_hint = f" The server OS is {sys.platform}; use commands appropriate for that system."
    return base + os_hint


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
                "Read files within the workspace. Supported file types include docx/doc/pdf/pptx/xlsx/txt/md/"
                "py/json/html, etc. For plain-text/code files, line-based paginated reading is supported "
                "(offset/limit), and returned results include line numbers; for rich-text/binary files such as "
                "pdf/doc(x)/ppt(x)/xlsx, the whole file is parsed at once, and offset/limit do not apply."
            ),
            "parameters": {
                "type": "object",
                "required": ["file_path"],
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "File path relative to the conversation workspace, e.g. dir/sub/xxx.txt",
                    },
                    "offset": {
                        "type": "integer",
                        "description": "Line number to start reading from (1-indexed), default 1, minimum 1",
                        "minimum": 1,
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of lines to read, default 500, maximum 2000",
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
            "description": "Write content to text files such as md/txt/py/json/html; repeated calls append content to the end",
            "parameters": {
                "type": "object",
                "required": ["file_path", "content"],
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "File path relative to the conversation workspace, e.g. dir/sub/xxx.txt",
                    },
                    "content": {"type": "string", "description": "Content to append to the end"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit",
            "description": "Modify/replace content in text files such as md/txt/py/json/html, based on replace(past_text, replace_text)",
            "parameters": {
                "type": "object",
                "required": ["file_path", "past_text", "replace_text"],
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "File path relative to the conversation workspace, e.g. dir/sub/xxx.txt",
                    },
                    "past_text": {"type": "string", "description": "Content that needs to be replaced"},
                    "replace_text": {"type": "string", "description": "Content to overwrite with"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_picture",
            "description": "View the content of an image",
            "parameters": {
                "type": "object",
                "required": ["file_name"],
                "properties": {
                    "file_name": {
                        "type": "string",
                        "description": "Full image file name, e.g. xxx.png/jpg/jpeg",
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "bash",
            "description": _bash_description(),
            "parameters": {
                "type": "object",
                "required": ["command"],
                "properties": {"command": {"type": "string", "description": "Shell command"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_agent",
            "description": (
                "Permanently instantiate a new Agent in the expert library, with optional tools, skills, knowledge bases, "
                "sub-agents, and initial files attached. Note: this tool is used to persist an agent long-term in the "
                "expert library so it can later be repeatedly retrieved and invoked; it **does not itself have the "
                "ability to call sub-agents to execute tasks**. To have a sub-agent execute a task immediately, use "
                "call_sub_agent instead."
            ),
            "parameters": {
                "type": "object",
                "required": ["name", "description", "system_prompt", "model", "model_source"],
                "properties": {
                    "name": {"type": "string", "description": "Composed of English letters and underscores"},
                    "description": {"type": "string", "description": "Agent description"},
                    "system_prompt": {"type": "string", "description": "System prompt"},
                    "model": {"type": "string", "description": "Model name"},
                    "model_source": {"type": "string", "description": "Model source"},
                    "name_zh": {"type": "string", "description": "Chinese display name"},
                    "tools": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of bound tool names",
                    },
                    "skills": {
                        "type": "object",
                        "description": (
                            "Set of bound skills, grouped by source: system is the list of system skill names, "
                            "and user is the list of personal skill names. Corresponds to "
                            "AgentCard.skills: Dict[Literal['system','user'], list]"
                        ),
                        "properties": {
                            "system": {"type": "array", "items": {"type": "string"}},
                            "user": {"type": "array", "items": {"type": "string"}},
                        },
                    },
                    "kbs": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of bound knowledge base IDs",
                    },
                    "agents": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of bound sub-agent agent_ids (structural relationship, not temporary invocation)",
                    },
                    "supervisor_history": {
                        "type": "boolean",
                        "description": "Whether to inherit the main agent history, default true",
                    },
                    "file_names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of file names initially injected into this agent's file library",
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
                "Unified information list query entry point; returns the corresponding list based on category:\n"
                "- category=models: returns the list of large models supported by the current service\n"
                "- category=tools: returns the list of all tools available for invocation\n"
                "- category=agent_cards: returns the list of sub-agents (experts) available to the current user"
            ),
            "parameters": {
                "type": "object",
                "required": ["category"],
                "properties": {
                    "category": {
                        "type": "string",
                        "enum": ["models", "tools", "agent_cards"],
                        "description": "List category: models / tools / agent_cards",
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
                "Unified skill entry point; switch sub-actions via module:\n"
                "- module=search: retrieve available skills based on query (system skills use vector recall Top20 & score>=0.6; "
                "personal skills directly return all name+description), used to select skills to load later. "
                "**In this mode, query is required and cannot be empty**—retrieve the most relevant skills according to the current intent.\n"
                "- module=view: view all skills available to the current user (system + personal, name+description), "
                "without query retrieval; returned content is truncated to 10000 characters by default.\n"
                "- module=load: load the specified skill folder into the workspace; requires source(system|user) and skill_name. "
                "When a system skill and a personal skill have similar functionality, prefer source=user.\n"
                "- module=close_search: call after skill selection for this round is complete; replaces historical skills tool results "
                "with a placeholder string to prevent the skill list from continuously occupying context."
            ),
            "parameters": {
                "type": "object",
                "required": ["module"],
                "properties": {
                    "module": {
                        "type": "string",
                        "enum": ["search", "view", "load", "close_search"],
                        "description": "Sub-action: search / view / load / close_search",
                    },
                    "query": {
                        "type": "string",
                        "description": (
                            "[Required for module=search, non-empty] Retrieval query for system skill recall; "
                            "should be the current user intent or task keywords; empty strings are not allowed"
                        ),
                        "minLength": 1,
                    },
                    "source": {
                        "type": "string",
                        "enum": ["system", "user"],
                        "description": "[Required for module=load] Skill source: system or user",
                    },
                    "skill_name": {
                        "type": "string",
                        "description": "[Required for module=load] Name of the skill to load",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Internet search tool.",
            "parameters": {
                "type": "object",
                "required": ["query"],
                "properties": {
                    "query": {"type": "string", "description": "Search keywords"},
                    "count": {"type": "integer", "description": "Number of results to return, default 10"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_fetch",
            "description": "Visit a URL and convert it to Markdown.",
            "parameters": {
                "type": "object",
                "required": ["url"],
                "properties": {"url": {"type": "string", "description": "URL address"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "soulprout_kb_tool",
            "description": "Basic RAG retrieval tool for knowledge bases.",
            "parameters": {
                "type": "object",
                "required": ["purpose", "kb_id"],
                "properties": {
                    "purpose": {"type": "string", "description": "Retrieval intent"},
                    "kb_id": {"type": "string", "description": "Knowledge base ID"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "kb_chunk_abstract",
            "description": "Get knowledge base chunk abstracts by kb_id.",
            "parameters": {
                "type": "object",
                "required": ["kb_id"],
                "properties": {"kb_id": {"type": "string", "description": "Knowledge base ID"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "chunk_content",
            "description": "Extract the full paragraph text by chunk_id.",
            "parameters": {
                "type": "object",
                "required": ["chunk_id"],
                "properties": {"chunk_id": {"type": "string", "description": "Paragraph ID"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "base_memory",
            "description": (
                "Basic operation tool for memory; it only handles four lightweight sub-actions: load / search / view / remove, "
                "switched via module; **use the separate create_memory / edit_memory tools for creation and editing**.\n"
                "- module=load: load the full content of a memory by memory name, and record that name in the current session's "
                "memory_loaded so subsequent recalls will not repeatedly push that memory; returns the memory's name, "
                "description, and content.\n"
                "- module=search: perform vector recall in the current user's memory library based on query, returning a list "
                "of related memory names and descriptions (content is not returned; call module=load to get content). "
                "**In this mode, query is required and cannot be empty**—it should be the current user intent or a key retrieval phrase.\n"
                "- module=view: view all memories under the current user (including name, description, and content), "
                "without query retrieval; returned content is truncated to 10000 characters by default.\n"
                "- module=remove: permanently delete a memory of the current user by memory name, and remove that name from "
                "the session's memory_loaded."
            ),
            "parameters": {
                "type": "object",
                "required": ["module"],
                "properties": {
                    "module": {
                        "type": "string",
                        "enum": ["load", "search", "view", "remove"],
                        "description": "Sub-action: load / search / view / remove",
                    },
                    "name": {
                        "type": "string",
                        "description": (
                            "[Required for module=load / module=remove] Short English name of the memory (business-unique identifier)"
                        ),
                    },
                    "query": {
                        "type": "string",
                        "description": (
                            "[Required for module=search, non-empty] Retrieval phrase for memory vector recall; "
                            "should be the current user intent or task keywords; empty strings are not allowed"
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
                "Add a new memory and write it to the vector database; after writing, it is automatically added to "
                "the current session's memory_loaded. The name must be unique under the same user."
            ),
            "parameters": {
                "type": "object",
                "required": ["name", "description", "content"],
                "properties": {
                    "name": {"type": "string", "description": "Short name of the memory, using only English letters and underscores"},
                    "description": {"type": "string", "description": "Memory description, describing what memory content this file records"},
                    "content": {"type": "string", "description": "Full content of the memory"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_memory",
            "description": (
                "Edit the description or content of an existing memory. Supports two modes: update "
                "(append to the end of the original content) and replace (exact replacement by old_text)."
            ),
            "parameters": {
                "type": "object",
                "required": ["name", "edit_type", "edit_module", "text"],
                "properties": {
                    "name": {"type": "string", "description": "Name of the target memory"},
                    "edit_type": {
                        "type": "string",
                        "enum": ["description", "content"],
                        "description": "Field to edit: description / content",
                    },
                    "edit_module": {
                        "type": "string",
                        "enum": ["update", "replace"],
                        "description": "Edit mode: update append to the end / replace text replacement",
                    },
                    "old_text": {
                        "type": "string",
                        "description": "Required only when edit_module=replace; the text in the original content to be replaced",
                    },
                    "text": {
                        "type": "string",
                        "description": "Content to write (appended content or the new replacement text)",
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
                "User personalization configuration tool. Persist the 'user personal information' and the "
                "'agent persona desired by the user' exposed during the conversation into that user's profile.\n"
                "- info_type=userinfo: call when the user reveals personal information such as identity, occupation, "
                "location, interests, hobbies, or taste preferences; store the information in the userinfo field "
                "to maintain memory and personalization in subsequent conversations.\n"
                "- info_type=agentinfo: call when the user expresses expectations for the current Soulprout agent "
                "(such as what name they want it to be called, personality, tone, speaking style, positioning, etc.); "
                "store the information in the agentinfo field.\n"
                "- module=view: view the existing content of the field corresponding to the current info_type, then "
                "decide whether to use add or edit.\n"
                "- module=add: append content to the end of the original content (write directly on first entry).\n"
                "- module=edit: exactly replace old_text in the original content with content; old_text is required in this case.\n"
                "Note: each of the userinfo and agentinfo fields has a 1024-character limit"
            ),
            "parameters": {
                "type": "object",
                "required": ["info_type", "module"],
                "properties": {
                    "info_type": {
                        "type": "string",
                        "enum": ["userinfo", "agentinfo"],
                        "description": "Target field: userinfo (user personal information) / agentinfo (agent personalization information)",
                    },
                    "module": {
                        "type": "string",
                        "enum": ["view", "add", "edit"],
                        "description": "Operation: view current content / add append to the end / edit exact replacement",
                    },
                    "content": {
                        "type": "string",
                        "description": "[Required for module=add or edit] For add, the content to append; for edit, the new replacement text",
                    },
                    "old_text": {
                        "type": "string",
                        "description": "[Required for module=edit] Text in the original content that needs to be replaced",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ask_user_feedback",
            "description": (
                "Launch batched interactive feedback and pause until the user submits all answers in the UI. "
                "Use when you need decisions, preferences, or missing details from the user. "
                "Put every question in the questions array in one call—do not invoke this tool repeatedly. "
                "Each item may be choice (single/multiple, optional custom input) or input (free text). "
                "Submitted answers arrive as the next user message."
            ),
            "parameters": {
                "type": "object",
                "required": ["questions"],
                "properties": {
                    "description": {
                        "type": "string",
                        "description": "Overall intro shown to the user, e.g. 'Please confirm deployment and config choices'",
                    },
                    "questions": {
                        "type": "array",
                        "description": "All questions to ask in one batch",
                        "minItems": 1,
                        "items": {
                            "type": "object",
                            "required": ["interaction_type", "prompt"],
                            "properties": {
                                "id": {
                                    "type": "string",
                                    "description": "Question id for answer aggregation; defaults to index",
                                },
                                "interaction_type": {
                                    "type": "string",
                                    "enum": ["choice", "input"],
                                    "description": "choice = multiple-choice; input = free-text",
                                },
                                "prompt": {
                                    "type": "string",
                                    "description": "Question text shown to the user",
                                },
                                "choice_mode": {
                                    "type": "string",
                                    "enum": ["single", "multiple"],
                                    "description": "[choice] single or multiple selection; default single",
                                },
                                "options": {
                                    "type": "array",
                                    "description": "[choice required] strings or {key, label, value} objects",
                                    "items": {
                                        "oneOf": [
                                            {"type": "string"},
                                            {
                                                "type": "object",
                                                "properties": {
                                                    "key": {"type": "string"},
                                                    "label": {"type": "string"},
                                                    "value": {"type": "string"},
                                                },
                                            },
                                        ]
                                    },
                                },
                                "allow_custom_input": {
                                    "type": "boolean",
                                    "description": "[choice] allow an additional free-text field",
                                },
                                "custom_input_placeholder": {
                                    "type": "string",
                                    "description": "[choice + allow_custom_input] placeholder for custom input",
                                },
                                "placeholder": {
                                    "type": "string",
                                    "description": "[input] input placeholder",
                                },
                            },
                        },
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "conversation_option",
            "description": (
                "Conversation context management tool.\n"
                "- module=clear: completely clear the current conversation context\n"
                "- module=compress: immediately perform one context compression"
            ),
            "parameters": {
                "type": "object",
                "required": ["module"],
                "properties": {
                    "module": {
                        "type": "string",
                        "enum": ["clear", "compress"],
                        "description": "clear clears context / compress compresses context",
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "call_sub_agent",
            "description": "Summon a sub-agent to execute a task immediately (not written to the expert library). Two modes:\n"
                "1. module=exist: call an agent already created in the expert library, using its existing configuration "
                "(system_prompt/tools/skills/kbs, etc.) without redefining it.\n"
                "2. module=new: temporarily create and run a sub-agent (not stored in the library), defining its behavior "
                "and capabilities on the spot through system_prompt/tools/skills/kbs when calling it.\n"
                "Difference from create_agent: create_agent permanently persists the agent into the expert library; "
                "call_sub_agent is only for immediate execution within this/current follow-up conversation.",
            "parameters": {
                "type": "object",
                "required": ["module", "purpose", "name"],
                "properties": {
                    "module": {"type": "string", "description": "Sub-agent summoning mode: exist (already exists) / new (create and run)"},
                    "purpose": {"type": "string", "description": "Context, instructions, and objectives to explain to the sub-agent"},
                    "name": {"type": "string", "description": "[Required] For module=exist, provide the target agent's English name in the library; for module=new, define the new agent name (only English letters and underscores are allowed)"},
                    "agent_id": {"type": "string", "description": "[Only effective for exist] Provide the ID of an existing sub-agent"},
                    "system_prompt": {"type": "string", "description": "[Only effective for new] System prompt for the sub-agent; defaults to the general sub-agent prompt"},
                    "skills": {
                        "type": "object",
                        "description": (
                            "[Only for new] Set of bound skills, grouped by source: system is the list of system skill names, "
                            "and user is the list of personal skill names. Corresponds to "
                            "AgentCard.skills: Dict[Literal['system','user'], list]"
                        ),
                        "properties": {
                            "system": {"type": "array", "items": {"type": "string"}},
                            "user": {"type": "array", "items": {"type": "string"}},
                        },
                    },
                    "tools": {"type": "array", "items": {"type": "string"}, "description": "[Only for new] List of tools to add to this sub-agent"},
                    "kbs": {"type": "array", "items": {"type": "string"}, "description": "[Only for new] List of knowledge base IDs bound to the sub-agent"},
                    "files": {"type": "array", "items": {"type": "string"}, "description": "[Only for new] List of file names bound to the sub-agent (files must be in the current workspace)"},
                    "session_id": {"type": "string", "description": "When continuing a previous sub-agent conversation, pass the 4-digit session ID returned by the previous sub-agent"},
                },
            },
        },
    }
]


def get_all_tool_schemas() -> list[dict]:
    return TOOL_SCHEMAS.copy()


def get_registered_tool_names() -> set[str]:
    return {item["function"]["name"] for item in TOOL_SCHEMAS}


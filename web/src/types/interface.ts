// ✅ 定义接口类型（建议和后端约定）
export interface ConversationBase {
    user_id: string
    conversation_id: string
    abstract?: string
    tools_use?: boolean // 是否使用工具
    skills_use?: boolean // 是否使用技能
    kb_use?: Array<string> // 是否使用知识库
    model_source?: string // 模型来源
    model?: string
    agent_use?: 'expert-agent' | 'select-agent' | 'soulprout' | string | null
    create_at: string
    updated_at: string
}

export interface ChatRequest {
  model_source?: string;        // 可选，默认值前端不写，在后端处理
  model?: string;
  message: string;
  user_id?: string;
  conversation_id?: string;
  /** 编辑已发送用户消息时，后端返回的 input 消息 id */
  input_message_id?: string;
  tools_use?: boolean; // 是否使用工具
  skills_use?: boolean; // 是否使用技能
  kb_use?: Array<string>; // 是否使用知识库
  agent_use?: 'expert-agent' | 'select-agent' | 'soulprout' | null;
  agent_id?: string | string[] | null;  // 传递时使用 agent_id
  agent_name?: string | string[] | null;  // 仅用于展示，从 agent_card_list 根据 agent_id 查找
  files?: File[];
}

export interface ToolCalls {
    type: string
    function: {
        name: string
        arguments: string
        parameters?: any
    }
    id: string
}

export interface AgentMessage {
  user_id: string
  conversation_id: string
  type: string
  role: string
  content?: string
  /** 用户消息的持久化 id（流式 input_message_id 或历史接口） */
  id?: string
  created_at: number // ISO 格式的时间字符串，例如 '2024-05-23T14:55:00Z'
  tool_call_id?: string
  tool_calls?: [ToolCalls]
  table?: Record<string, any>
  image?: string
  from_streaming?: boolean  // 标记来自流式输出，用于 tool_calls 不显示 content
}

export interface ChatMessage {
  role: string
  content?: string
  created_at: number // ISO 格式的时间字符串，例如 '2024-05-23T14:55:00Z'
  tool_call_id?: string
  tool_calls?: Record<string, any>
  table?: Record<string, any>
  image?: string
}

export interface AgentCard {
  agent_id?: string
  user_id?: string  // 创建者 user_id，用于分组：我的创建 / 我的订阅 / 系统预设
  name: string
  name_zh?: string | null // 智能体中文名称
  description: string
  system_prompt: string
  tools?: string[]
  /** 与后端 AgentCard.skills 一致：system / user 为技能名称列表 */
  skills?: { system?: string[]; user?: string[] } | null
  announcement?: string | null
  agents?: string[]
  kbs?: string[]
  model_source?: string;
  model?: string;
  user_name?: string;  // 创建者用户名，前端从 /api/user/me 获取后传入
  public?: boolean;    // 是否公开，默认 false
}
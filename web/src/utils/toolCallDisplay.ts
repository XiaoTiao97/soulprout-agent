import { parseWebSearchResultContent } from './parseWebSearchResult'

export type ToolCallLike = {
  id?: string
  function?: {
    name?: string
    arguments?: string
  }
}

export type ToolCallItem = {
  toolCallId: string
  toolName: string
  arguments: Record<string, unknown>
  messageType?: 'get_tools' | 'get_agents' | string
}

export function parseToolArguments(argsString: string): Record<string, unknown> {
  try {
    const parsed = JSON.parse(argsString)
    return typeof parsed === 'object' && parsed !== null ? parsed as Record<string, unknown> : {}
  } catch {
    return {}
  }
}

export function resolveToolCallId(toolCall: { id?: string }, fallbackId?: string): string {
  return toolCall?.id || fallbackId || ''
}

export type WebSearchCallItem = {
  toolCallId: string
  query?: string
}

export function buildWebSearchCallItems(
  toolCalls: ToolCallLike[] | undefined,
  fallbackId?: string,
): WebSearchCallItem[] {
  if (!toolCalls?.length) return []
  return toolCalls
    .filter((tc) => tc.function?.name === 'web_search')
    .map((tc) => {
      const args = parseToolArguments(tc.function?.arguments || '{}')
      const q = args.query ?? args.q ?? args.search_query ?? ''
      return {
        toolCallId: resolveToolCallId(tc, fallbackId),
        query: typeof q === 'string' ? q : String(q),
      }
    })
}

export function buildGenericToolCallItems(
  toolCalls: ToolCallLike[] | undefined,
  fallbackId?: string,
  messageType?: string,
): ToolCallItem[] {
  return buildToolCallItems(toolCalls, fallbackId, messageType)
    .filter((item) => item.toolName !== 'web_search')
}

export function buildToolCallItems(
  toolCalls: ToolCallLike[] | undefined,
  fallbackId?: string,
  messageType?: string,
): ToolCallItem[] {
  if (!toolCalls?.length) return []
  return toolCalls.map((tc) => ({
    toolCallId: resolveToolCallId(tc, fallbackId),
    toolName: tc.function?.name || '',
    arguments: parseToolArguments(tc.function?.arguments || '{}'),
    messageType,
  }))
}

function str(v: unknown): string {
  if (v == null) return ''
  return typeof v === 'string' ? v : String(v)
}

function basename(path: unknown): string {
  const s = str(path).replace(/\\/g, '/')
  const parts = s.split('/')
  return parts[parts.length - 1] || s
}

function truncate(text: string, max = 48): string {
  if (!text) return ''
  return text.length > max ? `${text.slice(0, max)}…` : text
}

/** 根据工具名与参数生成摘要文案（pending = 尚无结果） */
export function getToolSummaryLabel(
  toolName: string,
  args: Record<string, unknown>,
  hasResult: boolean,
  resultContent?: string,
): string {
  switch (toolName) {
    case 'get_action_blueprint':
      return hasResult ? '已完成行动蓝图' : '正在生成蓝图'

    case 'read': {
      const file = basename(args.file_path)
      return hasResult ? `已阅读 ${file || '文件'}` : `正在阅读 ${file || '文件'}…`
    }

    case 'write': {
      const file = basename(args.file_path)
      return hasResult ? `已写入 ${file || '文件'}` : `正在写入 ${file || '文件'}…`
    }

    case 'edit': {
      const file = basename(args.file_path)
      return hasResult ? `已编辑 ${file || '文件'}` : `正在编辑 ${file || '文件'}…`
    }

    case 'read_picture': {
      const file = str(args.file_name)
      return hasResult ? `已查看图片 ${file || ''}`.trim() : `正在查看图片 ${file || '…'}`.trim()
    }

    case 'bash': {
      const cmd = truncate(str(args.command), 36)
      return hasResult ? `命令执行完成${cmd ? `：${cmd}` : ''}` : `正在执行命令${cmd ? `：${cmd}` : '…'}`
    }

    case 'create_agent': {
      const name = str(args.name_zh || args.name)
      return hasResult ? `已创建智能体 ${name || ''}`.trim() : `正在创建智能体 ${name || '…'}`.trim()
    }

    case 'list_info': {
      const category = str(args.category)
      const label =
        category === 'models' ? '模型' : category === 'tools' ? '工具' : category === 'agent_cards' ? '子智能体' : category || '信息'
      return hasResult ? `已查询${label}列表` : `正在查询${label}列表…`
    }

    case 'skills': {
      const mod = str(args.module)
      if (mod === 'search') {
        const q = truncate(str(args.query), 28)
        return hasResult ? `已检索技能${q ? `：${q}` : ''}` : `正在检索技能${q ? `：${q}` : '…'}`
      }
      if (mod === 'view') return hasResult ? '已查看全部技能' : '正在查看全部技能…'
      if (mod === 'load') {
        const skill = str(args.skill_name)
        return hasResult ? `已加载技能 ${skill || ''}`.trim() : `正在加载技能 ${skill || '…'}`.trim()
      }
      if (mod === 'close_search') return hasResult ? '已关闭技能检索结果' : '正在关闭技能检索结果…'
      return hasResult ? '技能操作完成' : '正在处理技能…'
    }

    case 'web_search': {
      if (hasResult && resultContent) {
        const count = parseWebSearchResultContent(resultContent).length
        if (count > 0) return `已阅读 ${count} 个网页`
      }
      const q = truncate(str(args.query ?? args.q ?? args.search_query), 28)
      return hasResult ? `已完成网页搜索${q ? `：${q}` : ''}` : `正在搜索网页${q ? `：${q}` : '…'}`
    }

    case 'web_fetch': {
      const url = truncate(str(args.url), 40)
      return hasResult ? `已访问 ${url || '网页'}` : `正在访问 ${url || '网页'}…`
    }

    case 'soulprout_kb_agent': {
      const purpose = truncate(str(args.purpose), 32)
      return hasResult
        ? `知识库智能体已完成${purpose ? `：${purpose}` : ''}`
        : `正在调用知识库智能体${purpose ? `：${purpose}` : '…'}`
    }

    case 'soulprout_kb_tool': {
      const purpose = truncate(str(args.purpose), 32)
      return hasResult
        ? `知识库检索完成${purpose ? `：${purpose}` : ''}`
        : `正在检索知识库${purpose ? `：${purpose}` : '…'}`
    }

    case 'kb_chunk_abstract':
      return hasResult ? '已获取知识库摘要' : '正在获取知识库摘要…'

    case 'chunk_content':
      return hasResult ? '已读取段落内容' : '正在读取段落内容…'

    case 'base_memory': {
      const mod = str(args.module)
      const name = str(args.name)
      if (mod === 'load') {
        return hasResult ? `已加载记忆 ${name || ''}`.trim() : `正在加载记忆 ${name || '…'}`.trim()
      }
      if (mod === 'search') {
        const q = truncate(str(args.query), 28)
        return hasResult ? `已搜索记忆${q ? `：${q}` : ''}` : `正在搜索记忆${q ? `：${q}` : '…'}`
      }
      if (mod === 'view') return hasResult ? '已查看全部记忆' : '正在查看全部记忆…'
      if (mod === 'remove') {
        return hasResult ? `已删除记忆 ${name || ''}`.trim() : `正在删除记忆 ${name || '…'}`.trim()
      }
      return hasResult ? '记忆操作完成' : '正在处理记忆…'
    }

    case 'create_memory': {
      const name = str(args.name)
      return hasResult ? `已创建记忆 ${name || ''}`.trim() : `正在创建记忆 ${name || '…'}`.trim()
    }

    case 'edit_memory': {
      const name = str(args.name)
      return hasResult ? `已编辑记忆 ${name || ''}`.trim() : `正在编辑记忆 ${name || '…'}`.trim()
    }

    case 'ask_user_feedback': {
      const batch = Array.isArray(args.questions) ? args.questions.length : 0
      if (batch > 0) {
        return hasResult
          ? `已发起 ${batch} 项用户反馈，等待提交`
          : `等待用户完成 ${batch} 项反馈…`
      }
      const prompt = truncate(str(args.prompt), 28)
      return hasResult
        ? `已发起用户反馈${prompt ? `：${prompt}` : ''}`
        : `等待用户反馈${prompt ? `：${prompt}` : '…'}`
    }

    case 'user_option': {
      const mod = str(args.module)
      const info = str(args.info_type) === 'agentinfo' ? '智能体配置' : '用户档案'
      if (mod === 'view') return hasResult ? `已查看${info}` : `正在查看${info}…`
      if (mod === 'add') return hasResult ? `已更新${info}` : `正在更新${info}…`
      if (mod === 'edit') return hasResult ? `已修改${info}` : `正在修改${info}…`
      return hasResult ? `${info}操作完成` : `正在处理${info}…`
    }

    case 'call_sub_agent': {
      const name = str(args.name)
      const purpose = truncate(str(args.purpose), 28)
      const agentLabel = name ? `${name}(子智能体)` : '子智能体'
      return hasResult
        ? `已完成调用 ${agentLabel}${purpose ? `：${purpose}` : ''}`
        : `正在调用 ${agentLabel}${purpose ? `：${purpose}` : '…'}`
    }

    default:
      return hasResult ? `已完成 ${toolName || '工具调用'}` : `正在调用 ${toolName || '工具'}…`
  }
}

export function formatToolArgumentValue(value: unknown): string {
  if (value == null) return ''
  if (typeof value === 'string') return value
  return JSON.stringify(value, null, 2)
}

export function formatToolResultContent(content: string): string {
  if (!content) return ''
  const trimmed = content.trim()
  if (!trimmed) return ''
  try {
    const parsed = JSON.parse(trimmed)
    return JSON.stringify(parsed, null, 2)
  } catch {
    return content
  }
}

const FILE_PREVIEW_TOOL_NAMES = new Set(['read', 'write', 'edit'])

const EXTRA_PANEL_AUTO_EXPAND_TOOL_NAMES = new Set(['read', 'write', 'edit', 'call_sub_agent'])

/** 流式消息是否应自动展开右侧 ExtraInfo 面板 */
export function shouldAutoExpandExtraPanel(chunk: {
  role?: string
  type?: string
  tool_calls?: { function?: { name?: string } }[]
}): boolean {
  const role = chunk.role || ''
  const type = chunk.type || ''

  if (role === 'file') {
    return FILE_PREVIEW_TOOL_NAMES.has(type || 'read')
  }

  if (role === 'agent' && type !== 'plan') {
    return true
  }

  if (role === 'tool' && type === 'agent') {
    return true
  }

  if (chunk.tool_calls?.length) {
    for (const tc of chunk.tool_calls) {
      const name = tc.function?.name || ''
      if (EXTRA_PANEL_AUTO_EXPAND_TOOL_NAMES.has(name)) {
        return true
      }
    }
  }

  return false
}

export function normalizeToolFilePath(filePath: unknown): string {
  return str(filePath).replace(/\\/g, '/').replace(/^\/+/, '').trim()
}

/** read / write / edit 工具参数中的文件路径 */
export function getToolFilePath(toolName: string, args: Record<string, unknown>): string | null {
  if (!FILE_PREVIEW_TOOL_NAMES.has(toolName)) return null
  const normalized = normalizeToolFilePath(args.file_path ?? args.file_name)
  return normalized || null
}

export function getToolIconKind(toolName: string, messageType?: string): 'search' | 'agent' | 'file' | 'shell' | 'memory' | 'kb' | 'default' {
  if (toolName === 'web_search' || toolName === 'web_fetch') return 'search'
  if (toolName === 'call_sub_agent' || toolName === 'soulprout_kb_agent' || toolName === 'create_agent' || messageType === 'get_agents') {
    return 'agent'
  }
  if (['read', 'write', 'edit', 'read_picture'].includes(toolName)) return 'file'
  if (toolName === 'bash') return 'shell'
  if (['base_memory', 'create_memory', 'edit_memory'].includes(toolName)) return 'memory'
  if (['soulprout_kb_tool', 'kb_chunk_abstract', 'chunk_content'].includes(toolName)) return 'kb'
  return 'default'
}

export type WebSearchResultItem = {
  title: string
  link: string
  content: string
  media: string
  publish_date: string
}

const WS_KEYS = ['title', 'link', 'content', 'media', 'publish_date'] as const

function unescapePythonString(s: string): string {
  return s
    .replace(/\\n/g, '\n')
    .replace(/\\r/g, '\r')
    .replace(/\\t/g, '\t')
    .replace(/\\'/g, "'")
    .replace(/\\"/g, '"')
    .replace(/\\\\/g, '\\')
}

/** 从 Python dict 字符串中提取单个字段值 */
function extractPythonDictValue(dictStr: string, key: string): string {
  const patterns = [
    new RegExp(`['"]${key}['"]\\s*:\\s*'((?:\\\\.|[^'\\\\])*)'`, 's'),
    new RegExp(`['"]${key}['"]\\s*:\\s*"((?:\\\\.|[^"\\\\])*)"`, 's'),
    new RegExp(`['"]${key}['"]\\s*:\\s*None`, 's'),
  ]
  for (let i = 0; i < 2; i++) {
    const m = dictStr.match(patterns[i])
    if (m) return unescapePythonString(m[1])
  }
  if (patterns[2].test(dictStr)) return ''
  return ''
}

/** 按顶层 `{...}` 切分 Python 列表中的多个 dict */
function splitPythonDicts(inner: string): string[] {
  const parts: string[] = []
  let depth = 0
  let start = -1
  let inString = false
  let stringChar = ''
  let escape = false

  for (let i = 0; i < inner.length; i++) {
    const c = inner[i]
    if (escape) {
      escape = false
      continue
    }
    if (inString) {
      if (c === '\\') {
        escape = true
        continue
      }
      if (c === stringChar) inString = false
      continue
    }
    if (c === "'" || c === '"') {
      inString = true
      stringChar = c
      continue
    }
    if (c === '{') {
      if (depth === 0) start = i
      depth++
    } else if (c === '}') {
      depth--
      if (depth === 0 && start >= 0) {
        parts.push(inner.slice(start, i + 1))
        start = -1
      }
    }
  }
  return parts
}

function parsePythonDict(dictStr: string): WebSearchResultItem | null {
  const item: WebSearchResultItem = {
    title: '',
    link: '',
    content: '',
    media: '',
    publish_date: '',
  }
  let hasAny = false
  for (const key of WS_KEYS) {
    const val = extractPythonDictValue(dictStr, key)
    if (val !== '') hasAny = true
    item[key] = val
  }
  if (!hasAny && !dictStr.includes('title')) return null
  return item
}

function normalizeItems(raw: unknown[]): WebSearchResultItem[] {
  return raw
    .filter((x): x is Record<string, unknown> => x != null && typeof x === 'object' && !Array.isArray(x))
    .map((x) => ({
      title: String(x.title ?? ''),
      link: String(x.link ?? ''),
      content: String(x.content ?? ''),
      media: String(x.media ?? ''),
      publish_date: String(x.publish_date ?? ''),
    }))
    .filter((x) => x.title || x.link)
}

/**
 * 解析 web_search 返回内容。
 * 后端使用 Python str(list) 返回（单引号），需兼容 JSON 与 Python 字面量两种格式。
 */
export function parseWebSearchResultContent(content: string): WebSearchResultItem[] {
  if (!content || typeof content !== 'string') return []

  let trimmed = content.trim()
  if (!trimmed) return []

  // 可能被包了一层引号
  if (
    (trimmed.startsWith('"') && trimmed.endsWith('"')) ||
    (trimmed.startsWith("'") && trimmed.endsWith("'"))
  ) {
    try {
      trimmed = JSON.parse(trimmed)
      if (typeof trimmed === 'string') {
        return parseWebSearchResultContent(trimmed)
      }
    } catch {
      trimmed = trimmed.slice(1, -1)
    }
  }

  // 标准 JSON
  try {
    const parsed = JSON.parse(trimmed)
    if (Array.isArray(parsed)) return normalizeItems(parsed)
    if (parsed && typeof parsed === 'object') return normalizeItems([parsed])
  } catch {
    /* 继续尝试 Python 格式 */
  }

  // Python str(list)： [{'title': '...', ...}, ...]
  if (!trimmed.startsWith('[')) {
    const bracket = trimmed.match(/\[[\s\S]*\]/)
    if (bracket) trimmed = bracket[0]
    else return []
  }

  if (!trimmed.endsWith(']')) return []

  const inner = trimmed.slice(1, -1).trim()
  if (!inner) return []

  const dicts = splitPythonDicts(inner)
  const results: WebSearchResultItem[] = []
  for (const d of dicts) {
    const item = parsePythonDict(d)
    if (item && (item.title || item.link)) results.push(item)
  }
  return results
}

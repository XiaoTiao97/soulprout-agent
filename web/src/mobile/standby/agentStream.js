/**
 * 待命模式向 Agent 发送一句话，并流式取回回复文本。
 * 与手机聊天页同一条 Soul 会话（conversation_id = user_id），所以聊天记录会同步。
 * 回复文本的取法与 agent/services/rokid.py 一致：role=assistant 且 type=text。
 */
import { apiFetch } from '../api'

/**
 * @param {object} opts
 * @param {string} opts.message 用户说的话
 * @param {string} opts.userId 当前用户 id（Soul 会话 id）
 * @param {AbortSignal} [opts.signal]
 * @param {(delta: string) => void} opts.onDelta 每收到一段回复文本
 * @returns {Promise<string>} 完整回复文本
 */
export async function streamAgentReply({ message, userId, signal, onDelta }) {
  const payload = {
    message,
    conversation_id: userId,
    agent_use: 'soulprout',
    agent_id: null,
    agent_name: null,
    tools_use: true,
    skills_use: true,
    kb_use: [],
    files: [],
  }
  const formData = new FormData()
  formData.append('chat_request', JSON.stringify(payload))

  const response = await apiFetch('/api/message/chat', {
    method: 'POST',
    body: formData,
    headers: { Accept: 'text/event-stream' },
    cache: 'no-store',
    signal,
  })
  if (!response.ok) throw new Error(`Agent 请求失败（HTTP ${response.status}）`)
  if (!response.body) throw new Error('Agent 没有返回数据流')

  const reader = response.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''
  let full = ''
  let followedTurnId = ''

  const handleLine = (line) => {
    const trimmed = line.trim()
    if (!trimmed.startsWith('data:')) return
    const data = trimmed.slice(5).trim()
    if (!data) return
    let chunk
    try {
      chunk = JSON.parse(data)
    } catch {
      return
    }
    // 与聊天页一致：只跟随当前这一轮
    if (chunk.type === 'turn_started' && chunk.turn_id) followedTurnId = chunk.turn_id
    else if (chunk.turn_id && followedTurnId && chunk.turn_id !== followedTurnId) return
    else if (!followedTurnId && chunk.turn_id) followedTurnId = chunk.turn_id

    if (chunk.type === 'error') throw new Error(chunk.content || 'Agent 回复异常')
    const content = chunk.content || ''
    if (!content) return
    if (chunk.type === 'user_feedback' || (chunk.role === 'assistant' && chunk.type === 'text')) {
      full += content
      onDelta(content)
    }
  }

  try {
    while (true) {
      const { value, done } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''
      for (const line of lines) handleLine(line)
    }
    if (buffer) handleLine(buffer)
  } finally {
    reader.releaseLock()
  }
  return full
}

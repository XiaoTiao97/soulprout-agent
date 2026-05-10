<!-- ConversationPage.vue -->
<template>
  <div class="main-container">
    <div class="main-use-container">
      <ConversationWindow
        :conversation_list="conversation_list"
        :isExpanded="isExpanded"
        :chat_request="chat_request"
        :username="currentUsername"
        @createConversation="createConversation"
        @deleteConversation="deleteConversation"
        @pickConversation="pickConversation"
        @SidebarChange="SidebarChange"
        @openToolOption="openToolOption"
        @openSkillOption="openSkillOption"
        @openKBOption="openKBOption"
        @openAgentOption="openAgentOption"
          :isGenerating="isGenerating"
        @updateConversationAbstract="updateConversationAbstract"
      />

      <div class="chat-main" :class="{ 'with-extra': showExtraInfo }">
        <div class="chat-window-wrapper" :style="{ width: showExtraInfo ? chatWindowWidth : '100%' }">
          <ChatWindow
            :agentname="agentname"
            :chat_request="chat_request"
            :agent_message_list="agent_message_list"
            :currentStreamingMessage="currentStreamingMessage"
            :isGenerating="isGenerating"
            :planStreamContent="chatPlanStreamForWindow"
            :planFoldAfterNonPlan="chatPlanFoldAfterNonPlan"
            :isLoading="isLoading"
            :timeoutError="timeoutError"
            :model_list="model_list"
            :userId="currentUserId"
            :username="currentUsername"
            :reloadStreamingUiToken="reloadStreamingUiToken"
            @sendMessage="handleSendMessage"
            @stopGeneration="stopGeneration"
            :class="{ 'compressed': showExtraInfo }"
            @highlight="highlightedId = $event"
            @unhighlight="highlightedId = null"
            @scrollTo="handleScrollTo($event)"
          />
        </div>

        <div 
          v-if="showExtraInfo" 
          class="resizer" 
          @mousedown="startResize"
          :class="{ 'resizing': isResizing }"
        ></div>

        <transition name="slide">
          <div v-if="showExtraInfo" class="extra-info-wrapper" :style="{ width: extraInfoWidth }">
            <ExtraInfo 
              class="extra-info-panel" 
              :toolMessages="toolMessages" 
              :fileMessages="fileMessages"
              :highlightedId="highlightedId" 
              :scrollToId="scrollToId" 
              :toggleTrigger="toggleTrigger" 
              :conversationId="chat_request.conversation_id || ''" 
            />
          </div>
        </transition>

        <button 
          v-if="toolMessages.length > 0" 
          @click="toggleExtraInfo" 
          class="info-button" 
          :class="{ 'shifted': showExtraInfo }"
          :style="showExtraInfo ? { right: extraInfoWidth } : {}"
        >
          <img src="@/assets/images/info_icon.svg" class="info-icon" />
        </button>
      </div>
      <ToolsOption
        v-if="showToolOption"
        @close="closeToolOption"
      />
      <SkillsOption
        v-if="showSkillOption"
        :userId="currentUserId"
        @close="closeSkillOption"
      />
      <KBOption
        v-if="showKBOption"
        @close="closeKBOption"
        :userId="currentUserId"
      />
      <AgentOption
        v-if="showAgentOption"
        @close="closeAgentOption"
        :userId="currentUserId"
        :username="currentUsername"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch, computed } from 'vue'
import axios from 'axios'
import ConversationWindow from '../components/ConversationWindow.vue'
import ChatWindow from '../components/ChatWindow.vue'
import ToolsOption from '../components/ToolsOption.vue'
import SkillsOption from '../components/SkillsOption.vue'
import KBOption from '../components/KBOption.vue'
import AgentOption from '../components/AgentOption.vue'
import ExtraInfo from '../components/ExtraInfo.vue'
import type { ConversationBase, ChatRequest, AgentMessage } from '../types/interface.ts'
import { AgentCard } from '../types/interface.ts'
import { useRouter } from 'vue-router'

const router = useRouter()

// ✅ 定义响应式变量并加类型
const conversation_list = ref<ConversationBase[]>([])
const agentname = ref<string>('萌芽')
const chat_request = ref<Partial<ChatRequest>>({})
const agent_message_list = ref<AgentMessage[]>([])
chat_request.value.tools_use = true
chat_request.value.skills_use = true
chat_request.value.agent_use = null
chat_request.value.agent_id = null
chat_request.value.agent_name = ''
// ✅ 新增：ToolsOption 相关状态
const showToolOption = ref<boolean>(false)
const showSkillOption = ref<boolean>(false)
const isLoading = ref<boolean>(false)
const isGenerating = ref<boolean>(false)
/** 当前轮次 plan 内容；流式结束后仍保留供折叠区展示，直至下一轮发送 */
const chatPlanStreamForWindow = ref('')
/** 主对话收到非 plan 类型分片时置 true，驱动 Plan 区立即折叠 */
const chatPlanFoldAfterNonPlan = ref(false)
/** 当前 SSE 请求内所有分片的 created_at（用于区分本轮与历史 toolMessages，避免跨轮合并 plan） */
const streamingSessionCreatedAt = ref<number | null>(null)
/** 收到 reload_history 时递增，驱动 ChatWindow 清空流式块并继续接收后续分片 */
const reloadStreamingUiToken = ref(0)
/** 当前轮 plan 流式段已结束；下一段 type=plan 到达时应先清掉本轮旧 plan 再写入 */
const planStreamSegmentEnded = ref(false)
const timeoutError = ref<string>('')
const isStreamEnded = ref<boolean>(false)  // 标记SSE流是否已结束
const abstract = ref<string>('')
const showKBOption = ref<boolean>(false)
const currentUserId = ref<string>('')

const currentUsername = ref<string>('')

// 新增函数：获取当前用户ID
async function fetchCurrentUserId(): Promise<void> {
  try {
    const response = await axios.get('/api/user/me')
    if (response.data.success) {
      currentUserId.value = response.data.user_id
      currentUsername.value = response.data.username
    } else {
      console.error('获取用户ID失败:', response.data)
      router.push('/')  // 如果失败，重定向到登录页
    }
  } catch (error) {
    console.error('获取用户ID失败:', error)
    router.push('/')
  }
}

const showAgentOption = ref<boolean>(false)

const model_list = ref<Record<string, string[]>>({})

// 与 MessageInput.vue 一致：先把后端返回对象转成 providers 结构
const modelProviders = computed(() => {
  return Object.entries(model_list.value).map(([providerName, models]) => ({
    model_source: providerName,
    models: models.map(model => ({
      id: model,
      name: model
    })),
  }))
})

function getFirstModelFromList() {
  const providers = modelProviders.value
  if (providers.length === 0 || providers[0].models.length === 0) return null
  const first = providers[0]
  return {
    model_source: first.model_source,
    model: first.models[0].id
  }
}

function applyFirstModelToChatRequest() {
  const firstModel = getFirstModelFromList()
  if (!firstModel) return
  chat_request.value.model_source = firstModel.model_source
  chat_request.value.model = firstModel.model
}

async function getLLMmodels(): Promise<void> {
  try {
    const response = await axios.get('/api/message/models')
    model_list.value = response.data
    applyFirstModelToChatRequest()
  } catch (error) {
    console.error('获取模型列表失败:', error)
    router.push('/')
  }
}


// ✅ 加类型的异步函数
async function fetchConversations(): Promise<void> {
  try {
    const response = await axios.get<ConversationBase[]>('/api/conversations')
    conversation_list.value = response.data
    if (conversation_list.value.length > 0) {
      currentUserId.value = conversation_list.value[0].user_id
    }
  } catch (error) {
    console.error('获取会话列表失败:', error)
    router.push('/')
  }
}

// 以下是交互处理方法（后续可完善逻辑）
function createConversation() {
  chat_request.value.conversation_id = ""
  chat_request.value.tools_use = true
  chat_request.value.skills_use = true
  applyFirstModelToChatRequest()
  chat_request.value.agent_use = null
  chat_request.value.agent_id = null
  chat_request.value.agent_name = ''
  chat_request.value.kb_use = []
  agent_message_list.value = []
  toolMessages.value = []
  fileMessages.value = []
  chatPlanStreamForWindow.value = ''
  chatPlanFoldAfterNonPlan.value = false
  currentStreamingMessage.value = null
  isGenerating.value = false
  // 重置流状态
  isStreamEnded.value = false
  messageQueue.value = []
}

async function deleteConversation(conversationId) {
  // 删除某个会话
  try {
    const response = await axios.delete('/api/conversations/' + conversationId)
    if (response.data.success) {
      // 成功删除后，重新获取会话列表
      await fetchConversations()
      agent_message_list.value = []
      chat_request.value.conversation_id = ""
      chat_request.value.agent_use = null
      chat_request.value.agent_id = null
      chat_request.value.agent_name = ''
      chat_request.value.tools_use = true
      chat_request.value.skills_use = true
      toolMessages.value = []
      fileMessages.value = []
      chatPlanStreamForWindow.value = ''
      chatPlanFoldAfterNonPlan.value = false
      currentStreamingMessage.value = null
      isGenerating.value = false
      // 重置流状态
      isStreamEnded.value = false
      messageQueue.value = []
    } else {
      console.error('会话删除失败:', response.data.code)
    }
  } catch (error) {
    console.error('删除失败:', error)
  }
}

/**
 * 解析消息 id：兼容字符串、数字，以及 Mongo Extended JSON 形态
 * 例如 id: { "$oid": "69da6b70cfb1c2128ee20eca" }
 */
function parseMessageId(raw: unknown): string | undefined {
  if (raw == null) return undefined
  if (typeof raw === 'string') {
    const s = raw.trim()
    return s.length ? s : undefined
  }
  if (typeof raw === 'number' && Number.isFinite(raw)) {
    return String(raw)
  }
  if (typeof raw === 'object') {
    const o = raw as Record<string, unknown>
    if (typeof o.$oid === 'string' && o.$oid.trim()) return o.$oid.trim()
    if (typeof o.oid === 'string' && o.oid.trim()) return o.oid.trim()
  }
  return undefined
}

/** 历史/刷新接口：为 role=user 的消息统一挂上 id（与后端 id 字段一致），供编辑重发使用 */
function normalizeMessagesFromApi(raw: AgentMessage[]): AgentMessage[] {
  if (!Array.isArray(raw)) return []
  return raw.map((m) => {
    if (m.role !== 'user') return m
    const row = m as AgentMessage & {
      input_message_id?: unknown
      _id?: unknown
    }
    const parsed =
      parseMessageId(row.id) ??
      parseMessageId(row.input_message_id) ??
      parseMessageId(row._id)
    if (parsed) {
      return { ...row, id: parsed }
    }
    return m
  })
}

/** 会话上缓存的蓝图注入 toolMessages（与原 cot_plan 行为一致；日后可单独改 blueprint 展示样式） */
function injectPersistedBlueprintToToolMessages(
  conversationId: string,
  blueprint: string | undefined | null,
) {
  if (blueprint == null || String(blueprint).trim() === '') return
  toolMessages.value.push({
    user_id: agent_message_list.value[0]?.user_id ?? '',
    conversation_id: conversationId,
    role: 'agent',
    created_at: Date.now(),
    type: 'plan',
    content: blueprint,
  })
}

async function refreshMessagesFromServer(conversationId: string) {
  if (!conversationId) return
  try {
    const response = await axios.get<AgentMessage[]>(`/api/message/${conversationId}`)
    const response_conversation = await axios.get(`/api/conversation/${conversationId}`)
    agent_message_list.value = normalizeMessagesFromApi(response.data)
    toolMessages.value = agent_message_list.value.filter(
      (msg) => (msg.role === 'tool' || msg.role === 'agent' || msg.type === 'get_tools') && msg.role !== 'file',
    )
    fileMessages.value = agent_message_list.value.filter((msg) => msg.role === 'file')
    injectPersistedBlueprintToToolMessages(
      conversationId,
      response_conversation.data.action_blueprint,
    )
    reloadStreamingUiToken.value++
  } catch (e) {
    console.error('reload_history 刷新消息失败:', e)
  }
}

async function updateConversationAbstract(conversationId: string, abstract: string) {
  try {
    const formData = new FormData()
    formData.append('abstract', abstract)
    await axios.post(`/api/conversation/${conversationId}`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    const target = conversation_list.value.find(
      (item) => item.conversation_id === conversationId,
    )
    if (target) {
      target.abstract = abstract
    }
  } catch (error) {
    console.error('更新对话摘要失败:', error)
  }
}

async function pickConversation(conversationId) {
  try {
    chatPlanStreamForWindow.value = ''
    chatPlanFoldAfterNonPlan.value = false
    const response = await axios.get<AgentMessage[]>(`/api/message/${conversationId}`)
    const response_conversation = await axios.get(`/api/conversation/${conversationId}`)
    agent_message_list.value = normalizeMessagesFromApi(response.data)
    // 设置toolMessages和fileMessages
    toolMessages.value = agent_message_list.value.filter(msg => (msg.role === 'tool' || msg.role === 'agent' || msg.type === 'get_tools') && msg.role !== 'file')
    fileMessages.value = agent_message_list.value.filter(msg => msg.role === 'file')
    injectPersistedBlueprintToToolMessages(
      conversationId,
      response_conversation.data.action_blueprint,
    )
    chat_request.value.conversation_id = conversationId
      chat_request.value.tools_use = response_conversation.data.tools_use
      chat_request.value.skills_use = response_conversation.data.skills_use ?? false
      chat_request.value.kb_use = response_conversation.data.kb_use
      const rawAgentUse = response_conversation.data.agent_use
      chat_request.value.agent_use = (rawAgentUse === 'single-agent' || rawAgentUse === 'multi-agent')
        ? 'expert-agent'
        : rawAgentUse
      chat_request.value.agent_id = response_conversation.data.agent_id ?? response_conversation.data.agent_name
      chat_request.value.agent_name = response_conversation.data.agent_name
      const firstModel = getFirstModelFromList()
      chat_request.value.model_source = response_conversation.data.model_source || firstModel?.model_source
      chat_request.value.model = response_conversation.data.model || firstModel?.model
  } catch (error) {
    console.error('获取消息失败:', error)
  }
}

const currentStreamingMessage = ref<AgentMessage | null>(null)

// 消息队列相关
const messageQueue = ref<any[]>([])
let isProcessingQueue = false

// 生成唯一ID的辅助函数
const generateId = () => `msg_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`

// 队列处理函数
async function processMessageQueue() {
  if (isProcessingQueue || messageQueue.value.length === 0) return

  isProcessingQueue = true
  // console.log('开始处理消息队列，队列长度:', messageQueue.value.length)

  while (messageQueue.value.length > 0) {
    const chunk_json = messageQueue.value.shift()
    // console.log('处理队列消息:', chunk_json.role, chunk_json.type, '剩余队列长度:', messageQueue.value.length)

    // 重新处理消息分类逻辑
    if (chunk_json.role === 'file') {
      // 文件消息单独处理，不添加到 toolMessages
      const fileMessage = {
        user_id: chunk_json.user_id,
        conversation_id: chunk_json.conversation_id,
        type: chunk_json.type || 'read',
        role: chunk_json.role,
        content: chunk_json.content || '',
        tool_call_id: chunk_json.tool_call_id,
        tool_calls: chunk_json.tool_calls,
        created_at: chunk_json.created_at,
        table: chunk_json.json_table || chunk_json.table // 支持 json_table 字段
      }
      fileMessages.value.push(fileMessage)
      if (!showExtraInfo.value) {
        showExtraInfo.value = true
      }
    } else if (chunk_json.role === 'tool' || chunk_json.role === 'agent' || chunk_json.type === 'plan') {
      const canMerge = ['text', 'reasoner_content', 'plan'].includes(chunk_json.type)
      let lastMsg = toolMessages.value[toolMessages.value.length - 1]
      let shouldAppend = canMerge && lastMsg &&
        lastMsg.tool_call_id === chunk_json.tool_call_id &&
        lastMsg.type === (chunk_json.type || 'tool') &&
        lastMsg.created_at === chunk_json.created_at

      if (chunk_json.type === 'plan') {
        const batchAt = streamingSessionCreatedAt.value
        if (batchAt != null) {
          const mustClear = planStreamSegmentEnded.value || !shouldAppend
          if (mustClear) {
            if (planStreamSegmentEnded.value) planStreamSegmentEnded.value = false
            toolMessages.value = toolMessages.value.filter(
              (m) => !(m.type === 'plan' && m.created_at === batchAt)
            )
            chatPlanStreamForWindow.value = ''
            lastMsg = toolMessages.value[toolMessages.value.length - 1]
            shouldAppend = canMerge && !!lastMsg &&
              lastMsg.tool_call_id === chunk_json.tool_call_id &&
              lastMsg.type === (chunk_json.type || 'tool') &&
              lastMsg.created_at === chunk_json.created_at
          }
        }
      }

      if (shouldAppend) {
        lastMsg.content = (lastMsg.content || '') + (chunk_json.content || '')
      } else {
        toolMessages.value.push({
          user_id: chunk_json.user_id,
          conversation_id: chunk_json.conversation_id,
          type: chunk_json.type || 'tool',
          role: chunk_json.role,
          content: chunk_json.content || '',
          tool_call_id: chunk_json.tool_call_id,
          tool_calls: chunk_json.tool_calls,
          created_at: chunk_json.created_at
        })
      }
      if (chunk_json.type === 'plan') {
        const lastPlan = toolMessages.value[toolMessages.value.length - 1]
        if (lastPlan && lastPlan.type === 'plan') {
          chatPlanStreamForWindow.value = lastPlan.content || ''
        }
      }
      if (!showExtraInfo.value && chunk_json.type !== 'plan') {
        showExtraInfo.value = true
      }
    } else {
      const t = chunk_json.type
      if (chatPlanStreamForWindow.value && t !== 'plan' && t !== 'init') {
        chatPlanFoldAfterNonPlan.value = true
      }
      // 创建新的对象引用，确保Vue能检测到变化
      currentStreamingMessage.value = {
        user_id: chunk_json.user_id,
        conversation_id: chunk_json.conversation_id,
        type: chunk_json.type,
        role: chunk_json.role,
        content: chunk_json.content || '',
        tool_call_id: chunk_json.tool_call_id || '',
        tool_calls: chunk_json.tool_calls || undefined,
        created_at: chunk_json.created_at
      }
    }

    if (chunk_json.type === 'get_tools' && chunk_json.role === 'assistant') {
      // console.log('额外添加 get_tools 消息到 toolMessages')
      toolMessages.value.push({
        user_id: chunk_json.user_id || '',
        conversation_id: chunk_json.conversation_id || '',
        type: chunk_json.type,
        role: chunk_json.role,
        content: chunk_json.content || '',
        tool_call_id: chunk_json.tool_call_id || '',
        tool_calls: chunk_json.tool_calls || undefined,
        created_at: chunk_json.created_at
      })
    }

    applyPlanStreamSegmentEndedMarker(chunk_json)

    // 每个消息处理后让出线程给 Vue 再渲染（避免阻塞），但不要依赖 setTimeout（隐藏标签页会被节流）
    await Promise.resolve()
    // // 每个消息处理后等待一帧，让Vue有时间更新UI
    // await new Promise(resolve => setTimeout(resolve, 0))
  }

  isProcessingQueue = false
  // console.log('消息队列处理完成')
  // 检查是否需要清理：流已结束且队列已空
  if (isStreamEnded.value && messageQueue.value.length === 0) {
  // console.log('SSE流结束且队列处理完成，开始清理')
  isGenerating.value = false
  isStreamEnded.value = false
  currentStreamingMessage.value = null
  delete chat_request.value.input_message_id
  const at = streamingSessionCreatedAt.value
  if (at != null) {
    const last = toolMessages.value[toolMessages.value.length - 1]
    if (last?.type === 'plan' && last?.created_at === at) {
      planStreamSegmentEnded.value = true
    }
  }
  }
}

const abortController = ref<AbortController | null>(null)

const toolMessages = ref<AgentMessage[]>([])
const fileMessages = ref<AgentMessage[]>([]) // 文件消息列表

/** 在 plan 段输出结束后打标，便于下一段 plan 清除本轮旧块而非追加 */
function applyPlanStreamSegmentEndedMarker(chunk_json: { type?: string }) {
  if (streamingSessionCreatedAt.value == null) return
  if (chunk_json.type === 'plan') return
  if (chunk_json.type === 'init' || chunk_json.type === 'abstract') return
  const batchAt = streamingSessionCreatedAt.value
  const hasBatchPlan = toolMessages.value.some(
    (m) => m.type === 'plan' && m.created_at === batchAt
  )
  if (hasBatchPlan || chatPlanStreamForWindow.value) {
    planStreamSegmentEnded.value = true
  }
}

const highlightedId = ref<string | null>(null)

const scrollToId = ref<string | null>(null)

const toggleTrigger = ref<number>(0)

async function handleSendMessage(
  message: string,
  files: File[] = [],
  options?: { input_message_id?: string },
) {
  isGenerating.value = true
  isStreamEnded.value = false  // 重置流结束标志
  chatPlanStreamForWindow.value = ''
  chatPlanFoldAfterNonPlan.value = false
  planStreamSegmentEnded.value = false
  chat_request.value.message = message
  chat_request.value.files = files
  if (options?.input_message_id) {
    chat_request.value.input_message_id = options.input_message_id
  } else {
    delete chat_request.value.input_message_id
  }
  
  // 重置状态
  isLoading.value = true
  timeoutError.value = ''
  
  // 创建AI回复的流式消息对象
  currentStreamingMessage.value = {
    user_id: '',
    conversation_id: '',
    type: 'init',
    role: 'assistant', 
    content: '',
    tool_call_id: '',
    tool_calls: undefined,
    created_at: Date.now() 
  }

  let buffer = ''
  let timeoutId: ReturnType<typeof setTimeout> | null = null
  
  // 设置30秒超时
  const setupTimeout = () => {
    if (timeoutId) clearTimeout(timeoutId)
    timeoutId = setTimeout(() => {
      isLoading.value = false
      timeoutError.value = '请求超时，请刷新重试 ⏰'
      console.error('请求超时')
      // 中止请求
      if (abortController.value) {
        abortController.value.abort()
      }
    }, 1800000)
  }
  
  // 清除超时
  const clearTimeoutHandler = () => {
    if (timeoutId) {
      clearTimeout(timeoutId)
      timeoutId = null
    }
  }
  
  setupTimeout() // 开始计时
  try {
    abortController.value = new AbortController()
    const formData = new FormData();
    // 传递 agent_id 而非 agent_name
    const payload = { ...chat_request.value }
    if (payload.agent_id) delete payload.agent_name
    if (options?.input_message_id) {
      payload.input_message_id = options.input_message_id
    } else {
      delete payload.input_message_id
    }
    formData.append('chat_request', JSON.stringify(payload));
    files.forEach(file => formData.append('files', file));
    const response = await fetch('/api/message/chat', {
      method: 'POST',
      body: formData,
      headers: {
        'Accept': 'text/event-stream',
        'Cache-Control': 'no-cache'
      },
      cache: 'no-store',
      signal: abortController.value.signal
    })

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`)
    }

    if (!response.body) {
      throw new Error('没有返回流')
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder('utf-8')
    const created_at_time = Date.now()
    streamingSessionCreatedAt.value = created_at_time
    
    try {
      while (true) {
        const { value, done } = await reader.read()
        
        if (done) {
          break
        }

        if (value) {
          // 收到数据，重置超时计时器并清除错误
          clearTimeoutHandler()
          setupTimeout()
          if (timeoutError.value) {
            timeoutError.value = ''  // 清除可能的超时错误
          }
          
          buffer += decoder.decode(value, { stream: true })
          const lines = buffer.split('\n')
          buffer = lines.pop() || ''
          
          for (const line of lines) {
            const trimmedLine = line.trim()
            // SSE格式: data: {json_data}
            if (trimmedLine.startsWith('data: ')) {
              const data = trimmedLine.substring(6).trim() // 移除 'data: ' 前缀
              if (!data) continue

              try {
                const chunk_json = JSON.parse(data)
                chunk_json.created_at = created_at_time

                if (chunk_json.type === 'input_message_id') {
                  const mid = parseMessageId(chunk_json.content)
                  if (mid) {
                    for (let i = agent_message_list.value.length - 1; i >= 0; i--) {
                      const m = agent_message_list.value[i]
                      if (m.role === 'user' && !m.id) {
                        m.id = mid
                        break
                      }
                    }
                  }
                  continue
                }

                if (chunk_json.type === 'reload_history') {
                  const cid =
                    chunk_json.conversation_id || chat_request.value.conversation_id || ''
                  if (cid) {
                    await refreshMessagesFromServer(cid)
                  }
                  continue
                }

                // 如果type是'text'，隐藏loading
                if (chunk_json.type === 'text' || chunk_json.type === 'reasoner_content') {
                  isLoading.value = false
                } else if (chunk_json.type === 'abstract') {
                  // 优先更新会话列表，再进行流式输出
                   abstract.value = chunk_json.content
                  chat_request.value.conversation_id = chunk_json.conversation_id
                  conversation_list.value.unshift({
                    user_id: chunk_json.user_id,
                    conversation_id: chunk_json.conversation_id, 
                    abstract: abstract.value, 
                    create_at: "",
                    updated_at: "", 
                  })
                }
                
                // 将消息添加到队列中顺序处理
                // console.log('添加消息到队列:', chunk_json.role, chunk_json.type, '内容:', chunk_json.content?.substring(0, 50))
                messageQueue.value.push(chunk_json)
                processMessageQueue()
              } catch (error) {
                console.error('解析 JSON 失败:', error, '原始数据:', data)
              }
            }
          }
        }
      }
    } finally {
      reader.releaseLock()
      clearTimeoutHandler()  // 流结束时清除计时器
      abortController.value = null
      
      // 标记流已结束，但不立即清理队列
      isStreamEnded.value = true

      // 如果队列已经处理完，立即清理
      if (!isProcessingQueue && messageQueue.value.length === 0) {
        isGenerating.value = false
        isStreamEnded.value = false
        currentStreamingMessage.value = null
        chat_request.value.files = []  // 清理 files
        delete chat_request.value.input_message_id
      }
    }

    if (currentStreamingMessage.value) {
      currentStreamingMessage.value = null
    }
    
    // 注意：不要立即清空streamingContent，让用户看到完整响应
    // streamingContent.value = ''
  }
   catch (error) {
    if (error.name === 'AbortError') {
      timeoutError.value = '生成已停止'
    } else {
      console.error('流式消息失败:', error)
      timeoutError.value = '请求失败，请重试'
    }
    isLoading.value = false
    currentStreamingMessage.value = null
    clearTimeoutHandler()
    isGenerating.value = false
    isStreamEnded.value = false
    messageQueue.value = []  // 停止时清空队列
    chat_request.value.files = []  // 清理 files
    delete chat_request.value.input_message_id
  }
}

function stopGeneration() {
  if (abortController.value) {
    abortController.value.abort()
    abortController.value = null
  }
  isLoading.value = false
  currentStreamingMessage.value = null
  timeoutError.value = '生成已停止'
  isGenerating.value = false
  delete chat_request.value.input_message_id
}

const isExpanded = ref(false)

function SidebarChange() {
  isExpanded.value = !isExpanded.value
}

// ✅ 新增：ToolsOption 相关方法
function openToolOption() {
  showToolOption.value = true
}

function closeToolOption() {
  showToolOption.value = false
}

function openSkillOption() {
  showSkillOption.value = true
}

function closeSkillOption() {
  showSkillOption.value = false
}

function openKBOption() {
  showKBOption.value = true
}

function closeKBOption() {
  showKBOption.value = false
}

function openAgentOption() {
  showAgentOption.value = true
}

function closeAgentOption() {
  showAgentOption.value = false
}

const showExtraInfo = ref<boolean>(false)

// 拖拽调整大小相关状态
const isResizing = ref(false)
const chatWindowWidth = ref('60%')
const extraInfoWidth = ref('40%')
const minChatWidth = 300 // 最小宽度（像素）
const minExtraWidth = 250 // 最小宽度（像素）

// 从 localStorage 加载保存的宽度
function loadSavedWidths() {
  const savedChatWidth = localStorage.getItem('chatWindowWidth')
  const savedExtraWidth = localStorage.getItem('extraInfoWidth')
  if (savedChatWidth && savedExtraWidth) {
    chatWindowWidth.value = savedChatWidth
    extraInfoWidth.value = savedExtraWidth
  }
}

// 保存宽度到 localStorage
function saveWidths() {
  localStorage.setItem('chatWindowWidth', chatWindowWidth.value)
  localStorage.setItem('extraInfoWidth', extraInfoWidth.value)
}

// 开始拖拽调整大小
function startResize(e: MouseEvent) {
  e.preventDefault()
  e.stopPropagation()
  isResizing.value = true
  
  // 禁用文本选择
  document.body.style.userSelect = 'none'
  document.body.style.cursor = 'col-resize'
  
  const chatMain = document.querySelector('.chat-main') as HTMLElement
  if (!chatMain) return
  
  const chatMainWidth = chatMain.clientWidth
  const startX = e.clientX
  const startChatWidth = parseFloat(chatWindowWidth.value) / 100 * chatMainWidth
  
  function handleMouseMove(e: MouseEvent) {
    if (!isResizing.value) return
    e.preventDefault()
    
    const deltaX = e.clientX - startX
    const newChatWidth = startChatWidth + deltaX
    const newExtraWidth = chatMainWidth - newChatWidth
    
    // 限制最小宽度
    if (newChatWidth >= minChatWidth && newExtraWidth >= minExtraWidth) {
      const chatPercent = (newChatWidth / chatMainWidth) * 100
      const extraPercent = (newExtraWidth / chatMainWidth) * 100
      chatWindowWidth.value = `${chatPercent}%`
      extraInfoWidth.value = `${extraPercent}%`
    }
  }
  
  function handleMouseUp() {
    isResizing.value = false
    // 恢复文本选择
    document.body.style.userSelect = ''
    document.body.style.cursor = ''
    saveWidths()
    document.removeEventListener('mousemove', handleMouseMove)
    document.removeEventListener('mouseup', handleMouseUp)
  }
  
  document.addEventListener('mousemove', handleMouseMove)
  document.addEventListener('mouseup', handleMouseUp)
}

watch(toolMessages, () => {
  if (toolMessages.value.length === 0) {
    showExtraInfo.value = false
  }
}, { deep: true })

function toggleExtraInfo() {
  showExtraInfo.value = !showExtraInfo.value
  if (showExtraInfo.value) {
    // 恢复保存的宽度
    loadSavedWidths()
  }
}

const handleScrollTo = (id: string) => {
  if (scrollToId.value === id) {
    toggleTrigger.value++
  } else {
    scrollToId.value = id
  }
}

// 处理窗口大小改变
function handleResize() {
  if (!showExtraInfo.value) return
  
  const chatMain = document.querySelector('.chat-main') as HTMLElement
  if (!chatMain) return
  
  const chatMainWidth = chatMain.clientWidth
  const chatPercent = parseFloat(chatWindowWidth.value)
  const extraPercent = parseFloat(extraInfoWidth.value)
  
  // 检查最小宽度限制
  const chatWidthPx = (chatPercent / 100) * chatMainWidth
  const extraWidthPx = (extraPercent / 100) * chatMainWidth
  
  if (chatWidthPx < minChatWidth) {
    chatWindowWidth.value = `${(minChatWidth / chatMainWidth) * 100}%`
    extraInfoWidth.value = `${((chatMainWidth - minChatWidth) / chatMainWidth) * 100}%`
    saveWidths()
  } else if (extraWidthPx < minExtraWidth) {
    extraInfoWidth.value = `${(minExtraWidth / chatMainWidth) * 100}%`
    chatWindowWidth.value = `${((chatMainWidth - minExtraWidth) / chatMainWidth) * 100}%`
    saveWidths()
  }
}

// ✅ 生命周期中调用
onMounted(() => {
  fetchCurrentUserId()  // 先获取 userId
  fetchConversations()  // 然后获取会话列表
  getLLMmodels()
  loadSavedWidths()  // 加载保存的宽度设置
  window.addEventListener('resize', handleResize)
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
})
</script>

<style scoped>
@import '@/assets/css/chat.css';
</style>

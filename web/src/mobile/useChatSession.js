import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'
import { apiFetch, http } from './api'

const SOUL_MESSAGE_PAGE_SIZE = 120

/**
 * 手机端对话会话。请求和流式处理与网页 Chat.vue 对齐，
 * 但不渲染工具 / 技能 / 知识库 / 专家，也不改网页上的页面。
 */
export function useChatSession() {
  const { t } = useI18n()

  const conversation_list = ref([])
  const chat_request = ref({})
  const agent_message_list = ref([])
  const chatMode = ref('soulprout')
  const soulMessagesHasMore = ref(false)
  const soulMessagesLoadingMore = ref(false)
  const welcomeAnimationToken = ref(0)
  const cachedTaskChatRequest = ref(null)
  const isLoading = ref(false)
  const isGenerating = ref(false)
  const chatPlanStreamForWindow = ref('')
  const chatPlanProgressForWindow = ref('')
  const blueprintAwaitingResult = ref(false)
  const blueprintToolCallId = ref('')
  const blueprintStreamPending = computed(() => blueprintAwaitingResult.value)
  const streamingSessionCreatedAt = ref(null)
  const reloadStreamingUiToken = ref(0)
  const planStreamSegmentEnded = ref(false)
  const timeoutError = ref('')
  const isStreamEnded = ref(false)
  const abstract = ref('')
  const currentUserId = ref('')
  const currentUsername = ref('')
  const model_list = ref({})
  const runningConversations = ref([])
  const currentStreamingMessage = ref(null)
  const messageQueue = ref([])
  const toolMessages = ref([])
  const fileMessages = ref([])
  const ready = ref(false)
  const unauthorized = ref(false)

  let isProcessingQueue = false
  const abortController = ref(null)
  let streamEpoch = 0
  let runsAbortController = null

  chat_request.value.tools_use = true
  chat_request.value.skills_use = true
  chat_request.value.agent_use = null
  chat_request.value.agent_id = null
  chat_request.value.agent_name = ''

  const taskConversationList = computed(() =>
    conversation_list.value.filter(
      (item) => item.agent_use !== 'soulprout' && item.conversation_id !== currentUserId.value,
    ),
  )

  const modelProviders = computed(() =>
    Object.entries(model_list.value).map(([providerName, models]) => ({
      model_source: providerName,
      models: (models || []).map((model) => ({ id: model, name: model })),
    })),
  )

  function getFirstModelFromList() {
    const providers = modelProviders.value
    if (providers.length === 0 || providers[0].models.length === 0) return null
    const first = providers[0]
    return { model_source: first.model_source, model: first.models[0].id }
  }

  function applyFirstModelToChatRequest() {
    const firstModel = getFirstModelFromList()
    if (!firstModel) return
    chat_request.value.model_source = firstModel.model_source
    chat_request.value.model = firstModel.model
  }

  async function fetchCurrentUserId() {
    try {
      const response = await http.get('/api/user/me')
      if (response.data.success) {
        currentUserId.value = response.data.user_id
        currentUsername.value = response.data.username
        return true
      }
    } catch (error) {
      console.error('获取用户失败:', error)
    }
    unauthorized.value = true
    return false
  }

  async function getLLMmodels() {
    try {
      const response = await http.get('/api/message/models')
      model_list.value = response.data
      applyFirstModelToChatRequest()
    } catch (error) {
      console.error('获取模型列表失败:', error)
    }
  }

  async function fetchConversations() {
    try {
      const response = await http.get('/api/conversations')
      conversation_list.value = response.data
      if (conversation_list.value.length > 0 && !currentUserId.value) {
        currentUserId.value = conversation_list.value[0].user_id
      }
    } catch (error) {
      console.error('获取会话列表失败:', error)
    }
  }

  function detachLocalStream() {
    streamEpoch += 1
    if (abortController.value) {
      abortController.value.abort()
      abortController.value = null
    }
    messageQueue.value = []
  }

  function detachRunsStream() {
    if (runsAbortController) {
      runsAbortController.abort()
      runsAbortController = null
    }
  }

  function createConversation() {
    detachLocalStream()
    isGenerating.value = false
    chat_request.value.conversation_id = ''
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
    chatPlanProgressForWindow.value = ''
    blueprintAwaitingResult.value = false
    blueprintToolCallId.value = ''
    currentStreamingMessage.value = null
    isStreamEnded.value = false
    messageQueue.value = []
  }

  function parseMessageId(raw) {
    if (raw == null) return undefined
    if (typeof raw === 'string') {
      const s = raw.trim()
      return s.length ? s : undefined
    }
    if (typeof raw === 'number' && Number.isFinite(raw)) return String(raw)
    if (typeof raw === 'object') {
      if (typeof raw.$oid === 'string' && raw.$oid.trim()) return raw.$oid.trim()
      if (typeof raw.oid === 'string' && raw.oid.trim()) return raw.oid.trim()
    }
    return undefined
  }

  function normalizeMessagesFromApi(raw) {
    if (!Array.isArray(raw)) return []
    return raw.map((m) => {
      if (m.role !== 'user') return m
      const parsed = parseMessageId(m.id) ?? parseMessageId(m.input_message_id) ?? parseMessageId(m._id)
      if (parsed) return { ...m, id: parsed }
      return m
    })
  }

  function messageCreatedAtMs(msg) {
    const created = msg.created_at
    if (typeof created === 'number' && Number.isFinite(created)) return created
    const text = String(created)
    const hasZone = /(Z|[+-]\d{2}:?\d{2})$/i.test(text)
    return new Date(hasZone ? text : `${text}Z`).getTime()
  }

  function isToolSidebarMessage(msg) {
    if (msg.role === 'file') return false
    if (msg.type === 'user_feedback') return false
    return msg.role === 'tool' || msg.role === 'agent' || msg.type === 'get_tools' || msg.type === 'get_agents'
  }

  function applyMessageListsFromApi(messages) {
    agent_message_list.value = messages
    toolMessages.value = messages.filter(isToolSidebarMessage)
    fileMessages.value = messages.filter((msg) => msg.role === 'file')
  }

  function injectPersistedBlueprintToToolMessages(conversationId, blueprint) {
    if (blueprint == null || String(blueprint).trim() === '') return
    const already = agent_message_list.value.some((m) => m.type === 'plan' && m.content === blueprint)
    if (already) return
    agent_message_list.value.push({
      user_id: agent_message_list.value[0]?.user_id ?? '',
      conversation_id: conversationId,
      role: 'assistant',
      created_at: Date.now(),
      type: 'plan',
      content: blueprint,
    })
  }

  function bumpWelcomeIfEmpty() {
    if (
      agent_message_list.value.length === 0 &&
      !currentStreamingMessage.value &&
      !chatPlanStreamForWindow.value
    ) {
      welcomeAnimationToken.value += 1
    }
  }

  async function loadSoulproutConversation() {
    const userId = currentUserId.value
    chat_request.value = {
      conversation_id: userId || '',
      agent_use: 'soulprout',
      agent_id: null,
      agent_name: null,
      tools_use: true,
      skills_use: true,
      kb_use: [],
    }
    chatPlanStreamForWindow.value = ''
    chatPlanProgressForWindow.value = ''
    blueprintAwaitingResult.value = false
    blueprintToolCallId.value = ''
    currentStreamingMessage.value = null
    agent_message_list.value = []
    toolMessages.value = []
    fileMessages.value = []
    if (!userId) return

    try {
      const response = await http.get(`/api/message/${userId}`, {
        params: { limit: SOUL_MESSAGE_PAGE_SIZE },
      })
      const messages = normalizeMessagesFromApi(response.data)
      soulMessagesHasMore.value = messages.length >= SOUL_MESSAGE_PAGE_SIZE
      applyMessageListsFromApi(messages)
    } catch (error) {
      console.debug('灵芽会话尚未建立或拉取失败：', error)
      soulMessagesHasMore.value = false
    }
    // 会话流是一直保持的长连接，不能 await，否则「进入中」永远不会结束
    void attachConversationStream(userId)
  }

  async function loadMoreSoulMessages() {
    const userId = currentUserId.value
    if (
      chatMode.value !== 'soulprout' ||
      !userId ||
      !soulMessagesHasMore.value ||
      soulMessagesLoadingMore.value ||
      agent_message_list.value.length === 0
    ) {
      return
    }
    const first = agent_message_list.value[0]
    if (!first) return

    soulMessagesLoadingMore.value = true
    try {
      const response = await http.get(`/api/message/${userId}`, {
        params: { limit: SOUL_MESSAGE_PAGE_SIZE, before: messageCreatedAtMs(first) },
      })
      const older = normalizeMessagesFromApi(response.data)
      soulMessagesHasMore.value = older.length >= SOUL_MESSAGE_PAGE_SIZE
      applyMessageListsFromApi([...older, ...agent_message_list.value])
    } catch (error) {
      console.error('加载更多灵芽历史失败:', error)
    } finally {
      soulMessagesLoadingMore.value = false
    }
  }

  async function handleSwitchMode(mode) {
    if (mode === chatMode.value) return
    detachLocalStream()
    isGenerating.value = false
    currentStreamingMessage.value = null
    if (mode === 'soulprout') {
      cachedTaskChatRequest.value = { ...chat_request.value }
      chatMode.value = 'soulprout'
      await loadSoulproutConversation()
    } else {
      chatMode.value = 'task'
      if (cachedTaskChatRequest.value) {
        chat_request.value = { ...cachedTaskChatRequest.value }
        cachedTaskChatRequest.value = null
      } else {
        createConversation()
      }
      agent_message_list.value = []
      toolMessages.value = []
      fileMessages.value = []
      chatPlanStreamForWindow.value = ''
      chatPlanProgressForWindow.value = ''
      blueprintAwaitingResult.value = false
      blueprintToolCallId.value = ''
      currentStreamingMessage.value = null
      if (chat_request.value.conversation_id) {
        await pickConversation(chat_request.value.conversation_id)
      }
    }
    bumpWelcomeIfEmpty()
  }

  async function deleteConversation(conversationId) {
    try {
      detachLocalStream()
      isGenerating.value = false
      try {
        await http.post('/api/message/stop', { conversation_id: conversationId })
      } catch (error) {
        console.debug('停止会话失败：', error)
      }
      const response = await http.delete('/api/conversations/' + conversationId)
      if (response.data.success) {
        await fetchConversations()
        agent_message_list.value = []
        chat_request.value.conversation_id = ''
        chat_request.value.agent_use = null
        chat_request.value.agent_id = null
        chat_request.value.agent_name = ''
        chat_request.value.tools_use = true
        chat_request.value.skills_use = true
        toolMessages.value = []
        fileMessages.value = []
        chatPlanStreamForWindow.value = ''
        currentStreamingMessage.value = null
        isStreamEnded.value = false
        messageQueue.value = []
      }
    } catch (error) {
      console.error('删除失败:', error)
    }
  }

  async function refreshMessagesFromServer(conversationId) {
    if (!conversationId) return
    try {
      const response = await http.get(`/api/message/${conversationId}`)
      const responseConversation = await http.get(`/api/conversation/${conversationId}`)
      applyMessageListsFromApi(normalizeMessagesFromApi(response.data))
      injectPersistedBlueprintToToolMessages(conversationId, responseConversation.data.action_blueprint)
      if (chatMode.value === 'soulprout') soulMessagesHasMore.value = false
      reloadStreamingUiToken.value++
    } catch (error) {
      console.error('刷新消息失败:', error)
    }
  }

  async function updateConversationAbstract(conversationId, nextAbstract) {
    try {
      const formData = new FormData()
      formData.append('abstract', nextAbstract)
      await http.post(`/api/conversation/${conversationId}`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      const target = conversation_list.value.find((item) => item.conversation_id === conversationId)
      if (target) target.abstract = nextAbstract
    } catch (error) {
      console.error('更新对话摘要失败:', error)
    }
  }

  async function pickConversation(conversationId) {
    try {
      detachLocalStream()
      isGenerating.value = false
      currentStreamingMessage.value = null
      chatPlanStreamForWindow.value = ''
      chatPlanProgressForWindow.value = ''
      blueprintAwaitingResult.value = false
      blueprintToolCallId.value = ''
      const response = await http.get(`/api/message/${conversationId}`)
      const responseConversation = await http.get(`/api/conversation/${conversationId}`)
      agent_message_list.value = normalizeMessagesFromApi(response.data)
      toolMessages.value = agent_message_list.value.filter(isToolSidebarMessage)
      fileMessages.value = agent_message_list.value.filter((msg) => msg.role === 'file')
      injectPersistedBlueprintToToolMessages(conversationId, responseConversation.data.action_blueprint)
      chat_request.value.conversation_id = conversationId
      chat_request.value.tools_use = responseConversation.data.tools_use
      chat_request.value.skills_use = responseConversation.data.skills_use ?? false
      chat_request.value.kb_use = responseConversation.data.kb_use
      const rawAgentUse = responseConversation.data.agent_use
      chat_request.value.agent_use =
        rawAgentUse === 'single-agent' || rawAgentUse === 'multi-agent' ? 'expert-agent' : rawAgentUse
      chat_request.value.agent_id = responseConversation.data.agent_id ?? responseConversation.data.agent_name
      chat_request.value.agent_name = responseConversation.data.agent_name
      const firstModel = getFirstModelFromList()
      chat_request.value.model_source = responseConversation.data.model_source || firstModel?.model_source
      chat_request.value.model = responseConversation.data.model || firstModel?.model
      void attachConversationStream(conversationId)
    } catch (error) {
      console.error('获取消息失败:', error)
    }
  }

  function commitPlanStreamToHistory() {
    const content = (chatPlanStreamForWindow.value || '').trim()
    if (!content) return
    const already = agent_message_list.value.some((m) => m.type === 'plan' && m.content === content)
    if (already) return
    agent_message_list.value.push({
      user_id: currentUserId.value || '',
      conversation_id: chat_request.value.conversation_id || '',
      role: 'assistant',
      created_at: Date.now(),
      type: 'plan',
      content,
    })
  }

  function applyPlanStreamSegmentEndedMarker(chunk) {
    if (streamingSessionCreatedAt.value == null) return
    if (chunk.type === 'plan' || chunk.type === 'plan_progress') return
    if (chunk.type === 'init' || chunk.type === 'abstract') return
    const batchAt = streamingSessionCreatedAt.value
    const hasBatchPlan = toolMessages.value.some((m) => m.type === 'plan' && m.created_at === batchAt)
    if (hasBatchPlan || chatPlanStreamForWindow.value) planStreamSegmentEnded.value = true
  }

  async function handleControlChunk(chunk) {
    const kind = chunk?.type
    if (kind === 'accepted') {
      if (chunk.conversation_id) chat_request.value.conversation_id = chunk.conversation_id
      isGenerating.value = true
      return true
    }
    if (kind === 'turn_started') {
      if (currentStreamingMessage.value) {
        currentStreamingMessage.value = null
        await nextTick()
      }
      isGenerating.value = true
      isLoading.value = true
      return true
    }
    if (kind === 'snapshot') {
      if (!chunk.running && !chunk.content && !chunk.reasoning_content && !chunk.plan) return true
      isGenerating.value = true
      isLoading.value = !chunk.content
      if (chunk.plan_progress) chatPlanProgressForWindow.value = chunk.plan_progress
      if (chunk.plan) chatPlanStreamForWindow.value = chunk.plan
      if (chunk.reasoning_content) {
        currentStreamingMessage.value = {
          user_id: chunk.user_id || '',
          conversation_id: chunk.conversation_id || '',
          type: 'reasoner_content',
          role: 'assistant',
          content: chunk.reasoning_content,
          created_at: chunk.created_at,
        }
        await nextTick()
      }
      if (chunk.content) {
        currentStreamingMessage.value = {
          user_id: chunk.user_id || '',
          conversation_id: chunk.conversation_id || '',
          type: 'text',
          role: 'assistant',
          content: chunk.content,
          created_at: chunk.created_at,
        }
        await nextTick()
      }
      return true
    }
    if (kind === 'user_message') {
      const content = chunk.content || ''
      let pending = null
      for (let i = agent_message_list.value.length - 1; i >= 0; i--) {
        const message = agent_message_list.value[i]
        if (message.role === 'user' && (message.type === 'text' || message.type === 'user_feedback')) {
          pending = message
          break
        }
      }
      if (pending && !pending.id && (pending.content || '') === content) return true
      if (currentStreamingMessage.value) {
        currentStreamingMessage.value = null
        await nextTick()
      }
      agent_message_list.value.push({
        user_id: chunk.user_id || '',
        conversation_id: chunk.conversation_id || chat_request.value.conversation_id || '',
        type: 'text',
        role: 'user',
        content,
        created_at: chunk.created_at || Date.now(),
      })
      return true
    }
    if (kind === 'interrupted') {
      if (currentStreamingMessage.value) {
        currentStreamingMessage.value = null
        await nextTick()
      }
      isGenerating.value = true
      return true
    }
    if (kind === 'turn_done' || kind === 'stopped') {
      currentStreamingMessage.value = null
      await nextTick()
      isGenerating.value = false
      isLoading.value = false
      if (kind === 'stopped') timeoutError.value = t('chat.stopped')
      commitPlanStreamToHistory()
      chatPlanStreamForWindow.value = ''
      chatPlanProgressForWindow.value = ''
      blueprintAwaitingResult.value = false
      delete chat_request.value.input_message_id
      delete chat_request.value.user_feedback
      return true
    }
    return false
  }

  async function processMessageQueue() {
    if (isProcessingQueue || messageQueue.value.length === 0) return
    isProcessingQueue = true

    while (messageQueue.value.length > 0) {
      const chunk = messageQueue.value.shift()
      if (!chunk || (await handleControlChunk(chunk))) continue

      if (chunk.role === 'user' && chunk.type === 'file') {
        const fileContent = chunk.content || ''
        const last = agent_message_list.value[agent_message_list.value.length - 1]
        const isDuplicate =
          last?.role === 'user' && last?.type === 'file' && (last.content || '') === fileContent
        if (!isDuplicate) {
          agent_message_list.value.push({
            user_id: chunk.user_id,
            conversation_id: chunk.conversation_id,
            type: 'file',
            role: 'user',
            content: fileContent,
            table: chunk.json_table,
            created_at: chunk.created_at,
          })
        }
        continue
      }

      if (chunk.role === 'file') {
        fileMessages.value.push({
          user_id: chunk.user_id,
          conversation_id: chunk.conversation_id,
          type: chunk.type || 'read',
          role: chunk.role,
          content: chunk.content || '',
          tool_call_id: chunk.tool_call_id,
          tool_calls: chunk.tool_calls,
          created_at: chunk.created_at,
          table: chunk.json_table || chunk.table,
        })
      } else if (chunk.type === 'user_feedback') {
        if (chatPlanStreamForWindow.value && chunk.type !== 'plan' && chunk.type !== 'init' && chunk.type !== 'plan_progress') {
          commitPlanStreamToHistory()
          chatPlanStreamForWindow.value = ''
        }
        currentStreamingMessage.value = {
          user_id: chunk.user_id,
          conversation_id: chunk.conversation_id,
          type: 'user_feedback',
          role: chunk.role || 'tool',
          content: chunk.content || '',
          tool_call_id: chunk.tool_call_id || '',
          tool_calls: chunk.tool_calls || undefined,
          created_at: chunk.created_at,
          table: chunk.json_table || chunk.table,
        }
      } else if (chunk.type === 'plan_progress') {
        blueprintAwaitingResult.value = true
        chatPlanProgressForWindow.value = (chatPlanProgressForWindow.value || '') + (chunk.content || '')
      } else if (chunk.role === 'tool' || chunk.role === 'agent' || chunk.type === 'plan') {
        const canMerge = ['text', 'reasoner_content', 'plan'].includes(chunk.type)
        let lastMsg = toolMessages.value[toolMessages.value.length - 1]
        let shouldAppend =
          canMerge &&
          lastMsg &&
          lastMsg.tool_call_id === chunk.tool_call_id &&
          lastMsg.type === (chunk.type || 'tool') &&
          lastMsg.created_at === chunk.created_at

        if (chunk.type === 'plan') {
          const batchAt = streamingSessionCreatedAt.value
          if (batchAt != null) {
            const mustClear = planStreamSegmentEnded.value || !shouldAppend
            if (mustClear) {
              if (planStreamSegmentEnded.value) planStreamSegmentEnded.value = false
              toolMessages.value = toolMessages.value.filter((m) => !(m.type === 'plan' && m.created_at === batchAt))
              chatPlanStreamForWindow.value = ''
              lastMsg = toolMessages.value[toolMessages.value.length - 1]
              shouldAppend =
                canMerge &&
                !!lastMsg &&
                lastMsg.tool_call_id === chunk.tool_call_id &&
                lastMsg.type === (chunk.type || 'tool') &&
                lastMsg.created_at === chunk.created_at
            }
          }
          chatPlanProgressForWindow.value = ''
        }

        if (
          chunk.role === 'tool' &&
          blueprintToolCallId.value &&
          String(chunk.tool_call_id || '') === blueprintToolCallId.value
        ) {
          blueprintAwaitingResult.value = false
          chatPlanProgressForWindow.value = ''
          commitPlanStreamToHistory()
          chatPlanStreamForWindow.value = ''
        }

        if (shouldAppend) {
          lastMsg.content = (lastMsg.content || '') + (chunk.content || '')
        } else {
          toolMessages.value.push({
            user_id: chunk.user_id,
            conversation_id: chunk.conversation_id,
            type: chunk.type || 'tool',
            role: chunk.role,
            content: chunk.content || '',
            tool_call_id: chunk.tool_call_id,
            tool_calls: chunk.tool_calls,
            created_at: chunk.created_at,
            table: chunk.json_table || chunk.table,
          })
        }
        if (chunk.type === 'plan') {
          const lastPlan = toolMessages.value[toolMessages.value.length - 1]
          if (lastPlan && lastPlan.type === 'plan') chatPlanStreamForWindow.value = lastPlan.content || ''
        }
      } else {
        if (chatPlanStreamForWindow.value && chunk.type !== 'plan' && chunk.type !== 'init' && chunk.type !== 'plan_progress') {
          commitPlanStreamToHistory()
          chatPlanStreamForWindow.value = ''
        }
        currentStreamingMessage.value = {
          user_id: chunk.user_id,
          conversation_id: chunk.conversation_id,
          type: chunk.type,
          role: chunk.role,
          content: chunk.content || '',
          tool_call_id: chunk.tool_call_id || '',
          tool_calls: chunk.tool_calls || undefined,
          created_at: chunk.created_at,
          table: chunk.json_table || chunk.table,
        }
      }

      if ((chunk.type === 'get_tools' || chunk.type === 'get_agents') && chunk.role === 'assistant') {
        const toolCallId = chunk.tool_call_id || (chunk.tool_calls?.[0]?.id ?? '')
        const hasBlueprintCall = (chunk.tool_calls || []).some((tc) => tc.function?.name === 'get_action_blueprint')
        if (hasBlueprintCall) {
          const bpCall = (chunk.tool_calls || []).find((tc) => tc.function?.name === 'get_action_blueprint')
          blueprintToolCallId.value = String(bpCall?.id || toolCallId || '')
          blueprintAwaitingResult.value = true
        }
        toolMessages.value.push({
          user_id: chunk.user_id || '',
          conversation_id: chunk.conversation_id || '',
          type: chunk.type,
          role: chunk.role,
          content: chunk.content || '',
          tool_call_id: toolCallId,
          tool_calls: chunk.tool_calls || undefined,
          created_at: chunk.created_at,
        })
      }

      applyPlanStreamSegmentEndedMarker(chunk)
      await Promise.resolve()
    }

    isProcessingQueue = false
    if (isStreamEnded.value && messageQueue.value.length === 0) {
      isGenerating.value = false
      isStreamEnded.value = false
      currentStreamingMessage.value = null
      blueprintAwaitingResult.value = false
      chatPlanProgressForWindow.value = ''
      commitPlanStreamToHistory()
      chatPlanStreamForWindow.value = ''
      delete chat_request.value.input_message_id
      delete chat_request.value.user_feedback
      const at = streamingSessionCreatedAt.value
      if (at != null) {
        const last = toolMessages.value[toolMessages.value.length - 1]
        if (last?.type === 'plan' && last?.created_at === at) planStreamSegmentEnded.value = true
      }
    }
  }

  async function readSseResponse(response, epoch, setupTimeout, clearTimeoutHandler) {
    if (!response.body) throw new Error('没有返回流')
    const reader = response.body.getReader()
    const decoder = new TextDecoder('utf-8')
    const batch = { at: Date.now() }
    streamingSessionCreatedAt.value = batch.at
    let buffer = ''
    let followedTurnId = ''
    try {
      while (epoch === streamEpoch) {
        const { value, done } = await reader.read()
        if (done || epoch !== streamEpoch) break
        if (!value) continue

        clearTimeoutHandler()
        setupTimeout()
        if (timeoutError.value) timeoutError.value = ''

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          const trimmedLine = line.trim()
          if (!trimmedLine.startsWith('data: ')) continue
          const data = trimmedLine.substring(6).trim()
          if (!data) continue
          try {
            const chunk = JSON.parse(data)
            if (chunk.type === 'turn_started' || chunk.type === 'accepted' || chunk.type === 'snapshot') {
              batch.at = Date.now()
              streamingSessionCreatedAt.value = batch.at
              if (chunk.turn_id) followedTurnId = chunk.turn_id
            }
            chunk.created_at = batch.at
            if (chunk.type === 'turn_started' && chunk.turn_id) {
              followedTurnId = chunk.turn_id
            } else if (chunk.turn_id && followedTurnId && chunk.turn_id !== followedTurnId) {
              continue
            } else if (!followedTurnId && chunk.turn_id) {
              followedTurnId = chunk.turn_id
            }

            if (chunk.type === 'input_message_id') {
              const mid = parseMessageId(chunk.content)
              if (mid) {
                for (let i = agent_message_list.value.length - 1; i >= 0; i--) {
                  const message = agent_message_list.value[i]
                  if (message.role === 'user' && !message.id) {
                    message.id = mid
                    break
                  }
                }
              }
              continue
            }

            if (chunk.type === 'reload_history') {
              const cid = chunk.conversation_id || chat_request.value.conversation_id || ''
              if (cid) await refreshMessagesFromServer(cid)
              continue
            }

            if (chunk.type === 'text' || chunk.type === 'reasoner_content') {
              isLoading.value = false
            } else if (chunk.type === 'abstract') {
              abstract.value = chunk.content
              chat_request.value.conversation_id = chunk.conversation_id
              const existing = conversation_list.value.find((item) => item.conversation_id === chunk.conversation_id)
              if (existing) {
                existing.abstract = abstract.value
              } else {
                conversation_list.value.unshift({
                  user_id: chunk.user_id,
                  conversation_id: chunk.conversation_id,
                  abstract: abstract.value,
                  create_at: '',
                  updated_at: '',
                })
              }
            }

            messageQueue.value.push(chunk)
            processMessageQueue()
          } catch (error) {
            console.error('解析 JSON 失败:', error, '原始数据:', data)
          }
        }
      }
    } finally {
      reader.releaseLock()
      clearTimeoutHandler()
      if (epoch === streamEpoch) {
        abortController.value = null
        isStreamEnded.value = true
        if (!isProcessingQueue && messageQueue.value.length === 0) {
          isGenerating.value = false
          isStreamEnded.value = false
          currentStreamingMessage.value = null
          chat_request.value.files = []
          delete chat_request.value.input_message_id
          delete chat_request.value.user_feedback
        }
      }
    }
  }

  async function handleSendMessage(message, files = [], options) {
    detachLocalStream()
    const epoch = streamEpoch
    isGenerating.value = true
    isStreamEnded.value = false
    chatPlanStreamForWindow.value = ''
    chatPlanProgressForWindow.value = ''
    blueprintAwaitingResult.value = false
    blueprintToolCallId.value = ''
    planStreamSegmentEnded.value = false
    chat_request.value.message = message
    chat_request.value.files = files
    if (options?.input_message_id) chat_request.value.input_message_id = options.input_message_id
    else delete chat_request.value.input_message_id
    if (options?.user_feedback) chat_request.value.user_feedback = true
    else delete chat_request.value.user_feedback

    isLoading.value = true
    timeoutError.value = ''
    currentStreamingMessage.value = {
      user_id: '',
      conversation_id: '',
      type: 'init',
      role: 'assistant',
      content: '',
      tool_call_id: '',
      tool_calls: undefined,
      created_at: Date.now(),
    }

    let timeoutId = null
    const setupTimeout = () => {
      if (timeoutId) clearTimeout(timeoutId)
      timeoutId = setTimeout(() => {
        if (epoch !== streamEpoch) return
        isLoading.value = false
        timeoutError.value = t('chat.timeout')
        if (abortController.value) abortController.value.abort()
      }, 1800000)
    }
    const clearTimeoutHandler = () => {
      if (timeoutId) {
        clearTimeout(timeoutId)
        timeoutId = null
      }
    }

    setupTimeout()
    try {
      abortController.value = new AbortController()
      const formData = new FormData()
      const payload = { ...chat_request.value }
      if (chatMode.value !== 'soulprout' && !payload.conversation_id) {
        const conversationId = crypto.randomUUID()
        chat_request.value.conversation_id = conversationId
        payload.conversation_id = conversationId
      }
      if (payload.agent_id) delete payload.agent_name
      if (options?.input_message_id) payload.input_message_id = options.input_message_id
      else delete payload.input_message_id
      if (options?.user_feedback) payload.user_feedback = true
      else delete payload.user_feedback
      if (chatMode.value === 'soulprout') {
        delete payload.model_source
        delete payload.model
        payload.agent_use = 'soulprout'
        payload.agent_id = null
        payload.agent_name = null
        payload.tools_use = true
        payload.skills_use = true
        payload.kb_use = []
        payload.conversation_id = currentUserId.value
      }
      formData.append('chat_request', JSON.stringify(payload))
      files.forEach((file) => formData.append('files', file))
      const response = await apiFetch('/api/message/chat', {
        method: 'POST',
        body: formData,
        headers: { Accept: 'text/event-stream', 'Cache-Control': 'no-cache' },
        cache: 'no-store',
        signal: abortController.value.signal,
      })
      if (epoch !== streamEpoch) return
      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`)
      if (!response.body) throw new Error('没有返回流')
      await readSseResponse(response, epoch, setupTimeout, clearTimeoutHandler)
    } catch (error) {
      if (epoch !== streamEpoch) return
      if (error?.name === 'AbortError') return
      console.error('流式消息失败:', error)
      timeoutError.value = t('chat.requestFailed')
      isLoading.value = false
      currentStreamingMessage.value = null
      clearTimeoutHandler()
      isGenerating.value = false
      isStreamEnded.value = false
      messageQueue.value = []
      chat_request.value.files = []
      delete chat_request.value.input_message_id
      delete chat_request.value.user_feedback
    }
  }

  async function attachConversationStream(conversationId) {
    if (!conversationId) return
    detachLocalStream()
    const epoch = streamEpoch
    abortController.value = new AbortController()
    try {
      const response = await apiFetch(`/api/message/${encodeURIComponent(conversationId)}/stream`, {
        method: 'GET',
        headers: { Accept: 'text/event-stream', 'Cache-Control': 'no-cache' },
        cache: 'no-store',
        signal: abortController.value.signal,
      })
      if (epoch !== streamEpoch) return
      if (!response.ok || !response.body) return
      await readSseResponse(response, epoch, () => {}, () => {})
    } catch (error) {
      if (epoch !== streamEpoch) return
      if (error?.name === 'AbortError') return
      console.error('挂接会话流失败:', error)
    }
  }

  function applyRunEvent(event) {
    const conversationId = event.conversation_id || ''
    if (!conversationId) return
    if (event.type === 'run_started') {
      const idx = runningConversations.value.findIndex((item) => item.conversation_id === conversationId)
      const previous = idx >= 0 ? runningConversations.value[idx] : undefined
      const known = conversation_list.value.find((item) => item.conversation_id === conversationId)
      const next = {
        conversation_id: conversationId,
        user_id: event.user_id || previous?.user_id || '',
        mode: event.mode === 'soulprout' ? 'soulprout' : 'task',
        abstract: event.abstract || previous?.abstract || known?.abstract || '',
        started_at: event.started_at || previous?.started_at || Date.now(),
      }
      if (idx >= 0) runningConversations.value[idx] = next
      else runningConversations.value.unshift(next)
      return
    }
    if (event.type === 'run_updated') {
      const item = runningConversations.value.find((row) => row.conversation_id === conversationId)
      if (item && event.abstract) item.abstract = event.abstract
      return
    }
    if (event.type === 'run_finished') {
      runningConversations.value = runningConversations.value.filter((item) => item.conversation_id !== conversationId)
    }
  }

  async function watchRunningConversations() {
    detachRunsStream()
    const controller = new AbortController()
    runsAbortController = controller
    let buffer = ''
    while (!controller.signal.aborted) {
      try {
        const response = await apiFetch('/api/message/runs/stream', {
          method: 'GET',
          headers: { Accept: 'text/event-stream', 'Cache-Control': 'no-cache' },
          cache: 'no-store',
          signal: controller.signal,
        })
        if (!response.ok || !response.body) throw new Error('runs stream failed')
        const reader = response.body.getReader()
        const decoder = new TextDecoder('utf-8')
        buffer = ''
        while (!controller.signal.aborted) {
          const { value, done } = await reader.read()
          if (done) break
          buffer += decoder.decode(value, { stream: true })
          const lines = buffer.split('\n')
          buffer = lines.pop() || ''
          for (const line of lines) {
            const trimmed = line.trim()
            if (!trimmed.startsWith('data: ')) continue
            const data = trimmed.substring(6).trim()
            if (!data) continue
            try {
              applyRunEvent(JSON.parse(data))
            } catch (error) {
              console.error('解析运行状态失败:', error)
            }
          }
        }
        if (!controller.signal.aborted) await new Promise((resolve) => setTimeout(resolve, 2000))
      } catch (error) {
        if (controller.signal.aborted || error?.name === 'AbortError') return
        console.error('运行列表订阅中断:', error)
        await new Promise((resolve) => setTimeout(resolve, 2000))
      }
    }
  }

  async function openRunningConversation(item) {
    if (item.mode === 'soulprout' || item.conversation_id === currentUserId.value) {
      if (chatMode.value !== 'soulprout') {
        cachedTaskChatRequest.value = { ...chat_request.value }
        chatMode.value = 'soulprout'
      }
      await loadSoulproutConversation()
      return
    }
    if (chatMode.value !== 'task') chatMode.value = 'task'
    await pickConversation(item.conversation_id)
  }

  async function stopGeneration() {
    const conversationId =
      chatMode.value === 'soulprout'
        ? currentUserId.value || chat_request.value.conversation_id || ''
        : chat_request.value.conversation_id || ''
    detachLocalStream()
    isLoading.value = false
    currentStreamingMessage.value = null
    timeoutError.value = t('chat.stopped')
    isGenerating.value = false
    delete chat_request.value.input_message_id
    delete chat_request.value.user_feedback
    if (!conversationId) return
    try {
      await http.post('/api/message/stop', { conversation_id: conversationId })
    } catch (error) {
      console.error('停止生成失败:', error)
    }
  }

  onMounted(async () => {
    const ok = await fetchCurrentUserId()
    if (!ok) return
    await fetchConversations()
    await getLLMmodels()
    watchRunningConversations()
    try {
      await loadSoulproutConversation()
    } finally {
      ready.value = true
    }
  })

  onUnmounted(() => {
    detachLocalStream()
    detachRunsStream()
  })

  return {
    conversation_list,
    taskConversationList,
    chat_request,
    agent_message_list,
    chatMode,
    soulMessagesHasMore,
    soulMessagesLoadingMore,
    welcomeAnimationToken,
    isLoading,
    isGenerating,
    chatPlanStreamForWindow,
    chatPlanProgressForWindow,
    blueprintStreamPending,
    reloadStreamingUiToken,
    timeoutError,
    currentUserId,
    currentUsername,
    model_list,
    runningConversations,
    currentStreamingMessage,
    toolMessages,
    fileMessages,
    ready,
    unauthorized,
    loadMoreSoulMessages,
    handleSendMessage,
    stopGeneration,
    handleSwitchMode,
    createConversation,
    pickConversation,
    deleteConversation,
    updateConversationAbstract,
    openRunningConversation,
  }
}

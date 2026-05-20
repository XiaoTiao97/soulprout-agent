<template>
  <div class="query">
    <form class="query-form" @submit.prevent="submitMessage">
      <div class="selected-files" v-if="selectedFiles.length > 0">
        <div class="selected-file-item" v-for="(file, idx) in selectedFiles" :key="getFileKey(file)">
          <button class="remove-file-btn" type="button" @click="removeFile(idx)" title="删除">
            <img :src="DeleteFileIconUrl" alt="删除" />
          </button>
          <template v-if="isImageFile(file)">
            <img class="selected-file-thumb" :src="getImagePreviewUrl(file)" :alt="file.name" />
          </template>
          <template v-else>
            <img class="selected-file-icon" :src="getFileIconUrl(file)" :alt="file.name" />
          </template>
          <div class="selected-file-name" :title="file.name">{{ file.name }}</div>
        </div>
      </div>
      <div class="input-total">
        <textarea
          ref="textareaRef"
          class="input_field"
          v-model="input"
          @keydown.enter.exact.prevent="submitMessage"
          @input="adjustHeight"
          @paste="handleInputPaste"
          placeholder="提问，发现新世界"
          rows="1"
        />
      </div>
      <div class="input-options">
        <div class="input-options-left">
          <!-- 1. 上传文件（第一位） -->
          <button class="upload-option" type="button" @click="triggerFileUpload" title="上传文件">
            <img src="@/assets/images/file_upload.svg" width="18" height="18" />
          </button>

          <!-- 2. 设置对话 - 多选智能体或无专家时显示，子智能体/主智能体时隐藏 -->
          <div v-if="!props.chat_request.agent_use || props.chat_request.agent_use === 'select-agent'" class="settings-selector" ref="settingsSelectorRef">
            <button class="settings-select-btn" :class="{ 'settings-active': showSettingsPanel }" type="button" @click="toggleSettingsPanel">
              <span>⚙️ 设置</span>
              <svg class="dropdown-icon" :class="{ 'rotate': showSettingsPanel }" width="12" height="12" viewBox="0 0 12 12" fill="currentColor">
                <path d="M6 8L2 4h8l-4 4z"/>
              </svg>
            </button>
            
            <!-- 上拉栏：模型、工具、知识库 -->
            <div class="settings-panel" v-show="showSettingsPanel">
              <!-- 模型 - 从右侧展开 -->
              <div v-if="!props.chat_request.agent_use || props.chat_request.agent_use === 'select-agent'" class="settings-panel-row" ref="modelSelectorRef">
                <span class="settings-row-label">模型</span>
                <button class="settings-row-trigger" type="button" @click="toggleModelSelector">
                  <span class="settings-row-value">{{ selectedModelDisplay }}</span>
                  <svg class="dropdown-icon dropdown-icon-right" :class="{ 'rotate': showModelSelector }" width="12" height="12" viewBox="0 0 12 12" fill="currentColor">
                    <path d="M6 8L2 4h8l-4 4z"/>
                  </svg>
                </button>
              </div>

              <!-- 工具 -->
              <div v-if="!props.chat_request.agent_use || props.chat_request.agent_use === 'select-agent'" class="settings-panel-row">
                <span class="settings-row-label">工具</span>
                <button class="settings-row-trigger settings-row-trigger-tools" :class="{ 'kb-active': chat_request.tools_use ?? false }" type="button" @click="$emit('changeToolsUse')">
                  <span class="settings-row-value">{{ (chat_request.tools_use ?? false) ? '已启用' : '未启用' }}</span>
                </button>
              </div>

              <!-- 技能 -->
              <div v-if="!props.chat_request.agent_use || props.chat_request.agent_use === 'select-agent'" class="settings-panel-row">
                <span class="settings-row-label">技能</span>
                <button class="settings-row-trigger settings-row-trigger-tools" :class="{ 'kb-active': chat_request.skills_use ?? false }" type="button" @click="$emit('changeSkillsUse')">
                  <span class="settings-row-value">{{ (chat_request.skills_use ?? false) ? '已启用' : '未启用' }}</span>
                </button>
              </div>

              <!-- 知识库 - 从右侧展开 -->
              <div v-if="!props.chat_request.agent_use || props.chat_request.agent_use === 'select-agent'" class="settings-panel-row" ref="kbSelectorRef">
                <span class="settings-row-label">知识库</span>
                <button class="settings-row-trigger" :class="{ 'kb-active': (props.chat_request.kb_use?.length || 0) > 0 }" type="button" @click="toggleKBSelector">
                  <span class="settings-row-value">{{ selectedKBDisplay }}</span>
                  <svg class="dropdown-icon dropdown-icon-right" :class="{ 'rotate': showKBSelector }" width="12" height="12" viewBox="0 0 12 12" fill="currentColor">
                    <path d="M6 8L2 4h8l-4 4z"/>
                  </svg>
                </button>
              </div>

              <!-- 模型列表 - 从右侧展开，底部不超出设置面板 -->
              <div class="settings-right-dropdown settings-right-dropdown-fixed" v-show="showModelSelector">
                <div class="settings-right-dropdown-inner">
                  <div v-for="provider in modelProviders" :key="provider.model_source" class="model-group">
                    <div class="model-group-title">{{ provider.model_source }}</div>
                    <button 
                      v-for="model in provider.models" 
                      :key="model.id"
                      class="model-option"
                      :class="{ 'active': chat_request.model === model.id }"
                      type="button"
                      @click="selectModel(provider.model_source, model.id)"
                    >
                      {{ model.name }}
                    </button>
                  </div>
                </div>
              </div>

              <!-- 知识库列表 - 从右侧展开，底部不超出设置面板 -->
              <div class="settings-right-dropdown settings-right-dropdown-fixed kb-dropdown-right" v-show="showKBSelector">
                <div class="settings-right-dropdown-inner">
                  <div class="kb-list">
                    <label 
                      v-for="kb in props.kb_list" 
                      :key="kb.id"
                      class="kb-checkbox"
                    >
                      <input type="checkbox" v-model="selectedKBs" :value="kb.id" />
                      {{ kb.name }}
                    </label>
                    <button class="confirm-btn" type="button" @click="confirmKBSelect">确认</button>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- 3. 专家模式（第三位）- 毕业帽+专家模式 -->
          <div class="agent-selector" ref="agentSelectorRef">
                <button class="agent-select-btn" :class="{ 'agent-active': !!props.chat_request.agent_use }" type="button" @click="toggleAgentSelector">
              <span>🎓 {{ selectedAgentDisplay }}</span>
              <svg class="dropdown-icon" :class="{ 'rotate': showAgentSelector }" width="12" height="12" viewBox="0 0 12 12" fill="currentColor">
                <path d="M6 8L2 4h8l-4 4z"/>
              </svg>
            </button>
            
            <!-- 统一的下拉框 -->
            <div class="agent-dropdown" v-show="showAgentSelector" @mouseleave="handleModeMouseLeave">
              <div class="agent-dropdown-content">
                <!-- 左侧：模式选择 -->
                <div class="agent-dropdown-left" :class="{ 'has-right': currentMode }">
                  <button 
                    class="agent-select"
                    :class="{ 'active': !props.chat_request.agent_use }"
                    type="button"
                    @click="selectNone"
                  >
                    无
                  </button>
                  <div class="mode-selector">
                    <div class="mode-column">
                      <div
                        class="mode-item"
                        @mouseenter="currentMode = null"
                        @click="selectSoulprout"
                        :class="{ 'active': props.chat_request.agent_use === 'soulprout' }"
                      >
                        Soulprout
                      </div>
                      <div 
                        class="mode-item" 
                        @mouseenter="currentMode = 'expert'"
                        :class="{ 'active': props.chat_request.agent_use === 'expert-agent' }"
                      >
                        智能体
                      </div>
                      <div 
                        class="mode-item" 
                        @mouseenter="currentMode = 'select'"
                        :class="{ 'active': props.chat_request.agent_use === 'select-agent' }"
                      >
                        多选智能体
                      </div>
                    </div>
                  </div>
                </div>

                <!-- 右侧：智能体列表（分块：我的创建 / 我的订阅 / 系统预设） -->
                <div class="agent-dropdown-right" ref="agentListDropdownRef" v-if="currentMode" @mouseenter="keepRightDropdownOpen = true" @mouseleave="keepRightDropdownOpen = false">
                  <div class="list-column-wrapper">
                    <div class="list-column">
                      <!-- 智能体 -->
                      <template v-if="currentMode === 'expert'">
                        <div v-for="(agents, blockKey) in singleGrouped" :key="blockKey" class="agent-dropdown-block" v-show="blockKey === 'mySubscribed' || agents.length > 0">
                          <div class="agent-dropdown-block-header" @click="toggleAgentBlock('expert_' + blockKey)">
                            <span class="agent-dropdown-block-title">{{ blockKey === 'myCreated' ? '我的创建' : blockKey === 'mySubscribed' ? '我的订阅' : '系统预设' }}</span>
                            <svg class="agent-block-toggle" :class="{ expanded: agentDropdownExpanded['expert_' + blockKey] }" width="10" height="10" viewBox="0 0 12 12">
                              <path d="M2 4l4 4 4-4" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" fill="none"/>
                            </svg>
                          </div>
                          <div v-show="agentDropdownExpanded['expert_' + blockKey]" class="agent-dropdown-block-items">
                            <div v-if="agents.length === 0" class="agent-dropdown-empty-hint">暂无订阅</div>
                            <button 
                              v-for="agent in agents" 
                              :key="agent.agent_id || agent.name"
                              class="agent-select"
                              :class="{ 'active': selectedSingle === (agent.agent_id || agent.name) }"
                              type="button"
                              @click="selectSingle(agent)"
                            >
                              {{ agent.name_zh || agent.name }}
                            </button>
                          </div>
                        </div>
                      </template>
                      <!-- 多选智能体 -->
                      <template v-if="currentMode === 'select'">
                        <div v-for="(agents, blockKey) in singleGrouped" :key="blockKey" class="agent-dropdown-block" v-show="blockKey === 'mySubscribed' || agents.length > 0">
                          <div class="agent-dropdown-block-header" @click="toggleAgentBlock('select_' + blockKey)">
                            <span class="agent-dropdown-block-title">{{ blockKey === 'myCreated' ? '我的创建' : blockKey === 'mySubscribed' ? '我的订阅' : '系统预设' }}</span>
                            <svg class="agent-block-toggle" :class="{ expanded: agentDropdownExpanded['select_' + blockKey] }" width="10" height="10" viewBox="0 0 12 12">
                              <path d="M2 4l4 4 4-4" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" fill="none"/>
                            </svg>
                          </div>
                          <div v-show="agentDropdownExpanded['select_' + blockKey]" class="agent-dropdown-block-items">
                            <div v-if="agents.length === 0" class="agent-dropdown-empty-hint">暂无订阅</div>
                            <div v-else class="agent-checkbox-list">
                              <label 
                                v-for="agent in agents" 
                                :key="agent.agent_id || agent.name"
                                class="agent-checkbox"
                                :class="{ 'agent-checkbox-disabled': isDefaultEnabledAgent(agent.name) }"
                              >
                                <input 
                                  v-if="!isDefaultEnabledAgent(agent.name)"
                                  type="checkbox" 
                                  v-model="selectedSelect" 
                                  :value="agent.agent_id || agent.name" 
                                />
                                <input 
                                  v-else
                                  type="checkbox" 
                                  checked
                                  disabled
                                  class="agent-checkbox-disabled-input"
                                />
                                {{ agent.name_zh || agent.name }}
                              </label>
                            </div>
                          </div>
                        </div>
                      </template>
                    </div>
                    <!-- 多选智能体时，确定按钮固定在底部 -->
                    <div class="confirm-btn-wrapper" v-if="currentMode === 'select'">
                      <button class="confirm-btn" type="button" @click="confirmSelect" :disabled="filteredSelectedSelect.length === 0">确认</button>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
        <div class="input-options-right">
          <button class="input_button" type="button" @click="handleButtonClick">
            <div v-if="props.isGenerating" class="loading-spinner"></div>
            <img v-else :src="InputIconUrl" width="18" height="18" />
          </button>
          <div v-if="showGenerationPrompt" class="generation-prompt">
            停止生成
          </div>
        </div>
      </div>
    </form>

    <input type="file" multiple ref="fileInput" style="display: none;" @change="handleFileUpload" />
  </div>
</template>

<script lang="ts" setup>
import { ref, nextTick, computed, onMounted, onUnmounted } from 'vue'
import { AgentCard } from '../types/interface'

const StopIconUrl = new URL('@/assets/images/stop_icon.svg', import.meta.url).href
const InputIconUrl = new URL('@/assets/images/mengya_input.svg', import.meta.url).href
const DocIconUrl = new URL('@/assets/images/doc_update.svg', import.meta.url).href
const ExcelIconUrl = new URL('@/assets/images/excel_update.svg', import.meta.url).href
const PptIconUrl = new URL('@/assets/images/ppt_update.svg', import.meta.url).href
const PdfIconUrl = new URL('@/assets/images/pdf_update.svg', import.meta.url).href
const FileIconUrl = new URL('@/assets/images/file_update.svg', import.meta.url).href
const DeleteFileIconUrl = new URL('@/assets/images/delete_file.svg', import.meta.url).href

const props = defineProps<{
  chat_request: {
    tools_use?: boolean
    skills_use?: boolean
    model_source?: string
    model?: string
    agent_id?: string[] | string | null
    agent_name?: string[] | string | null
    agent_use?: string | null
    kb_use?: string[] | null
  }
  model_list: Record<string, string[]>
  agent_card_list: AgentCard[]
  isGenerating: boolean
  userId: string
  kb_list: { id: string, name: string }[]
}>()

const emit = defineEmits<{
  sendMessage: [message: string, files: File[]]
  changeToolsUse: []
  changeSkillsUse: []
  selectModel: [model_source: string, model: string]
  selectAgent: [agent_use: string | null, agent_id: string | string[] | null]
  stopGeneration: []
  loadAgents: []
  selectKB: [kb_use: string[]]
  loadKBs: []
}>()

const input = ref('')
const showModelSelector = ref(false)
const modelSelectorRef = ref<HTMLElement>()
const showSettingsPanel = ref(false)
const settingsSelectorRef = ref<HTMLElement>()
const textareaRef = ref<HTMLTextAreaElement>()
const showAgentSelector = ref(false)
const agentSelectorRef = ref<HTMLElement>()
const agentListDropdownRef = ref<HTMLElement>()
const currentMode = ref<'single' | 'multi' | 'select' | null>(null)
const keepRightDropdownOpen = ref(false)
const selectedSingle = ref<string>('')  // 存储 agent_id
const showGenerationPrompt = ref(false)
const selectedSelect = ref<string[]>([])  // 存储 agent_id[]

const selectedFiles = ref<File[]>([])
const fileInput = ref<HTMLInputElement | null>(null)
const filePreviewUrls = ref(new Map<string, string>())

// 默认开启的智能体，不计入选择数量且不可取消
const DEFAULT_ENABLED_AGENTS = ['mengya_deepsearch', 'mengya_pptx']

// 判断是否为默认开启的智能体
const isDefaultEnabledAgent = (agentName: string) => {
  return DEFAULT_ENABLED_AGENTS.includes(agentName)
}

// 所有智能体（不再区分 single/multi，每个智能体都可添加子智能体）
const singleAgents = computed(() => props.agent_card_list)

// 按 user_id 分组的智能体：我的创建 / 我的订阅 / 系统预设
const groupByUserId = <T extends { user_id?: string }>(list: T[]) => ({
  myCreated: list.filter(a => a.user_id === props.userId),
  mySubscribed: list.filter(a => a.user_id !== props.userId && a.user_id !== 'mengya'),
  systemPreset: list.filter(a => a.user_id === 'mengya')
})
const singleGrouped = computed(() => groupByUserId(singleAgents.value))

// 下拉框内各块展开状态
const agentDropdownExpanded = ref<Record<string, boolean>>({
  expert_myCreated: true, expert_mySubscribed: false, expert_systemPreset: false,
  select_myCreated: true, select_mySubscribed: false, select_systemPreset: false
})
const toggleAgentBlock = (key: string) => {
  agentDropdownExpanded.value[key] = !agentDropdownExpanded.value[key]
}

// 过滤掉默认开启的智能体后的选中列表（按 agent_id）
const filteredSelectedSelect = computed(() => {
  return selectedSelect.value.filter(id => {
    const agent = singleAgents.value.find(a => (a.agent_id || a.name) === id)
    return agent && !isDefaultEnabledAgent(agent.name)
  })
})


// Add arraysEqual function
const arraysEqual = (a: string[], b: string[]) => {
  const sortedA = [...a].sort()
  const sortedB = [...b].sort()
  return sortedA.length === sortedB.length && sortedA.every((val, i) => val === sortedB[i])
}

// 调整textarea高度
function adjustHeight() {
  nextTick(() => {
    if (textareaRef.value) {
      // 重置高度为auto以获取实际的scrollHeight
      textareaRef.value.style.height = 'auto'
      
      const scrollHeight = textareaRef.value.scrollHeight
      const maxHeight = 200 // 对应CSS中的max-height
      
      // 如果内容高度小于最大高度，自动调整高度
      if (scrollHeight <= maxHeight) {
        textareaRef.value.style.height = scrollHeight + 'px'
        textareaRef.value.style.overflowY = 'hidden'
      } else {
        // 如果内容超出最大高度，固定高度并显示滚动条
        textareaRef.value.style.height = maxHeight + 'px'
        textareaRef.value.style.overflowY = 'auto'
      }
    }
  })
}

// 将原始数据转换为模板需要的格式
const modelProviders = computed(() => {
  return Object.entries(props.model_list).map(([providerName, models]) => ({
    model_source: providerName,
    models: models.map(model => ({
      id: model,
      name: model // 假设模型名称与ID相同
    })), 
  }))
})

// 显示的模型名称
const selectedModelDisplay = computed(() => {
  if (!props.chat_request.model) return '选择模型'
  
  for (const provider of modelProviders.value) {
    const model = provider.models.find(m => m.id === props.chat_request.model)
    if (model) return model.name
  }
  return '选择模型'
})

// 根据 agent_id 从 agent_card_list 获取显示名称（优先 name_zh，否则 name）
const getAgentNameById = (agentId: string) => {
  const agent = singleAgents.value.find(a => (a.agent_id || a.name) === agentId)
  return (agent?.name_zh || agent?.name) ?? agentId
}

// 显示时优先使用 agent_name，发送时仍使用 agent_id
const selectedAgentDisplay = computed(() => {
  if (!props.chat_request.agent_use) return '专家模式'
  const agentId = props.chat_request.agent_id
  const agentName = props.chat_request.agent_name
  if (props.chat_request.agent_use === 'soulprout') {
    return 'Soulprout'
  }
  if (props.chat_request.agent_use === 'expert-agent') {
    if (typeof agentName === 'string' && agentName) return agentName
    if (typeof agentId === 'string') return getAgentNameById(agentId) || agentId
    return '智能体'
  }
  if (props.chat_request.agent_use === 'select-agent') {
    const agentIds = Array.isArray(agentId) ? agentId : []
    const filteredCount = agentIds.filter(id => {
      const agent = singleAgents.value.find(a => (a.agent_id || a.name) === id)
      return agent && !isDefaultEnabledAgent(agent.name)
    }).length
    return filteredCount > 0 ? `已选择${filteredCount}个专家` : '多选专家'
  }
  return '专家模式'
})

function handleButtonClick() {
  if (props.isGenerating) {
    emit('stopGeneration')
  } else {
    submitMessage()
  }
}

function submitMessage() {
  if (input.value.trim()) {
    if (props.isGenerating) {
      showGenerationPrompt.value = true
      setTimeout(() => {
        showGenerationPrompt.value = false
      }, 2000) // Hide after 2 seconds
      return
    }
    emit('sendMessage', input.value, selectedFiles.value)
    input.value = ''
    clearSelectedFiles()
    nextTick(() => {
      if (textareaRef.value) {
        textareaRef.value.style.height = 'auto'
      }
    })
  } else if (props.isGenerating) {
    showGenerationPrompt.value = true
    setTimeout(() => {
      showGenerationPrompt.value = false
      // Removed: emit('stopGeneration')
    }, 2000)
    return
  }
}

function toggleModelSelector() {
  showModelSelector.value = !showModelSelector.value
}

function toggleSettingsPanel() {
  showSettingsPanel.value = !showSettingsPanel.value
  if (!showSettingsPanel.value) {
    showModelSelector.value = false
    showKBSelector.value = false
  } else {
    if (showKBSelector.value) emit('loadKBs')
  }
}

function toggleAgentSelector() {
  showAgentSelector.value = !showAgentSelector.value
    if (showAgentSelector.value) {
    emit('loadAgents')
  }
  currentMode.value = null
  keepRightDropdownOpen.value = false
  // 初始化选中状态（优先使用 agent_id；agent_name 可为 name_zh 或 name）
  const matchAgentByNameOrZh = (agent: AgentCard, name: string) => (agent.name_zh || agent.name) === name
  if (props.chat_request.agent_use === 'expert-agent') {
    const id = typeof props.chat_request.agent_id === 'string' ? props.chat_request.agent_id
      : (typeof props.chat_request.agent_name === 'string' ? (singleAgents.value.find(a => matchAgentByNameOrZh(a, props.chat_request.agent_name as string))?.agent_id || props.chat_request.agent_name) : '')
    selectedSingle.value = id || ''
  }
  if (props.chat_request.agent_use === 'select-agent' && (Array.isArray(props.chat_request.agent_id) || Array.isArray(props.chat_request.agent_name))) {
    const ids = Array.isArray(props.chat_request.agent_id) ? props.chat_request.agent_id
      : (Array.isArray(props.chat_request.agent_name) ? props.chat_request.agent_name.map(name => singleAgents.value.find(a => matchAgentByNameOrZh(a, name))?.agent_id || name).filter(Boolean) : [])
    selectedSelect.value = ids.filter(id => {
      const agent = singleAgents.value.find(a => (a.agent_id || a.name) === id)
      return agent && !isDefaultEnabledAgent(agent.name)
    })
  }
    // 清除之前的选择状态
  if (!props.chat_request.agent_use) {
    selectedSingle.value = ''
    selectedSelect.value = []
  }
}

function handleModeMouseLeave() {
  // 延迟关闭，给用户时间移动到右侧下拉框
  setTimeout(() => {
    if (!keepRightDropdownOpen.value) {
      currentMode.value = null
    }
  }, 100)
}

// 选择智能体，传递 agent_id
function selectSingle(agent: AgentCard) {
  const id = agent.agent_id || agent.name
  emit('selectAgent', 'expert-agent', id)
  emit('selectKB', agent.kbs || [])
  emit('selectModel', '', '')
  showAgentSelector.value = false
  selectedSingle.value = id
  selectedSelect.value = []
}

function confirmSelect() {
  // 过滤掉默认开启的智能体，传递 agent_id 数组
  const filteredAgentIds = filteredSelectedSelect.value
  emit('selectAgent', 'select-agent', [...filteredAgentIds])
  const combinedKbs = new Set<string>()
  // 合并知识库时，包括用户选择的智能体的知识库
  selectedSelect.value.forEach(id => {
    const agent = singleAgents.value.find(a => (a.agent_id || a.name) === id)
    if (agent?.kbs) {
      agent.kbs.forEach(kb => combinedKbs.add(kb))
    }
  })
  // 也要包含默认开启的智能体的知识库
  DEFAULT_ENABLED_AGENTS.forEach(name => {
    const agent = singleAgents.value.find(a => a.name === name)
    if (agent?.kbs) {
      agent.kbs.forEach(kb => combinedKbs.add(kb))
    }
  })
  emit('selectKB', Array.from(combinedKbs))
  showAgentSelector.value = false
  selectedSingle.value = ''
}

function selectNone() {
  emit('selectAgent', null, null)
  emit('selectKB', [])
  // 切回「无」时恢复默认模型（选子/主智能体时会被清空）
  const providers = modelProviders.value
  if (providers.length > 0 && providers[0].models.length > 0) {
    const first = providers[0]
    emit('selectModel', first.model_source, first.models[0].id)
  }
  showAgentSelector.value = false
  selectedSingle.value = ''
  selectedSelect.value = []
}

// 选择 Soulprout 模式：无需二级 agent_id 选择，直接生效
function selectSoulprout() {
  emit('selectAgent', 'soulprout', null)
  emit('selectKB', [])
  // Soulprout 模式同样使用默认模型
  const providers = modelProviders.value
  if (providers.length > 0 && providers[0].models.length > 0) {
    const first = providers[0]
    emit('selectModel', first.model_source, first.models[0].id)
  }
  showAgentSelector.value = false
  currentMode.value = null
  keepRightDropdownOpen.value = false
  selectedSingle.value = ''
  selectedSelect.value = []
}

function selectModel(model_source: string, model: string) {
  console.log('选择模型:', model)
  emit('selectModel', model_source, model)
  showModelSelector.value = false
}

// 点击外部关闭设置上拉栏（含模型、知识库）
function handleSettingsClickOutside(event: Event) {
  if (settingsSelectorRef.value && !settingsSelectorRef.value.contains(event.target as Node)) {
    showSettingsPanel.value = false
    showModelSelector.value = false
    showKBSelector.value = false
  }
}

function handleAgentClickOutside(event: Event) {
  if (agentSelectorRef.value && !agentSelectorRef.value.contains(event.target as Node)) {
    showAgentSelector.value = false
    currentMode.value = null
    keepRightDropdownOpen.value = false
  }
}

// Add to refs
const showKBSelector = ref(false)
const kbSelectorRef = ref<HTMLElement>()
const selectedKBs = ref<string[]>([])

// Add computed
const selectedKBDisplay = computed(() => {
  const len = props.chat_request.kb_use?.length || 0;
  if (len > 0) {
    return `已选 ${len} 个知识库`;
  }
  return '未选择';
})

// Add functions
function toggleKBSelector() {
  showKBSelector.value = !showKBSelector.value
  if (showKBSelector.value) {
    emit('loadKBs')
    selectedKBs.value = props.chat_request.kb_use || []
  }
}

function confirmKBSelect() {
  emit('selectKB', [...selectedKBs.value])
  showKBSelector.value = false
}


function triggerFileUpload() {
  if (fileInput.value) fileInput.value.click()
}

function appendSelectedFiles(newFiles: File[]) {
  if (!newFiles.length) return
  selectedFiles.value = [...selectedFiles.value, ...newFiles]
  newFiles.forEach(file => {
    if (isImageFile(file)) {
      const key = getFileKey(file)
      if (!filePreviewUrls.value.has(key)) {
        filePreviewUrls.value.set(key, URL.createObjectURL(file))
      }
    }
  })
}

function handleFileUpload() {
  if (fileInput.value && fileInput.value.files) {
    const newFiles = Array.from(fileInput.value.files)
    appendSelectedFiles(newFiles)
    fileInput.value.value = ''
  }
}

function handleInputPaste(event: ClipboardEvent) {
  const items = event.clipboardData?.items
  if (!items || items.length === 0) return
  const pastedFiles: File[] = []
  Array.from(items).forEach(item => {
    if (item.kind === 'file') {
      const file = item.getAsFile()
      if (file) pastedFiles.push(file)
    }
  })
  if (pastedFiles.length > 0) {
    event.preventDefault()
    appendSelectedFiles(pastedFiles)
  }
}

function removeFile(index: number) {
  const removed = selectedFiles.value.splice(index, 1)[0]
  if (removed) {
    revokePreviewUrl(removed)
  }
}

function clearSelectedFiles() {
  selectedFiles.value.forEach(file => revokePreviewUrl(file))
  selectedFiles.value = []
}

function getFileKey(file: File) {
  return `${file.name}_${file.size}_${file.lastModified}`
}

function getFileExtension(file: File) {
  const name = file.name || ''
  const idx = name.lastIndexOf('.')
  return idx >= 0 ? name.slice(idx + 1).toLowerCase() : ''
}

function isImageFile(file: File) {
  const ext = getFileExtension(file)
  return ['png', 'jpg', 'jpeg', 'gif', 'webp', 'svg'].includes(ext)
}

function getImagePreviewUrl(file: File) {
  const key = getFileKey(file)
  const cached = filePreviewUrls.value.get(key)
  if (cached) return cached
  if (isImageFile(file)) {
    const url = URL.createObjectURL(file)
    filePreviewUrls.value.set(key, url)
    return url
  }
  return ''
}

function revokePreviewUrl(file: File) {
  const key = getFileKey(file)
  const url = filePreviewUrls.value.get(key)
  if (url) {
    URL.revokeObjectURL(url)
    filePreviewUrls.value.delete(key)
  }
}

function getFileIconUrl(file: File) {
  const ext = getFileExtension(file)
  if (['doc', 'docx'].includes(ext)) return DocIconUrl
  if (['xls', 'xlsx', 'csv'].includes(ext)) return ExcelIconUrl
  if (['ppt', 'pptx'].includes(ext)) return PptIconUrl
  if (['pdf'].includes(ext)) return PdfIconUrl
  return FileIconUrl
}

onMounted(() => {
  document.addEventListener('click', handleSettingsClickOutside)
  document.addEventListener('click', handleAgentClickOutside)
})

onUnmounted(() => {
  document.removeEventListener('click', handleSettingsClickOutside)
  document.removeEventListener('click', handleAgentClickOutside)
  clearSelectedFiles()
})

defineExpose({
  setInput: (text: string) => {
    input.value = text
    adjustHeight()
  }
})
</script>

<style scoped>
@import '@/assets/css/chat.css';

.input-options {
  min-height: 40px;
  height: auto;
}

.model-select-btn,
.tools-use-option,
.upload-option,
.kb-select-btn,
.agent-select-btn,
.settings-select-btn {
  height: 36px;
  min-height: 36px;
  box-sizing: border-box;
}

/* 设置对话：上拉栏 */
.settings-selector {
  position: relative;
}

.settings-select-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 14px;
  background: linear-gradient(180deg, #fafbfc 0%, #f5f7fa 100%);
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  cursor: pointer;
  font-size: 14px;
  transition: all 0.2s ease;
  color: #111827;
}

.settings-select-btn:hover {
  background: #eef1f5;
  border-color: #dfe3e8;
  box-shadow: 0 8px 18px -14px rgba(15, 23, 42, 0.45);
}

.settings-active {
  background: #eef1f5;
  border-color: #dfe3e8;
}

.settings-panel {
  position: absolute;
  bottom: 100%;
  left: 0;
  margin-bottom: 8px;
  background: linear-gradient(180deg, #fafbfc 0%, #f5f7fa 100%);
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  box-shadow: 0 18px 38px -22px rgba(15, 23, 42, 0.16);
  z-index: 1000;
  min-width: 220px;
  padding: 10px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  isolation: isolate;
}

.settings-panel-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 6px 0;
  position: relative;
}

.settings-row-label {
  font-size: 14px;
  font-weight: 500;
  color: #374151;
  flex-shrink: 0;
}

.settings-row-trigger {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  min-height: 36px;
  box-sizing: border-box;
  background: linear-gradient(180deg, #fafbfc 0%, #f5f7fa 100%);
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  cursor: pointer;
  font-size: 13px;
  color: #111827;
  transition: all 0.2s ease;
  min-width: 165px;
  width: 165px;
  justify-content: space-between;
}

.settings-row-trigger:hover {
  background: #eef1f5;
  border-color: #dfe3e8;
}

.settings-row-trigger.kb-active {
  background: #e2e9ff;
  color: #1d4ed8;
  border-color: #c8d7ff;
}

.settings-row-value {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 13px;
  color: inherit;
}

.settings-row-trigger-tools .settings-row-value {
  flex: 1;
  text-align: left;
}

/* 从右侧展开的下拉框 - 底部不超出设置面板 */
.settings-right-dropdown {
  position: absolute;
  top: 0;
  left: 100%;
  margin-left: 8px;
  min-width: 200px;
  max-width: 320px;
  overflow-y: auto;
  background: linear-gradient(180deg, #fafbfc 0%, #f5f7fa 100%);
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  box-shadow: 0 18px 38px -22px rgba(15, 23, 42, 0.16);
  z-index: 1001;
  padding: 10px 0;
}

/* 底部对齐面板底部，顶部可向上延伸 */
.settings-right-dropdown-fixed {
  top: auto;
  bottom: 0;
  max-height: 400px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.settings-right-dropdown-inner {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 0 4px;
}

.settings-right-dropdown .model-group,
.settings-right-dropdown-inner .model-group {
  padding: 8px 0;
}

.settings-right-dropdown .model-group-title {
  padding: 4px 16px;
  font-size: 12px;
  font-weight: 600;
  text-transform: uppercase;
  background-color: transparent;
  text-align: left;
  color: inherit;
}

.settings-right-dropdown .model-option {
  width: 90%;
  padding: 9px 8px;
  text-align: left;
  background: none;
  border: transparent;
  cursor: pointer;
  font-size: 14px;
  transition: background-color 0.2s ease;
  color: #111827;
  border-radius: 10px;
}

.settings-right-dropdown .model-option:hover,
.settings-right-dropdown .model-option.active {
  background: #e7e7e7;
}

.kb-dropdown-right .kb-list {
  flex-direction: column;
  flex-wrap: nowrap;
  align-items: stretch;
  padding: 8px 4px;
}

.kb-dropdown-right .kb-checkbox {
  margin-inline: 0;
}

.kb-dropdown-right .confirm-btn {
  margin-top: 8px;
  margin-left: 0;
  margin-right: 0;
}

/* 设置栏中模型/知识库的右箭头 */
.dropdown-icon-right {
  transform: rotate(-90deg);
}

.dropdown-icon-right.rotate {
  transform: rotate(90deg);
}

.agent-selector {
  position: relative;
}

.agent-dropdown {
  position: absolute;
  bottom: 100%;
  left: 0;
  background: linear-gradient(180deg, #fafbfc 0%, #f5f7fa 100%);
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  box-shadow: 0 18px 38px -22px rgba(15, 23, 42, 0.16);
  z-index: 1000;
  padding: 10px;
  min-width: 140px;
  width: fit-content;
  max-width: 90vw;
  height: 500px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.agent-dropdown-content {
  display: flex;
  gap: 0;
  align-items: flex-start;
  width: 100%;
  height: 100%;
  overflow: hidden;
  position: relative;
}

.agent-dropdown-left {
  min-width: 140px;
  flex-shrink: 0;
  position: absolute;
  top: 0;
  left: 0;
  height: auto;
  z-index: 2;
}

.agent-dropdown-left.has-right {
  padding-right: 10px;
  border-right: 1px solid #e5e7eb;
  margin-right: 10px;
}

.agent-dropdown-right {
  min-width: 200px;
  max-width: 500px;
  flex: 1;
  width: auto;
  height: 100%;
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
  margin-left: 160px;
}

.mode-selector {
  display: flex;
  gap: 0;
  padding: 6px 0;
  width: fit-content;
}

.mode-column {
  width: 120px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.mode-item {
  padding: 8px 12px;
  cursor: pointer;
  border-radius: 10px;
  transition: background-color 0.2s ease, color 0.2s ease;
  color: #303030;
  text-align: left;
}

.mode-item:hover {
  background: #e7e7e7;
  color: #303030;
}
  
  .mode-item.active {
    background: #dbe7ff;
    color: #303030;
    box-shadow: inset 0 0 0 1px #e7e7e7;
  }

.list-column-wrapper {
  display: flex;
  flex-direction: column;
  height: 100%;
  max-height: 100%;
  min-height: 0;
  overflow: hidden;
}

.list-column {
  flex: 1;
  padding: 8px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  overflow-y: auto;
  min-height: 0;
  max-height: 100%;
}

/* 智能体下拉框分块样式：我的创建 / 我的订阅 / 系统预设 */
.agent-dropdown-block {
  margin-bottom: 8px;
}

.agent-dropdown-block-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 6px 10px;
  background: #f1f5f9;
  border-radius: 6px;
  cursor: pointer;
  font-weight: 600;
  color: #334155;
  font-size: 1rem;
  transition: background 0.2s;
}

.agent-dropdown-block-header:hover {
  background: #e2e8f0;
}

.agent-dropdown-block-title {
  flex: 1;
}

.agent-block-toggle {
  flex-shrink: 0;
  transition: transform 0.2s;
}

.agent-block-toggle.expanded {
  transform: rotate(180deg);
}

.agent-dropdown-block-items {
  margin-top: 6px;
  padding-left: 4px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.agent-dropdown-block-items .agent-select {
  padding: 6px 10px;
  font-size: 13px;
}

.agent-dropdown-empty-hint {
  padding: 10px 12px;
  color: #9ca3af;
  font-size: 0.9rem;
}

/* 自定义滚动条样式 - 细竖条 */
.list-column::-webkit-scrollbar,
.agent-checkbox-list::-webkit-scrollbar,
.list-column-single::-webkit-scrollbar,
.list-column-multi::-webkit-scrollbar {
  width: 4px;
}

.list-column::-webkit-scrollbar-track,
.agent-checkbox-list::-webkit-scrollbar-track,
.list-column-single::-webkit-scrollbar-track,
.list-column-multi::-webkit-scrollbar-track {
  background: transparent;
}

.list-column::-webkit-scrollbar-thumb,
.agent-checkbox-list::-webkit-scrollbar-thumb,
.list-column-single::-webkit-scrollbar-thumb,
.list-column-multi::-webkit-scrollbar-thumb {
  background: #d1d5db;
  border-radius: 2px;
}

.list-column::-webkit-scrollbar-thumb:hover,
.agent-checkbox-list::-webkit-scrollbar-thumb:hover,
.list-column-single::-webkit-scrollbar-thumb:hover,
.list-column-multi::-webkit-scrollbar-thumb:hover {
  background: #9ca3af;
}

/* Firefox 滚动条样式 */
.list-column,
.agent-checkbox-list,
.list-column-single,
.list-column-multi {
  scrollbar-width: thin;
  scrollbar-color: #d1d5db transparent;
}

.list-column-select {
  display: flex;
  flex-direction: column;
  gap: 0;
  padding-bottom: 0;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.agent-checkbox-list {
  display: flex;
  flex-direction: column;
  gap: 0;
  overflow-y: auto;
  flex: 1;
  min-height: 0;
  max-height: 100%;
}

.confirm-btn-wrapper {
  padding: 8px;
  border-top: 1px solid #e5e7eb;
  background: linear-gradient(180deg, #fafbfc 0%, #f5f7fa 100%);
  flex-shrink: 0;
  z-index: 10;
}

.agent-checkbox {
  display: flex;
  align-items: center;
  padding: 9px 12px;
  text-align: left;
  background: none;
  border: none;
  cursor: pointer;
  font-size: 14px;
  transition: background-color 0.2s ease;
  color: #111827;
  border-radius: 10px;
  margin: 4px 0;
  width: fit-content;
  min-width: 120px;
  justify-content: flex-start;
}

.agent-checkbox input {
  margin: 0;
  margin-right: 8px;
  accent-color: #2b63ff;
}

.agent-checkbox:hover {
  background: #e7e7e7;
}

.agent-checkbox:has(input:checked) {
  background: #e7e7e7;
  color: #111827;
}

.agent-checkbox-disabled {
  cursor: not-allowed;
  opacity: 0.6;
  pointer-events: none;
}

.agent-checkbox-disabled-input {
  accent-color: #9ca3af;
  cursor: not-allowed;
}

.multi-active {
  background: #007bff;
  color: white;
}
  
.list-column-single, .list-column-multi {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  justify-content: flex-start;
  gap: 4px;
  overflow-y: auto;
  flex: 1;
  min-height: 0;
  max-height: 100%;
}

.input-options-right {
  position: relative;
}

.generation-prompt {
  position: absolute;
  bottom: 100%;
  left: 50%;
  transform: translateX(-50%);
  background: rgba(39, 38, 38, 0.84);
  color: white;
  padding: 8px 16px;
  border-radius: 4px;
  z-index: 1000;
  transition: opacity 0.3s ease;
  margin-bottom: 8px;
  font-size: 14px;
  white-space: nowrap;
}

.generation-prompt::after {
  content: '';
  position: absolute;
  bottom: -6px;
  left: 50%;
  transform: translateX(-50%);
  border-left: 6px solid transparent;
  border-right: 6px solid transparent;
  border-top: 6px solid rgba(39, 38, 38, 0.84);
}
  
.agent-active {
  background: linear-gradient(135deg, #f4f7ff 0%, #e8efff 45%, #f4f8ff 100%) !important;
  color: #2b63ff !important;
  border: 1px solid #2b63ff !important;
  box-shadow: 0 10px 22px -18px rgba(43, 99, 255, 0.45);
}

.kb-selector {
  position: relative;
}

.kb-select-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 14px;
  background: linear-gradient(180deg, #fafbfc 0%, #f5f7fa 100%);
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  cursor: pointer;
  font-size: 14px;
  transition: all 0.2s ease;
  color: #111827;
}

.kb-select-btn:hover {
  background: #eef1f5;
  border-color: #dfe3e8;
  box-shadow: 0 8px 18px -14px rgba(15, 23, 42, 0.45);
}

.kb-active {
  background: #e2e9ff !important;
  color: #1d4ed8;
  border: 1px solid #c8d7ff;
}

.kb-dropdown {
  position: absolute;
  bottom: 100%;
  left: 0;
  background: linear-gradient(180deg, #fafbfc 0%, #f5f7fa 100%);
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  box-shadow: 0 18px 38px -22px rgba(15, 23, 42, 0.16);
  z-index: 1000;
  min-width: 200px;
  padding: 10px 0;
  max-height: 400px;
  overflow-y: auto;
}

.kb-list {
  display: flex;
  flex-direction: row;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
}

.kb-checkbox {
  display: flex;
  align-items: center;
  margin: 0;
  cursor: pointer;
  margin-inline: 10px;
  padding: 9px 10px;
  border-radius: 10px;
  transition: background-color 0.2s ease, color 0.2s ease, box-shadow 0.2s ease;
}

.kb-checkbox input {
  margin: 0;
  margin-right: 8px;
  accent-color: #2b63ff;
}

.kb-checkbox span {
  flex-direction: row;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
}

.kb-checkbox:hover {
  background: #f4f6f8;
}

.kb-checkbox input:checked + span,
.kb-checkbox input:checked + * {
  color: #2b63ff;
  font-weight: 600;
}

.confirm-btn {
  margin-top: 8px;
  padding: 8px 14px;
  background: linear-gradient(135deg, #f4f7ff 0%, #e8efff 45%, #f4f8ff 100%);
  color: #2b63ff;
  border: 1px solid #2b63ff;
  border-radius: 10px;
  cursor: pointer;
  width: 80%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  margin-left: auto;
  margin-right: auto;
  transition: all 0.2s ease;
  box-shadow: 0 10px 22px -18px rgba(43, 99, 255, 0.45);
}

.confirm-btn-wrapper .confirm-btn {
  margin-top: 0;
  width: 100%;
  margin-left: 0;
  margin-right: 0;
}

.confirm-btn:disabled {
  background: #ccc;
  color: #666;
  border-color: #ccc;
  cursor: not-allowed;
  box-shadow: none;
}

.confirm-btn:not(:disabled):hover {
  background: linear-gradient(135deg, #e8efff 0%, #d6e4ff 45%, #e8efff 100%);
  border-color: #2563eb;
  color: #2563eb;
  box-shadow: 0 10px 22px -18px rgba(43, 99, 255, 0.6);
}

.upload-option {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 14px;
  background: linear-gradient(180deg, #fafbfc 0%, #f5f7fa 100%);
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  cursor: pointer;
  font-size: 14px;
  transition: all 0.2s ease;
  color: #111827;
}

.upload-option:hover {
  background: #eef1f5;
  border-color: #dfe3e8;
  box-shadow: 0 8px 18px -14px rgba(15, 23, 42, 0.45);
}

.selected-files {
  font-size: 12px;
  color: #666;
  display: flex;
  align-items: flex-start;
  justify-content: center;
  flex-wrap: wrap;
  gap: 10px;
  background: transparent;
}

.selected-file-item {
  position: relative;
  width: 70px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  padding: 2px;
}

.selected-file-thumb,
.selected-file-icon {
  width: 40px;
  height: 40px;
  border-radius: 6px;
  object-fit: cover;
  border: none;
  background: transparent;
}

.selected-file-icon {
  object-fit: contain;
  padding: 4px;
  background: transparent;
}

.selected-file-name {
  max-width: 64px;
  text-align: center;
  font-size: 11px;
  color: #374151;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.remove-file-btn {
  position: absolute;
  top: -4px;
  right: -4px;
  width: 16px;
  height: 16px;
  line-height: 14px;
  border-radius: 50%;
  border: none;
  background: transparent;
  cursor: pointer;
  padding: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  transition: transform 0.2s ease;
}

.remove-file-btn:hover {
  transform: scale(1.05);
}

.remove-file-btn img {
  width: 12px;
  height: 12px;
  display: block;
}

.loading-spinner {
  width: 18px;
  height: 18px;
  border: 2px solid #f5f5f5;
  border-top: 2px solid transparent;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}
</style>
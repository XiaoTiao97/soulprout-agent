<!-- AgentOption.vue -->
<template>
  <div class="agent-option-overlay" @click="handleOverlayClick">
    <div class="agent-option-container" @click.stop>
      <div class="agent-option-header">
        <h2>智能体库</h2>
        <button class="close-btn" @click="$emit('close')">
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
            <path d="M15 5L5 15M5 5L15 15" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
        </button>
      </div>

      <!-- 智能体内容 -->
      <div class="agent-content">
        <div class="agent-sidebar">
          <div class="create-agent" @click="startCreate" title="创建智能体">
            <div class="plus-box">
                <img src="@/assets/images/add_icon.svg" width="18" height="18" />
            </div>
          </div>
          <div v-if="loading" class="loading-state">
            <div class="loading-spinner"></div>
            <p>Loading agents...</p>
          </div>

          <div v-else-if="error" class="error-state">
            <p>{{ error }}</p>
            <button @click="fetchAgentList" class="retry-btn">Retry</button>
          </div>

          <div v-else class="agent-list">
            <div 
              v-for="agent in filteredAgentList" 
              :key="agent.agent_id"
              :class="['agent-item', { selected: selectedAgent && selectedAgent.agent_id === agent.agent_id }]"
              @click="selectAgent(agent)"
            >
              <h3 class="agent-name">{{ agent.name }}</h3>
            </div>

            <!-- 空状态 -->
            <div v-if="filteredAgentList.length === 0" class="empty-state">
              <p>暂无智能体</p>
            </div>
          </div>
        </div>

        <div class="agent-main">
          <div v-if="isCreating">
            <div class="agent-info">
              <div class="agent-info-header">
                <div class="name-wrapper">
                  <h3>创建智能体</h3>
                </div>
                <div class="agent-actions">
                  <button class="action-btn save-edit" @click="confirmCreate">创建</button>
                  <button class="action-btn cancel-edit" @click="cancelCreate">取消</button>
                </div>
              </div>
              <div class="agent-info-content">
                <div class="field-group">
                  <label>模型<span class="required">*</span></label>
                  <div class="model-selector" ref="newModelSelectorRef">
                    <button class="model-select-btn" type="button" @click="toggleNewModelSelector">
                      <span>{{ newSelectedModelDisplay }}</span>
                      <svg class="dropdown-icon" :class="{ 'rotate': showNewModelSelector }" width="12" height="12" viewBox="0 0 12 12" fill="currentColor">
                        <path d="M6 8L2 4h8l-4 4z"/>
                      </svg>
                    </button>
                    <div class="model-dropdown" v-show="showNewModelSelector">
                      <div v-for="provider in modelProviders" :key="provider.model_source" class="model-group">
                        <div class="model-group-title">{{ provider.model_source }}</div>
                        <button 
                          v-for="model in provider.models" 
                          :key="model.id"
                          class="model-option"
                          :class="{ 'active': newModel === model.id }"
                          type="button"
                          @click="selectNewModel(provider.model_source, model.id)"
                        >
                          {{ model.name }}
                        </button>
                      </div>
                    </div>
                  </div>
                </div>
                <div class="field-group">
                  <label>名称<span class="required">*</span></label>
                  <input v-model="newName" class="edit-input-agent" placeholder="请使用英文和下划线(_)组合命名，例如：example_agent">
                </div>
                <div class="field-group">
                  <label>描述<span class="required">*</span></label>
                  <textarea v-model="newDescription" class="edit-textarea" placeholder="请描述智能体的用途，或者你在什么情况/场景下会使用该智能体"></textarea>
                </div>
                <div class="field-group">
                  <label>系统提示词</label>
                  <textarea v-model="newSystemPrompt" class="edit-textarea" placeholder="请为智能体配置系统提示词，写明你希望智能体完成什么任务，任务的逻辑顺序，以及使用什么工具或知识库"></textarea>
                </div>
                <div class="field-group">
                  <label>公告</label>
                  <textarea v-model="newAnnouncement" class="edit-textarea" placeholder="给用户的提示，告知用户如何使用该智能体"></textarea>
                </div>
                <div class="field-group">
                  <label>工具</label>
                  <div class="tools-selection">
                    <div v-for="tool in allTools" :key="tool" class="tool-checkbox">
                      <input type="checkbox" :id="'new-' + tool" :value="tool" v-model="selectedNewTools" />
                      <label :for="'new-' + tool">{{ tool }}</label>
                    </div>
                  </div>
                </div>
                <div class="field-group">
                  <label>子智能体</label>
                  <div class="agents-selection">
                    <div v-for="agent in filteredSubAgents" :key="agent.agent_id" class="agent-checkbox">
                      <input type="checkbox" :id="'new-sub-' + agent.agent_id" :value="agent.name" v-model="selectedNewSubAgents" />
                      <label :for="'new-sub-' + agent.agent_id">{{ agent.name }}</label>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
          <div v-else-if="!selectedAgent" class="no-selection">
            <p>请选择一个智能体查看详情</p>
          </div>

          <div v-else>
            <div class="agent-info">
                <div class="agent-info-header">
                  <div class="name-wrapper">
                    <h3 v-if="!isEditing">{{ selectedAgent.name }}</h3>
                    <h3 v-else>编辑智能体</h3>
                    <button v-if="!isEditing" class="action-btn edit-agent" @click="startEdit">
                      <img src="@/assets/images/edit_icon.svg" width="18" height="18" />
                    </button>
                  </div>
                  <div class="agent-actions">
                    <button v-if="!isEditing" class="action-btn delete-agent" @click="deleteAgent(selectedAgent.agent_id)">
                    <img src="@/assets/images/delete.svg" width="18" height="18" />
                    </button>
                    <template v-if="isEditing">
                      <button class="action-btn save-edit" @click="saveEdit">保存</button>
                      <button class="action-btn cancel-edit" @click="cancelEdit">取消</button>
                    </template>
                  </div>
                </div>
                <div class="agent-info-content">
                  <div class="field-group" v-if="isEditing">
                    <label>模型<span class="required">*</span></label>
                    <div class="model-selector" ref="editModelSelectorRef">
                      <button class="model-select-btn" type="button" @click="toggleEditModelSelector">
                        <span>{{ editedSelectedModelDisplay }}</span>
                        <svg class="dropdown-icon" :class="{ 'rotate': showEditModelSelector }" width="12" height="12" viewBox="0 0 12 12" fill="currentColor">
                          <path d="M6 8L2 4h8l-4 4z"/>
                        </svg>
                      </button>
                      <div class="model-dropdown" v-show="showEditModelSelector">
                        <div v-for="provider in modelProviders" :key="provider.model_source" class="model-group">
                          <div class="model-group-title">{{ provider.model_source }}</div>
                          <button 
                            v-for="model in provider.models" 
                            :key="model.id"
                            class="model-option"
                            :class="{ 'active': editedModel === model.id }"
                            type="button"
                            @click="selectEditModel(provider.model_source, model.id)"
                          >
                            {{ model.name }}
                          </button>
                        </div>
                      </div>
                    </div>
                  </div>
                  <div class="field-group" v-if="!isEditing">
                    <label>模型</label>
                    <p>{{ selectedAgent.model_source }}: {{ selectedAgent.model }}</p>
                  </div>
                  <div class="field-group" v-if="isEditing">
                    <label>名称<span class="required">*</span></label>
                    <input v-model="editedName" class="edit-input-agent" placeholder="请使用英文和下划线(_)组合命名，例如：example_agent">
                  </div>
                  <div class="field-group">
                    <label>描述<span class="required" v-if="isEditing">*</span></label>
                    <p v-if="!isEditing">{{ selectedAgent.description }}</p>
                    <textarea v-else v-model="editedDescription" class="edit-textarea" placeholder="智能体描述"></textarea>
                  </div>
                  <div class="field-group">
                    <label>系统提示词<span class="required" v-if="isEditing">*</span></label>
                    <p v-if="!isEditing">{{ selectedAgent.system_prompt }}</p>
                    <textarea v-else v-model="editedSystemPrompt" class="edit-textarea" placeholder="系统提示词"></textarea>
                  </div>
                  <div class="field-group">
                    <label>公告</label>
                    <p v-if="!isEditing">{{ selectedAgent.announcement }}</p>
                    <textarea v-else v-model="editedAnnouncement" class="edit-textarea" placeholder="公告"></textarea>
                  </div>
                  <div class="field-group">
                    <label>工具</label>
                    <p v-if="!isEditing">{{ selectedAgent.tools.join(', ') }}</p>
                    <div v-else class="tools-selection">
                      <div v-for="tool in allTools" :key="tool" class="tool-checkbox">
                        <input type="checkbox" :id="'edit-' + tool" :value="tool" v-model="selectedEditedTools" />
                        <label :for="'edit-' + tool">{{ tool }}</label>
                      </div>
                    </div>
                  </div>
                  <div class="field-group">
                    <label>子智能体</label>
                    <p v-if="!isEditing">{{ selectedAgent.agents?.join(', ') || '无' }}</p>
                    <template v-else>
                      <div v-if="filteredSubAgents.length === 0" class="empty-state">没有可用子智能体</div>
                      <div v-else class="agents-selection">
                        <div v-for="agent in filteredSubAgents" :key="agent.agent_id" class="agent-checkbox">
                          <input type="checkbox" :id="'edit-sub-' + agent.agent_id" :value="agent.name" v-model="selectedEditedSubAgents" />
                          <label :for="'edit-sub-' + agent.agent_id">{{ agent.name }}</label>
                        </div>
                      </div>
                    </template>
                  </div>
                  <div class="field-group">
                    <label>知识库</label>
                    <p v-if="!isEditing">{{ selectedAgent.kbs.join(', ') }}</p>
                    <textarea v-else v-model="editedKbs" class="edit-textarea" placeholder="知识库列表，用逗号分隔"></textarea>
                  </div>
                </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 删除确认模态 -->
      <div v-if="showConfirmModal" class="confirm-modal">
        <div class="confirm-content">
          <h3>确认删除</h3>
          <p>{{ confirmMessage }}</p>
          <div class="confirm-buttons">
            <button class="confirm-btn" @click="confirmDelete">确认</button>
            <button class="cancel-btn" @click="cancelConfirm">取消</button>
          </div>
        </div>
      </div>

      <!-- 错误模态 -->
      <div v-if="showErrorModal" class="error-modal">
        <div class="error-content">
          <h3><img src="@/assets/images/error_icon.svg" width="18" height="18" alt="错误" /> 错误</h3>
          <p>{{ errorMessage }}</p>
          <div class="confirm-buttons">
            <button class="ok-btn" @click="showErrorModal = false">确定</button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed, onUnmounted } from 'vue'
import axios from 'axios'

defineEmits<{ close: [] }>()
const { userId } = defineProps<{ userId: string }>()

// 接口定义
interface Agent {
  agent_id: string
  name: string
  description: string
  system_prompt: string
  tools: string[]
  kbs: string[]
  announcement?: string
  create_at?: string
  updated_at?: string
  agents?: string[] | null
  model_source?: string
  model?: string
}

const agentList = ref<Agent[]>([])
const selectedAgent = ref<Agent | null>(null)
const loading = ref(false)
const error = ref('')
const isEditing = ref(false)
const editedName = ref('')
const editedDescription = ref('')
const editedSystemPrompt = ref('')
const editedAnnouncement = ref('')
const editedTools = ref('')
const editedKbs = ref('')

const isCreating = ref(false)
const newName = ref('')
const newDescription = ref('')
const newSystemPrompt = ref('')
const newAnnouncement = ref('')

const showConfirmModal = ref(false)
const confirmMessage = ref('')
const currentAgentIdForDelete = ref('')
const currentUserIdForDelete = ref('')

const showErrorModal = ref(false)
const errorMessage = ref('')

const allTools = ref<string[]>([])
const selectedNewTools = ref<string[]>([])
const selectedEditedTools = ref<string[]>([])
const selectedNewSubAgents = ref<string[]>([])
const selectedEditedSubAgents = ref<string[]>([])

const model_list = ref<Record<string, string[]>>({})
const showNewModelSelector = ref(false)
const newModelSelectorRef = ref<HTMLElement>()
const showEditModelSelector = ref(false)
const editModelSelectorRef = ref<HTMLElement>()
const newModelSource = ref('')
const newModel = ref('')
const editedModelSource = ref('')
const editedModel = ref('')

// Add computed for modelProviders
const modelProviders = computed<Array<{model_source: string, models: Array<{id: string, name: string}> }>>(() => {
  return Object.entries(model_list.value).map(([providerName, models]) => ({
    model_source: providerName,
    models: models.map(model => ({
      id: model,
      name: model
    })), 
  }))
})

// For new:
const newSelectedModelDisplay = computed<string>(() => {
  if (!newModel.value) return '选择模型'
  for (const provider of modelProviders.value) {
    const model = provider.models.find(m => m.id === newModel.value)
    if (model) return `${provider.model_source}: ${model.name}`
  }
  return '选择模型'
})

// For edit:
const editedSelectedModelDisplay = computed<string>(() => {
  if (!editedModel.value) return '选择模型'
  for (const provider of modelProviders.value) {
    const model = provider.models.find(m => m.id === editedModel.value)
    if (model) return `${provider.model_source}: ${model.name}`
  }
  return '选择模型'
})

// Filter out invalid/empty agents to prevent blank items
const filteredAgentList = computed(() => {
  return agentList.value.filter(agent => agent.agent_id && agent.name?.trim())
})

const filteredSubAgents = computed(() => {
  let agents = filteredAgentList.value
  if (isEditing && selectedAgent.value) {
    agents = agents.filter(agent => agent.agent_id !== selectedAgent.value!.agent_id);
  }
  return agents;
})

async function fetchAgentList() {
  loading.value = true
  error.value = ''
  try {
    const response = await axios.get(`/api/agent_cards/${userId}`)
    console.log(response.data)
    agentList.value = response.data.map((item: any) => ({
      ...item,
      tools: item.tools || [],
      kbs: item.kbs || [],
      agents: item.agents || null,
      model_source: item.model_source || '',
      model: item.model || ''
    })) // Ensure arrays are initialized
    // 如果有选中的，更新它
    if (selectedAgent.value) {
      const updated = agentList.value.find(a => a.agent_id === selectedAgent.value!.agent_id)
      if (updated) selectedAgent.value = updated
    }
  } catch (err) {
    error.value = 'Failed to load agents'
  } finally {
    loading.value = false
  }
}

async function fetchTools() {
  try {
    const response = await axios.get('/api/tools_info')
    allTools.value = response.data.map((tool: any) => tool.name)
    console.log(allTools.value)
  } catch (err) {
    console.error('Failed to fetch tools:', err)
  }
}

async function fetchModels() {
  try {
    const response = await axios.get('/api/message/models')
    model_list.value = response.data
  } catch (err) {
    console.error('Failed to fetch models:', err)
  }
}

function toggleNewModelSelector() {
  showNewModelSelector.value = !showNewModelSelector.value
}

function toggleEditModelSelector() {
  showEditModelSelector.value = !showEditModelSelector.value
}

function selectNewModel(model_source: string, model: string) {
  newModelSource.value = model_source
  newModel.value = model
  showNewModelSelector.value = false
}

function selectEditModel(model_source: string, model: string) {
  editedModelSource.value = model_source
  editedModel.value = model
  showEditModelSelector.value = false
}

function handleNewClickOutside(event: Event) {
  if (newModelSelectorRef.value && !newModelSelectorRef.value.contains(event.target as Node)) {
    showNewModelSelector.value = false
  }
}

function handleEditClickOutside(event: Event) {
  if (editModelSelectorRef.value && !editModelSelectorRef.value.contains(event.target as Node)) {
    showEditModelSelector.value = false
  }
}

function selectAgent(agent: Agent) {
  selectedAgent.value = agent
  isEditing.value = false
  isCreating.value = false
}

function startCreate() {
  selectedAgent.value = null
  isCreating.value = true
  // Reset new agent fields
  newName.value = ''
  newDescription.value = ''
  newSystemPrompt.value = ''
  newAnnouncement.value = ''
  selectedNewTools.value = []
  selectedNewSubAgents.value = []
  newModelSource.value = ''
  newModel.value = ''
}

async function confirmCreate() {
  if (!newName.value.trim()) {
    errorMessage.value = '名称不能为空'
    showErrorModal.value = true
    return
  }
  if (!newDescription.value.trim()) {
    errorMessage.value = '描述不能为空'
    showErrorModal.value = true
    return
  }
  if (!newModelSource.value || !newModel.value) {
    errorMessage.value = '模型不能为空'
    showErrorModal.value = true
    return
  }
  const newAgent = {
    user_id: userId,
    agent_id: "",
    name: newName.value,
    description: newDescription.value,
    system_prompt: newSystemPrompt.value,
    tools: selectedNewTools.value,
    agents: selectedNewSubAgents.value.length > 0 ? selectedNewSubAgents.value : null,
    kbs: [],
    announcement: newAnnouncement.value,
    model_source: newModelSource.value,
    model: newModel.value
  }
  try {
    const response = await axios.post('/api/agent_card/create', newAgent)
    if (response.data.success) {
      await fetchAgentList()
      isCreating.value = false
      // Optionally select the new agent
      const createdAgent = agentList.value.find(a => a.name === newName.value)
      if (createdAgent) selectAgent(createdAgent)
    } else {
      errorMessage.value = response.data.message || '创建失败'
      showErrorModal.value = true
    }
  } catch (err) {
    errorMessage.value = '创建失败: ' + (err as Error).message
    showErrorModal.value = true
  }
}

function cancelCreate() {
  isCreating.value = false
}

async function deleteAgent(agentId: string) {
  confirmMessage.value = '确认删除此智能体吗？'
  currentAgentIdForDelete.value = agentId
  currentUserIdForDelete.value = userId
  showConfirmModal.value = true
}

async function confirmDelete() {
  showConfirmModal.value = false
  try {
    const response = await axios.post(`/api/agent_card/${currentAgentIdForDelete.value}/delete/${currentUserIdForDelete.value}`)
    if (!response.data.success) {
      errorMessage.value = response.data.message || '删除失败'
      showErrorModal.value = true
    }
    fetchAgentList()
    if (selectedAgent.value?.agent_id === currentAgentIdForDelete.value) {
      selectedAgent.value = null
    }
  } catch (err) {
    errorMessage.value = '删除失败: ' + (err as Error).message
    showErrorModal.value = true
  }
}

function cancelConfirm() {
  showConfirmModal.value = false
}

function startEdit() {
  if (selectedAgent.value) {
    editedName.value = selectedAgent.value.name
    editedDescription.value = selectedAgent.value.description
    editedSystemPrompt.value = selectedAgent.value.system_prompt
    editedAnnouncement.value = selectedAgent.value.announcement || ''
    selectedEditedTools.value = [...(selectedAgent.value.tools || [])]
    selectedEditedSubAgents.value = [...(selectedAgent.value.agents || [])]
    editedKbs.value = selectedAgent.value.kbs.join(', ')
    editedModelSource.value = selectedAgent.value.model_source || ''
    editedModel.value = selectedAgent.value.model || ''
    isEditing.value = true
  }
}

async function saveEdit() {
  if (!selectedAgent.value) return
  if (!editedName.value.trim()) {
    errorMessage.value = '名称不能为空'
    showErrorModal.value = true
    return
  }
  if (!editedDescription.value.trim()) {
    errorMessage.value = '描述不能为空'
    showErrorModal.value = true
    return
  }
  if (!editedModelSource.value || !editedModel.value) {
    errorMessage.value = '模型不能为空'
    showErrorModal.value = true
    return
  }
  try {
    const updatedAgent = {
      user_id: userId,
      agent_id: selectedAgent.value.agent_id,
      name: editedName.value,
      description: editedDescription.value,
      system_prompt: editedSystemPrompt.value,
      announcement: editedAnnouncement.value,
      tools: selectedEditedTools.value,
      agents: selectedEditedSubAgents.value.length > 0 ? selectedEditedSubAgents.value : null,
      kbs: editedKbs.value.split(',').map(k => k.trim()).filter(k => k),
      model_source: editedModelSource.value,
      model: editedModel.value
    }
    const response = await axios.post(`/api/agent_card/${selectedAgent.value.agent_id}/update`, updatedAgent)
    if (response.data.success) {
      Object.assign(selectedAgent.value, updatedAgent)
      // 更新列表
      const index = agentList.value.findIndex(a => a.agent_id === selectedAgent.value!.agent_id)
      if (index !== -1) {
        Object.assign(agentList.value[index], updatedAgent)
      }
      isEditing.value = false
      await fetchAgentList() // Refresh the list to ensure consistency
    } else {
      errorMessage.value = response.data.message || '更新失败'
      showErrorModal.value = true
    }
  } catch (err) {
    errorMessage.value = '更新失败: ' + (err as Error).message
    showErrorModal.value = true
  }
}

function cancelEdit() {
  isEditing.value = false
  editedName.value = ''
  editedDescription.value = ''
  editedSystemPrompt.value = ''
  editedAnnouncement.value = ''
  selectedEditedTools.value = []
  selectedEditedSubAgents.value = []
  editedKbs.value = ''
  editedModelSource.value = ''
  editedModel.value = ''
}

function handleOverlayClick() {
  // 点击遮罩关闭
}

onMounted(() => {
  if (userId) fetchAgentList()
  fetchTools()
  fetchModels()
  document.addEventListener('click', handleNewClickOutside)
  document.addEventListener('click', handleEditClickOutside)
})

onUnmounted(() => {
  document.removeEventListener('click', handleNewClickOutside)
  document.removeEventListener('click', handleEditClickOutside)
})
</script>

<style scoped>
/* Copy styles from KBOption.vue and replace kb with agent */
.agent-option-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.agent-option-container {
  background: white;
  border-radius: 12px;
  width: 90%;
  width: 120vh;
  height: 80vh;
  overflow: hidden;
  box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04);
  display: flex;
  flex-direction: column;
}

.agent-option-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px 24px;
  border-bottom: 1px solid #e5e7eb;
  background: #f9fafb;
  color: darkslategray;
}

.agent-option-header h2 {
  margin: 0;
  font-size: 1.5rem;
  font-weight: 600;
  color: #2f4f4f;
}

.close-btn {
  background: none;
  border: none;
  cursor: pointer;
  color: #6b7280;
  padding: 4px;
  border-radius: 6px;
  transition: all 0.2s;
}

.close-btn:hover {
  background-color: #f3f4f6;
  color: darkslategrey;
}

.agent-content {
  flex: 1;
  display: flex;
  overflow: hidden;
}

.agent-sidebar {
  width: 300px;
  border-right: 1px solid #e5e7eb;
  overflow-y: auto;
  padding: 16px;
  background: #f9fafb;
}

.agent-main {
  flex: 1;
  padding: 24px;
  overflow-y: auto;
}

.no-selection {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #6b7280;
}

.agent-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.agent-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s;
}

.agent-item:hover {
  box-shadow: 0 2px 4px rgba(0,0,0,0.1);
}

.agent-item.selected {
  background: #c5c5c565;
  border-color: transparent;
}

.agent-name {
  margin: 0;
  width: 70%;
  font-size: 1.125rem;
  font-weight: 500;
  word-wrap: break-word;
}

.agent-type {
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 0.875rem;
  font-weight: 400;
}
.single-type {
  color: #ff0000;
  border: 1px solid #ff0000;
}
.multi-type {
  color: #0000ff;
  border: 1px solid #0000ff;
}

.agent-info {
  margin-bottom: 16px;
}

.agent-info p {
  color: #6b7280;
  margin: 8px 0;
}

.agent-info-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.agent-actions {
  display: flex;
  gap: 8px;
}

.action-btn {
  padding: 4px 8px;
  border-radius: 4px;
  border: none;
  cursor: pointer;
  font-size: 0.875rem;
}

.delete-agent,
.delete-doc {
  background: none;
  padding: 0;
  border: none;
  cursor: pointer;
  font-size: 0.875rem;
  transition: opacity 0.2s;
}

.delete-agent:hover,
.delete-doc:hover {
  opacity: 0.7;
}

.loading-state,
.error-state,
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 20px;
  text-align: center;
  color: #6b7280;
}

.loading-spinner {
  width: 32px;
  height: 32px;
  border: 2px solid #f3f3f3;
  border-top: 2px solid #068b12;
  border-radius: 50%;
  animation: spin 1s linear infinite;
  margin-bottom: 16px;
}

.loading-spinner.small {
  width: 16px;
  height: 16px;
  border-width: 2px;
  margin-bottom: 0;
}

.loading-spinner.inline {
  display: inline-block;
  vertical-align: middle;
  margin-left: 8px;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.retry-btn {
  margin-top: 16px;
  padding: 8px 16px;
  background: #3b82f6;
  color: white;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-weight: 500;
  transition: background-color 0.2s;
}

.retry-btn:hover {
  background: #2563eb;
}

.create-agent {
  display: flex;
  justify-content: center;
  align-items: center;
  background: #f9fafb;
  border-bottom: 5px solid transparent;
}

.plus-box {
  width: 100%;
  height: 40px;
  border: 1px solid #c4c1c17a;
  border-radius: 8px;
  display: flex;
  justify-content: center;
  align-items: center;
  font-size: 24px;
  color: darkslategrey;
  font-family: "AlimamaShuHeiTi-Bold";
  font-size: 16px;
  font-weight: bold;
  cursor: pointer;
  background: #10b981;
  transition: all 0.2s;
}

.plus-box:hover {
  background: #059669;
  box-shadow: 0 2px 4px rgba(0,0,0,0.1);
}

.confirm-modal,
.error-modal {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0,0,0,0.5);
  display: flex;
  justify-content: center;
  align-items: center;
}

.confirm-content,
.error-content {
  background: white;
  padding: 20px;
  border-radius: 8px;
  width: 300px;
  text-align: center;
}

.confirm-buttons {
  display: flex;
  justify-content: space-around;
  margin-top: 20px;
}

.confirm-btn {
  background: #10b981;
  color: white;
  padding: 8px 16px;
  border: none;
  border-radius: 4px;
  cursor: pointer;
}

.confirm-btn:hover {
  background: #059669;
}

.cancel-btn,
.ok-btn {
  background: #f3f4f6;
  color: #4b5563;
  padding: 8px 16px;
  border: none;
  border-radius: 4px;
  cursor: pointer;
}

.cancel-btn:hover,
.ok-btn:hover {
  background: #e5e7eb;
}

/* 响应式 */
@media (max-width: 768px) {
  .agent-content {
    flex-direction: column;
  }
  
  .agent-sidebar {
    width: auto;
    border-right: none;
    border-bottom: 1px solid #e5e7eb;
  }
  
  .agent-main {
    padding: 16px;
  }
}

@media (max-width: 640px) {
  .agent-option-container {
    width: 95%;
    max-height: 90vh;
  }
}

.edit-agent {
  background: none;
  padding: 0;
  border: none;
  cursor: pointer;
}

.edit-agent:hover {
  opacity: 0.7;
}

.edit-input-agent {
  width: 100%;
  padding: 12px;
  border: 1px solid #d1d5db;
  border-radius: 6px;
  font-family: inherit;
  font-size: 1rem;
  line-height: 1.5;
  background: #f9fafb;
  transition: border-color 0.2s;
}

.edit-input-agent::placeholder {
  color: #9ca3af; /* Standard gray color to match typical textarea placeholder */
  font-family: inherit;
  font-size: 1rem;
  opacity: 1; /* Ensure full opacity */
  font-weight: 400;
}

.edit-input-agent:focus {
  outline: none;
  border-color: #2aaf66a1;
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
}
  
.edit-textarea {
  width: 100%;
  min-height: 80px;
  padding: 12px;
  border: 1px solid #d1d5db;
  border-radius: 6px;
  resize: vertical;
  font-family: inherit;
  font-size: 1rem;
  line-height: 1.5;
  background: #f9fafb;
  transition: border-color 0.2s;
}

.edit-textarea::placeholder {
  color: #9ca3af;
  font-family: inherit;
  font-size: 1rem;
  opacity: 1;
}

.edit-textarea:focus {
  outline: none;
  border-color: #2aaf66a1;
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
}

.save-edit {
  background: #10b981;
  color: white;
}

.save-edit:hover {
  background: #059669;
}

.cancel-edit {
  background: #f3f4f6;
  color: #4b5563;
}

.cancel-edit:hover {
  background: #e5e7eb;
}

.name-wrapper {
  display: flex;
  align-items: center;
  gap: 8px;
}

.name-wrapper h3 {
  margin: 0;
}

.name-wrapper .edit-input-agent {
  flex: 1;
}

.agent-info-content {
  margin-top: 8px;
  padding-right: 16px;
}

.field-group {
  margin-bottom: 24px;
  border-bottom: 1px solid #d1d5db8e;
}

.field-group label {
  display: block;
  font-weight: 500;
  margin-bottom: 4px;
  color: #2d333b;
}

.required {
  color: red;
  margin-left: 4px;
}

.tools-selection {
  max-height: 200px;
  overflow-y: auto;
  border: 1px solid #d1d5db;
  border-radius: 6px;
  padding: 8px;
  background: #f9fafb;
}

.tool-checkbox {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
}

.tool-checkbox input {
  margin: 0;
  accent-color: #10b981;
}

.tool-checkbox label {
  cursor: pointer;
}

.agents-selection {
  max-height: 200px;
  overflow-y: auto;
  border: 1px solid #d1d5db;
  border-radius: 6px;
  padding: 8px;
  background: #f9fafb;
}

.agent-checkbox {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
}

.agent-checkbox input {
  margin: 0;
  accent-color: #10b981;
}

.agent-checkbox label {
  cursor: pointer;
}

.model-selector {
  position: relative;
}

.model-select-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 8px 12px;
  background: white;
  border: 1px solid #ddd;
  border-radius: 4px;
  cursor: pointer;
}

.dropdown-icon {
  transition: transform 0.2s;
}

.dropdown-icon.rotate {
  transform: rotate(180deg);
}

.model-dropdown {
  position: absolute;
  top: 100%;
  left: 0;
  background: white;
  border: 1px solid #ddd;
  border-radius: 4px;
  box-shadow: 0 2px 4px rgba(0,0,0,0.1);
  z-index: 10;
  min-width: 200px;
  max-height: 300px;
  overflow-y: auto;
}

.model-group-title {
  padding: 8px 12px;
  font-weight: bold;
  background: #f5f5f5;
}

.model-option {
  display: block;
  width: 100%;
  padding: 8px 12px;
  background: none;
  border: none;
  text-align: left;
  cursor: pointer;
}

.model-option:hover {
  background: #f0f0f0;
}

.model-option.active {
  background: #007bff;
  color: white;
}

</style>

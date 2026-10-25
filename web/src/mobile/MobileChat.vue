<template>
  <div class="phone">
    <header class="topbar">
      <button type="button" class="icon-btn" :aria-label="t('mobile.menu')" @click="drawerOpen = true">
        <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M4 7h16M4 12h16M4 17h16" />
        </svg>
      </button>
      <div class="topbar-title">
        <strong>{{ headerTitle }}</strong>
        <span>{{ chatMode === 'soulprout' ? t('conversation.soulHint') : t('conversation.taskHint') }}</span>
      </div>
      <button type="button" class="file-btn" @click="openFileList">
        <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.8">
          <path d="M7 3h7l5 5v13a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1z" />
          <path d="M14 3v6h6" />
        </svg>
        <span>{{ t('mobile.files') }}</span>
      </button>
    </header>

    <main class="mobile-chat">
      <div v-if="!ready" class="booting">{{ t('mobile.entering') }}</div>
      <ChatWindow
        v-else
        :chat_request="chat_request"
        :agent_message_list="agent_message_list"
        :currentStreamingMessage="currentStreamingMessage"
        :isGenerating="isGenerating"
        :planStreamContent="chatPlanStreamForWindow"
        :planProgressContent="chatPlanProgressForWindow"
        :blueprintPending="blueprintStreamPending"
        :isLoading="isLoading"
        :timeoutError="timeoutError"
        :model_list="model_list"
        :userId="currentUserId"
        :username="currentUsername"
        :reloadStreamingUiToken="reloadStreamingUiToken"
        :welcomeAnimationToken="welcomeAnimationToken"
        :chatMode="chatMode"
        :toolMessages="toolMessages"
        :soulMessagesHasMore="soulMessagesHasMore"
        :soulMessagesLoadingMore="soulMessagesLoadingMore"
        @loadMoreSoulMessages="loadMoreSoulMessages"
        @sendMessage="handleSendMessage"
        @stopGeneration="stopGeneration"
        @openFilePreview="openFilePreview"
        @openWebPreview="openWebPreview"
      />
    </main>

    <div v-if="drawerOpen" class="backdrop" @click="drawerOpen = false"></div>
    <aside class="drawer" :class="{ 'drawer--open': drawerOpen }">
      <div class="drawer-head">
        <img src="@/assets/images/logo.png" alt="Soulprout" class="drawer-logo" />
        <button type="button" class="icon-btn" :aria-label="t('mobile.close')" @click="drawerOpen = false">
          <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M6 6l12 12M18 6L6 18" />
          </svg>
        </button>
      </div>

      <div class="mode-section">
        <div class="mode-header">
          <span>{{ t('conversation.chatMode') }}</span>
          <span class="mode-hint">{{ chatMode === 'soulprout' ? t('conversation.soulHint') : t('conversation.taskHint') }}</span>
        </div>
        <div class="mode-switch" :data-active="chatMode">
          <span class="mode-thumb"></span>
          <button type="button" class="mode-option" :class="{ 'mode-option--active': chatMode === 'soulprout' }" @click="switchMode('soulprout')">
            {{ t('conversation.soulLabel') }}
          </button>
          <button type="button" class="mode-option" :class="{ 'mode-option--active': chatMode === 'task' }" @click="switchMode('task')">
            {{ t('conversation.taskLabel') }}
          </button>
        </div>
      </div>

      <template v-if="chatMode === 'task'">
        <button type="button" class="new-task" @click="startNewTask">
          <img src="@/assets/images/create_conversation.svg" width="18" height="18" alt="" />
          {{ t('conversation.newTask') }}
        </button>

        <div v-if="visibleRunning.length" class="running-block">
          <div class="section-label">{{ t('conversation.runningNow') }}</div>
          <button
            v-for="item in visibleRunning"
            :key="item.conversation_id"
            type="button"
            class="task-row"
            :class="{ 'task-row--active': item.conversation_id === chat_request.conversation_id }"
            @click="openRunning(item)"
          >
            <span class="dot"></span>
            <span class="task-name">{{ item.abstract || t('conversation.unnamedConversation') }}</span>
          </button>
        </div>

        <div class="section-label">{{ t('conversation.taskLabel') }}</div>
        <div class="task-list">
          <div
            v-for="item in historyTasks"
            :key="item.conversation_id"
            class="task-row"
            :class="{ 'task-row--active': item.conversation_id === chat_request.conversation_id }"
            @click="openTask(item)"
          >
            <input
              v-if="editingId === item.conversation_id"
              v-model="editingText"
              class="rename-input"
              @click.stop
              @keydown.enter.prevent="saveEdit(item)"
              @blur="saveEdit(item)"
            />
            <span v-else class="task-name">{{ item.abstract || t('conversation.unnamedConversation') }}</span>
            <button type="button" class="mini-btn" @click.stop="toggleMenu(item.conversation_id)">···</button>
            <div v-if="menuId === item.conversation_id" class="mini-menu" @click.stop>
              <button type="button" @click="startEdit(item)">{{ t('conversation.edit') }}</button>
              <button type="button" class="danger" @click="askDelete(item.conversation_id)">{{ t('conversation.delete') }}</button>
            </div>
          </div>
          <p v-if="!historyTasks.length" class="empty-tasks">{{ t('conversation.newTask') }}</p>
        </div>
      </template>

      <div class="drawer-user">{{ currentUsername || t('conversation.defaultUser') }}</div>
    </aside>

    <div v-if="confirmDeleteId" class="confirm-mask" @click.self="confirmDeleteId = ''">
      <div class="confirm-card">
        <p>{{ t('conversation.confirmDeleteTitle') }}</p>
        <p class="confirm-sub">{{ t('conversation.confirmDeleteSub') }}</p>
        <div class="confirm-actions">
          <button type="button" @click="confirmDeleteId = ''">{{ t('conversation.cancel') }}</button>
          <button type="button" class="danger-fill" @click="confirmDelete">{{ t('conversation.confirm') }}</button>
        </div>
      </div>
    </div>

    <MobileFiles
      :open="filesOpen"
      :conversation-id="activeConversationId"
      :open-path="previewPath"
      :refresh-token="fileRefreshToken"
      @close="closeFiles"
    />
  </div>
</template>

<script setup>
import { computed, nextTick, provide, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import ChatWindow from '@/components/ChatWindow.vue'
import MobileFiles from './MobileFiles.vue'
import { useChatSession } from './useChatSession'

const emit = defineEmits(['logout'])
const { t } = useI18n()
// 告诉输入框用手机布局（网页端不会 provide，保持原样）
provide('mobileLayout', true)
const session = useChatSession()

const {
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
} = session

watch(unauthorized, (value) => {
  if (value) emit('logout')
})

const drawerOpen = ref(false)
const filesOpen = ref(false)
const previewPath = ref('')
const fileRefreshToken = ref(0)
const menuId = ref('')
const editingId = ref('')
const editingText = ref('')
const confirmDeleteId = ref('')

const runningIds = computed(() => new Set(runningConversations.value.map((item) => item.conversation_id)))
const visibleRunning = computed(() =>
  runningConversations.value.filter((item) => item.mode !== 'soulprout' && item.conversation_id !== currentUserId.value),
)
const historyTasks = computed(() =>
  taskConversationList.value.filter((item) => !runningIds.value.has(item.conversation_id)),
)

const headerTitle = computed(() => {
  if (chatMode.value === 'soulprout') return t('conversation.soulLabel')
  const current = taskConversationList.value.find((item) => item.conversation_id === chat_request.value.conversation_id)
  return current?.abstract || t('conversation.newTask')
})

const activeConversationId = computed(() => {
  if (chatMode.value === 'soulprout') return currentUserId.value || ''
  return chat_request.value.conversation_id || ''
})

watch(
  () => fileMessages.value.length,
  () => {
    fileRefreshToken.value += 1
  },
)

function switchMode(mode) {
  handleSwitchMode(mode)
}

function startNewTask() {
  createConversation()
  drawerOpen.value = false
}

async function openTask(item) {
  if (editingId.value) return
  menuId.value = ''
  await pickConversation(item.conversation_id)
  drawerOpen.value = false
}

async function openRunning(item) {
  await openRunningConversation(item)
  drawerOpen.value = false
}

function toggleMenu(id) {
  menuId.value = menuId.value === id ? '' : id
}

function startEdit(item) {
  menuId.value = ''
  editingId.value = item.conversation_id
  editingText.value = item.abstract || ''
  nextTick(() => {
    document.querySelector('.rename-input')?.focus()
  })
}

async function saveEdit(item) {
  if (editingId.value !== item.conversation_id) return
  const next = editingText.value.trim()
  editingId.value = ''
  if (!next || next === item.abstract) return
  await updateConversationAbstract(item.conversation_id, next)
}

function askDelete(id) {
  menuId.value = ''
  confirmDeleteId.value = id
}

async function confirmDelete() {
  const id = confirmDeleteId.value
  confirmDeleteId.value = ''
  if (id) await deleteConversation(id)
}

function openFileList() {
  previewPath.value = ''
  filesOpen.value = true
}

function openFilePreview(filePath) {
  previewPath.value = filePath || ''
  filesOpen.value = true
}

function closeFiles() {
  filesOpen.value = false
  previewPath.value = ''
}

function openWebPreview(url) {
  if (url) window.open(url, '_blank', 'noopener')
}
</script>

<style scoped>
.phone {
  height: 100%;
  height: 100dvh;
  display: flex;
  flex-direction: column;
  background: #f2f2f2;
  position: relative;
  overflow: hidden;
}

.topbar {
  flex-shrink: 0;
  display: grid;
  grid-template-columns: 44px 1fr auto;
  align-items: center;
  gap: 4px;
  min-height: 52px;
  padding: env(safe-area-inset-top) 8px 0 4px;
  background: rgba(255, 255, 255, 0.94);
  border-bottom: 1px solid rgba(0, 0, 0, 0.06);
  z-index: 5;
}

.topbar-title {
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.topbar-title strong {
  font-size: 16px;
  font-weight: 650;
  color: #111;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.topbar-title span {
  font-size: 11px;
  color: #9a9a9a;
}

.icon-btn,
.file-btn {
  border: none;
  background: transparent;
  color: #111;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.icon-btn {
  width: 44px;
  height: 44px;
}

.file-btn {
  height: 36px;
  padding: 0 10px;
  gap: 4px;
  border-radius: 999px;
  background: #111;
  color: #fff;
  font-size: 13px;
}

.mobile-chat {
  flex: 1;
  min-height: 0;
  background: #fff;
  /* 自成一层：聊天区里输入框、下拉的高 z-index 不会盖过侧边栏 */
  position: relative;
  z-index: 0;
  isolation: isolate;
}

.mobile-chat :deep(.conversation-container) {
  height: 100% !important;
  max-height: 100% !important;
  min-height: 0 !important;
  overflow: hidden !important;
}

.mobile-chat :deep(.conversation-answer) {
  height: 100% !important;
  min-height: 0 !important;
  overflow: hidden !important;
  border-radius: 0 !important;
  box-shadow: none !important;
}

.mobile-chat :deep(.answer-container) {
  padding-bottom: 16px !important;
  min-height: 0 !important;
  overflow-y: auto !important;
  -webkit-overflow-scrolling: touch;
  touch-action: pan-y;
  overscroll-behavior: contain;
}

.mobile-chat :deep(.answer-single-me-agent),
.mobile-chat :deep(.answer-single-me-usual) {
  width: 100% !important;
  padding-inline: 12px !important;
  box-sizing: border-box;
}

.mobile-chat :deep(.answer-single-robot) {
  width: 100% !important;
  padding-left: 12px !important;
  padding-right: 12px !important;
  box-sizing: border-box;
}

.mobile-chat :deep(.answer-robot-container) {
  width: 100% !important;
}

.booting {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #6b7280;
}

.backdrop {
  position: fixed;
  inset: 0;
  background: rgba(17, 17, 17, 0.38);
  z-index: 20;
}

.drawer {
  position: fixed;
  top: 0;
  left: 0;
  bottom: 0;
  width: min(84vw, 320px);
  background: #f7f7f7;
  z-index: 30;
  transform: translateX(-105%);
  transition: transform 0.28s ease;
  display: flex;
  flex-direction: column;
  padding: env(safe-area-inset-top) 0 env(safe-area-inset-bottom);
  box-shadow: 8px 0 30px rgba(0, 0, 0, 0.08);
}

.drawer--open {
  transform: translateX(0);
}

.drawer-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 8px 0 16px;
}

.drawer-logo {
  height: 28px;
  width: auto;
}

.mode-section {
  margin: 12px 16px 8px;
}

.mode-header {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.4px;
  color: #6e6e6e;
  margin-bottom: 8px;
}

.mode-hint {
  font-weight: 500;
  color: #969696;
  letter-spacing: 0;
}

.mode-switch {
  position: relative;
  display: flex;
  padding: 4px;
  background: rgba(0, 0, 0, 0.05);
  border-radius: 12px;
}

.mode-thumb {
  position: absolute;
  top: 4px;
  left: 4px;
  width: calc(50% - 4px);
  height: calc(100% - 8px);
  background: #212121;
  border-radius: 9px;
  transition: transform 0.28s ease;
}

.mode-switch[data-active='task'] .mode-thumb {
  transform: translateX(100%);
}

.mode-option {
  position: relative;
  z-index: 1;
  flex: 1;
  height: 36px;
  border: none;
  background: transparent;
  color: #4b5563;
  font-size: 14px;
  font-weight: 600;
}

.mode-option--active {
  color: #fff;
}

.new-task {
  margin: 8px 16px;
  height: 44px;
  border: none;
  border-radius: 12px;
  background: #111;
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  font-size: 15px;
}

.section-label {
  margin: 8px 20px 4px;
  font-size: 12px;
  font-weight: 600;
  color: #787878;
}

.running-block,
.task-list {
  display: flex;
  flex-direction: column;
}

.task-list {
  flex: 1;
  min-height: 0;
  overflow: auto;
}

.task-row {
  position: relative;
  width: calc(100% - 24px);
  margin: 2px 12px;
  min-height: 44px;
  border: none;
  border-radius: 10px;
  background: transparent;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  text-align: left;
  color: #111827;
}

.task-row--active {
  background: #fff;
}

.task-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 14px;
}

.dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #16a34a;
  flex-shrink: 0;
}

.rename-input {
  flex: 1;
  min-width: 0;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 6px 8px;
  font-size: 14px;
}

.mini-btn {
  border: none;
  background: transparent;
  color: #6b7280;
  font-size: 16px;
  letter-spacing: 1px;
  padding: 4px;
}

.mini-menu {
  position: absolute;
  right: 8px;
  top: 36px;
  z-index: 2;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  box-shadow: 0 10px 24px rgba(0, 0, 0, 0.08);
  display: flex;
  flex-direction: column;
  min-width: 96px;
  overflow: hidden;
}

.mini-menu button {
  border: none;
  background: #fff;
  text-align: left;
  padding: 10px 12px;
  font-size: 14px;
}

.danger {
  color: #b91c1c;
}

.empty-tasks {
  margin: 12px 20px;
  color: #9ca3af;
  font-size: 13px;
}

.drawer-user {
  margin-top: auto;
  padding: 14px 20px;
  border-top: 1px solid rgba(0, 0, 0, 0.06);
  color: #6b7280;
  font-size: 13px;
}

.confirm-mask {
  position: fixed;
  inset: 0;
  z-index: 50;
  background: rgba(17, 17, 17, 0.4);
  display: flex;
  align-items: flex-end;
  justify-content: center;
}

.confirm-card {
  width: min(100%, 480px);
  margin: 0 12px calc(12px + env(safe-area-inset-bottom));
  background: #fff;
  border-radius: 16px;
  padding: 18px 16px 14px;
}

.confirm-card p {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
}

.confirm-sub {
  margin-top: 6px !important;
  font-size: 13px !important;
  font-weight: 400 !important;
  color: #6b7280;
}

.confirm-actions {
  display: flex;
  gap: 8px;
  margin-top: 16px;
}

.confirm-actions button {
  flex: 1;
  height: 42px;
  border-radius: 12px;
  border: 1px solid #e5e7eb;
  background: #fff;
}

.danger-fill {
  background: #111 !important;
  color: #fff;
  border-color: #111 !important;
}
</style>

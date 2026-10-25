<template>
  <div class="phone">
    <header class="topbar">
      <button
        type="button"
        class="icon-btn"
        :aria-label="chatMode === 'soulprout' ? t('mobile.swapToTask') : t('mobile.swapToSoul')"
        @click="swapMode"
      >
        <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
          <path d="M7 4L3.5 7.5 7 11" />
          <path d="M3.5 7.5H17" />
          <path d="M17 13l3.5 3.5L17 20" />
          <path d="M20.5 16.5H7" />
        </svg>
      </button>
      <div class="topbar-title">
        <strong>{{ headerTitle }}</strong>
        <span>{{ chatMode === 'soulprout' ? t('mobile.soulSubtitle') : t('mobile.taskSubtitle') }}</span>
      </div>
      <button v-if="chatMode === 'soulprout'" type="button" class="entry-btn entry-btn--yavis" @click="yavisOpen = true">
        <span class="entry-glow"></span>
        {{ t('mobile.yavis') }}
      </button>
      <button v-else type="button" class="entry-btn" @click="drawerOpen = true">
        <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="12" r="8.5" />
          <path d="M12 7.5V12l3 2" />
        </svg>
        {{ t('mobile.history') }}
      </button>
      <span class="topbar-spacer"></span>
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

    <YavisPage v-if="yavisOpen" @close="yavisOpen = false" />

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
import YavisPage from './standby/YavisPage.vue'
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
const yavisOpen = ref(false)
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

/** 灵芽 <-> 任务 互换 */
function swapMode() {
  drawerOpen.value = false
  handleSwitchMode(chatMode.value === 'soulprout' ? 'task' : 'soulprout')
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
  display: flex;
  align-items: center;
  gap: 6px;
  min-height: 52px;
  padding: env(safe-area-inset-top) 8px 0 4px;
  background: rgba(255, 255, 255, 0.94);
  border-bottom: 1px solid rgba(0, 0, 0, 0.06);
  z-index: 5;
}

.topbar-spacer {
  flex: 1;
}

.icon-btn {
  flex-shrink: 0;
}

.entry-btn {
  position: relative;
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 30px;
  padding: 0 12px;
  border: 1px solid rgba(0, 0, 0, 0.08);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.9);
  color: #3a3a3c;
  font-size: 12.5px;
  font-weight: 560;
  letter-spacing: 0.3px;
  overflow: hidden;
}

.entry-btn:active {
  transform: scale(0.97);
}

/* 芽维斯入口：极淡的彩色光晕，呼应待命页的「灵魂光感」 */
.entry-btn--yavis {
  padding-left: 14px;
  border-color: rgba(30, 180, 140, 0.32);
  color: #0f8f73;
}

.entry-glow {
  position: absolute;
  inset: -40% -10%;
  background:
    radial-gradient(60% 80% at 20% 50%, rgba(30, 180, 140, 0.26), transparent 70%),
    radial-gradient(60% 80% at 85% 50%, rgba(111, 224, 189, 0.3), transparent 70%);
  filter: blur(6px);
  animation: entry-breathe 5s ease-in-out infinite;
  pointer-events: none;
}

@keyframes entry-breathe {
  0%,
  100% {
    opacity: 0.55;
  }
  50% {
    opacity: 1;
  }
}

.topbar-title {
  min-width: 0;
  flex: 0 1 auto;
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
  /* 手机上不允许左右滑动：宽度恒定，超宽内容在各自内部处理（见下） */
  overflow-x: hidden !important;
  -webkit-overflow-scrolling: touch;
  touch-action: pan-y;
  overscroll-behavior: contain;
  /* 不占宽度的滚动条，避免可用宽度被吃掉一截 */
  scrollbar-width: none;
  -ms-overflow-style: none;
}

.mobile-chat :deep(.answer-container::-webkit-scrollbar) {
  display: none;
  width: 0;
  height: 0;
}

/* 网页端用来占位的空白栏，手机上没有用，且会在屏幕右侧外多出一块 */
.mobile-chat :deep(.conversation-view) {
  display: none !important;
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
  min-width: 0;
}

/* 气泡原本是 width: fit-content，遇到长链接 / 表格 / 代码块会按最长内容撑宽，
   把整个聊天区顶出横向滚动条。这里限制为不超过屏幕，并让长文本能换行。 */
.mobile-chat :deep(.answer-robot-content),
.mobile-chat :deep(.answer-robot-content-us),
.mobile-chat :deep(.answer-me-content) {
  box-sizing: border-box;
  min-width: 0;
  max-width: calc(100% - 32px);
  overflow-wrap: anywhere;
  word-break: break-word;
}

.mobile-chat :deep(.p-content-markdown) {
  min-width: 0;
  max-width: 100%;
  overflow-wrap: anywhere;
}

/* 表格、代码块：只在自己内部横向滚动，不撑宽页面 */
.mobile-chat :deep(.p-content-markdown table) {
  display: block;
  max-width: 100%;
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
}

.mobile-chat :deep(.code-wrapper),
.mobile-chat :deep(.p-content-markdown pre) {
  max-width: 100%;
  min-width: 0;
  box-sizing: border-box;
}

.mobile-chat :deep(.code-wrapper pre) {
  overflow-x: auto;
}

.mobile-chat :deep(.p-content-markdown img) {
  max-width: 100%;
  height: auto;
}

/* 灵芽欢迎页：「多渠道接入：微信 飞书 ……」一整行不换行，手机上会被裁掉，改成换行居中 */
.mobile-chat :deep(.no-history-container--soul) {
  box-sizing: border-box;
  width: 100%;
  max-width: 100%;
  padding: 0 16px;
}

.mobile-chat :deep(.soul-channel-line) {
  flex-wrap: wrap;
  justify-content: center;
  row-gap: 8px;
}

.mobile-chat :deep(.soul-channel-list) {
  flex-wrap: wrap;
  justify-content: center;
  row-gap: 8px;
  max-width: 100%;
}

/* 欢迎页（任务模式）标题 + 「移动到这里查看」提示原本是一整行，手机上标题贴边、提示被裁掉 */
.mobile-chat :deep(.no-history-container) {
  box-sizing: border-box;
  max-width: 100%;
  padding-inline: 16px;
  text-align: center;
}

.mobile-chat :deep(.no-history-title-row) {
  flex-wrap: wrap;
  align-items: center;
  justify-content: center;
  row-gap: 8px;
  max-width: 100%;
}

.mobile-chat :deep(.no-history-container .no-history-content1) {
  font-size: 26px;
}

/* 欢迎页（任务模式）两张卡片原本不换行、各自至少 300px，手机放不下 */
.mobile-chat :deep(.suggestion-cards-two) {
  flex-wrap: wrap;
  gap: 14px;
}

.mobile-chat :deep(.suggestion-cards-two .suggestion-card) {
  flex: 1 1 100%;
  min-width: 0;
  width: 100%;
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

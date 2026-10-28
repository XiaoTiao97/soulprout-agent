<template>
  <div class="phone" :class="{ 'phone--yavis': yavisOpen }">
    <div ref="surfaceEl" class="phone-surface">
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
      <button v-if="chatMode === 'soulprout'" type="button" class="entry-btn entry-btn--yavis" @click="openYavis">
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
    </div>

    <div ref="washEl" class="water-wash"></div>

    <div v-if="yavisOpen" ref="slotEl" class="yavis-slot">
      <YavisPage
        v-if="yavisMounted"
        :gate-visible="showGate"
        :present="yavisPresent"
        :commit="yavisCommit"
        @reveal="onYavisReveal"
        @close="closeYavis"
      />
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
import { computed, nextTick, onBeforeUnmount, onMounted, provide, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { App } from '@capacitor/app'
import { Capacitor } from '@capacitor/core'
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
  refreshHistory,
} = session

watch(unauthorized, (value) => {
  if (value) emit('logout')
})

const drawerOpen = ref(false)
const yavisOpen = ref(false)
const showGate = ref(false)
/** 芽维斯页面本体延后挂载：它的初始化和权限检测不能和点击、动画首帧挤在一起 */
const yavisMounted = ref(false)
/** 先把待命页画出来，但先别启动引擎 */
const yavisPresent = ref(false)
/** 溶解结束后才真正开麦克风 */
const yavisCommit = ref(false)
const surfaceEl = ref(null)
const washEl = ref(null)
const slotEl = ref(null)
/** '' | standby | gate | close */
let revealKind = ''
let runId = 0
let held = false
let emerging = false
const EASE = 'cubic-bezier(0.4, 0, 0.2, 1)'

// ---- 临时性能日志（定位进场卡顿用，查完删除）----
let perfPhase = 'idle'
let perfRaf = 0
let perfLast = 0
function perf(msg) {
  console.log('[yavis-perf] ' + Math.round(performance.now()) + ' ' + msg)
}
function setPhase(p) {
  perfPhase = p
  perf('phase ' + p)
}
function perfStart() {
  cancelAnimationFrame(perfRaf)
  perfLast = 0
  const tick = (t) => {
    if (perfLast && t - perfLast > 24) perf(`frame gap ${Math.round(t - perfLast)}ms in ${perfPhase}`)
    perfLast = t
    perfRaf = requestAnimationFrame(tick)
  }
  perfRaf = requestAnimationFrame(tick)
}
function perfStop() {
  cancelAnimationFrame(perfRaf)
}
try {
  new PerformanceObserver((list) => {
    for (const e of list.getEntries()) {
      const scripts = (e.scripts || [])
        .map((s) => `${s.invoker || s.sourceFunctionName || '?'}:${Math.round(s.duration)}`)
        .join(',')
      perf(
        `LoAF ${Math.round(e.duration)}ms block=${Math.round(e.blockingDuration || 0)} ` +
          `renderStart=${Math.round(e.renderStart ? e.startTime + e.duration - e.renderStart : 0)} ` +
          `scripts=[${scripts}] phase=${perfPhase}`,
      )
    }
  }).observe({ type: 'long-animation-frame' })
} catch {
  /* 不支持就算了 */
}
try {
  new PerformanceObserver((list) => {
    for (const e of list.getEntries()) perf(`longtask ${Math.round(e.duration)}ms phase=${perfPhase}`)
  }).observe({ type: 'longtask' })
} catch {
  /* ignore */
}

function opacityOf(el, fallback) {
  if (!el) return fallback
  const n = parseFloat(getComputedStyle(el).opacity)
  return Number.isFinite(n) ? n : fallback
}

function fade(el, to, ms, delay = 0, easing = EASE) {
  if (!el) return Promise.resolve()
  const from = opacityOf(el, to)
  for (const anim of el.getAnimations()) anim.cancel()
  // 完全透明的层浏览器不会预先栅格化，首帧才画会掉帧；起点用接近 0 的值
  el.style.visibility = ''
  el.style.opacity = String(from)
  if (Math.abs(from - to) < 0.01 || ms <= 0) {
    el.style.opacity = String(to)
    if (to === 0) el.style.visibility = 'hidden'
    return Promise.resolve()
  }
  const anim = el.animate([{ opacity: from }, { opacity: to }], {
    duration: ms,
    delay,
    easing,
    fill: 'both',
  })
  return anim.finished.then(() => {
    el.style.opacity = String(to)
    // 已经完全看不见的层不再参与合成，省掉后面光球动画时的开销
    if (to === 0) el.style.visibility = 'hidden'
    anim.cancel()
  })
}

function clearDissolveStyle() {
  for (const el of [surfaceEl.value, washEl.value, slotEl.value]) {
    if (!el) continue
    for (const anim of el.getAnimations()) anim.cancel()
    el.style.opacity = ''
    el.style.visibility = ''
  }
}

function afterFrames(n = 2) {
  return new Promise((resolve) => {
    const step = () => (n-- <= 0 ? resolve() : requestAnimationFrame(step))
    requestAnimationFrame(step)
  })
}

function openYavis() {
  if (yavisOpen.value) return
  drawerOpen.value = false
  revealKind = ''
  held = false
  emerging = false
  showGate.value = false
  yavisMounted.value = false
  yavisPresent.value = false
  yavisCommit.value = false
  prepPromise = null
  perfStart()
  setPhase('tap')
  revealedPromise = new Promise((resolve) => {
    revealResolve = resolve
  })
  yavisOpen.value = true
  yavisMounted.value = true
  const id = ++runId
  // 点击后立刻开始淡出，不等权限检测。检测和光球的准备并行做，
  // 结果出来再决定：进待命页就接着走，权限没齐就改道停在一半。
  nextTick(async () => {
    // 让整页先提升成独立图层，只等两帧
    await afterFrames(2)
    if (id === runId) play(id)
  })
}

let revealResolve = null
let revealedPromise = null

const OUT = 'cubic-bezier(0.2, 0.8, 0.3, 1)'
const SLOT_IN = 'cubic-bezier(0.25, 0.1, 0.25, 1)'

// 只播透明度，交给合成线程。一条连续的时间轴，起步就有明显变化，中间没有停顿点。
async function play(id) {
  setPhase('play')
  const t0 = performance.now()
  const bg = Promise.all([
    fade(surfaceEl.value, 0, 850, 0, OUT),
    fade(washEl.value, 1, 850, 0, OUT),
  ])
  // 被改道时这两条动画会被取消，属于预期
  bg.catch(() => {})

  await Promise.race([revealedPromise, new Promise((resolve) => setTimeout(resolve, 900))])
  if (id !== runId) return
  perf('play: decision=' + (revealKind || 'none'))

  if (revealKind === 'gate') {
    // 权限没齐：从当前位置改道，停在一半。这时动画才起步很短，看不出来。
    try {
      await Promise.all([fade(surfaceEl.value, 0.4, 420), fade(washEl.value, 0.9, 420)])
    } catch {
      return
    }
    if (id !== runId) return
    revealGate()
    return
  }

  if (revealKind === 'standby') {
    if (emerging) return
    emerging = true
    held = false
    try {
      await prepareStandby()
      if (id !== runId) {
        emerging = false
        return
      }
      const elapsed = performance.now() - t0
      await Promise.all([bg, fade(slotEl.value, 1, 560, Math.max(0, 230 - elapsed), SLOT_IN)])
    } catch {
      emerging = false
      return
    }
    emerging = false
    if (id !== runId) return
    await finishEmerge(id)
    return
  }

  // 900ms 内还没有结果（网络慢）：等背景走完，再按结果接着走
  try {
    await bg
  } catch {
    return
  }
  if (id !== runId) return
  if (revealKind === 'standby') emerge(id)
  else if (revealKind === 'gate') revealGate()
  else held = true
}

/**
 * 待命页提前挂好并栅格化。放在第一段淡出期间做，
 * 这样第二段开始时不需要再等任何准备，两段之间没有空档。
 */
let prepPromise = null
function prepareStandby() {
  if (prepPromise) return prepPromise
  perf('prepare standby (mount stage + orb)')
  yavisPresent.value = true
  prepPromise = (async () => {
    await nextTick()
    perf('prepare: nextTick done')
    // 起点给一个肉眼看不见的透明度，让光球提前栅格化
    if (slotEl.value && !slotEl.value.getAnimations().length && opacityOf(slotEl.value, 0) < 0.05) {
      slotEl.value.style.visibility = ''
      slotEl.value.style.opacity = '0.01'
    }
    await afterFrames(3)
  })()
  return prepPromise
}

async function emerge(id) {
  if (emerging || id !== runId) return
  emerging = true
  held = false
  try {
    setPhase('emerge-wait-prep')
    await prepareStandby()
    perf('prep ready')
    if (id !== runId) {
      emerging = false
      return
    }
    setPhase('emerge-fade')
    // 三层同时起步：聊天页继续淡出，水色铺满，芽维斯稍晚一点浮上来，交叠着过渡
    await Promise.all([
      fade(surfaceEl.value, 0, 760),
      fade(washEl.value, 1, 760),
      fade(slotEl.value, 1, 620, 220),
    ])
  } catch {
    emerging = false
    return
  }
  emerging = false
  if (id !== runId) return
  await finishEmerge(id)
}

async function finishEmerge(id) {
  // 淡入结束后再留一小会儿，让光球动画先稳住，再去开麦克风和加载唤醒模型
  setPhase('settle-wait')
  await new Promise((resolve) => setTimeout(resolve, 240))
  if (id !== runId) return
  setPhase('engine-start')
  yavisCommit.value = true
  setTimeout(() => {
    setPhase('idle')
    perfStop()
  }, 2500)
}

function revealGate() {
  held = false
  showGate.value = true
  fade(slotEl.value, 1, 320)
}

function onYavisReveal(kind) {
  if (!yavisOpen.value || revealKind === 'close') return
  const prev = revealKind
  revealKind = kind
  perf(`reveal ${kind} (prev=${prev || 'none'}, held=${held})`)
  revealResolve?.()
  revealResolve = null
  if (kind === 'standby') {
    showGate.value = false
    // 一知道要进待命页就开始准备，趁第一段淡出还在播的时候把重活做完
    prepareStandby()
    if (emerging) return
    if (held || prev === 'gate') emerge(++runId)
    return
  }
  if (emerging) return
  if (prev === 'standby') {
    retreat(++runId)
    return
  }
  if (held) revealGate()
}

async function retreat(id) {
  yavisCommit.value = false
  showGate.value = false
  try {
    await Promise.all([fade(surfaceEl.value, 0.4, 560), fade(washEl.value, 0.9, 560), fade(slotEl.value, 0, 320)])
  } catch {
    return
  }
  if (id !== runId) return
  showGate.value = true
  fade(slotEl.value, 1, 280)
}

async function closeYavis() {
  if (!yavisOpen.value || revealKind === 'close') return
  const id = ++runId
  revealKind = 'close'
  emerging = false
  held = false
  yavisCommit.value = false
  showGate.value = false
  try {
    await fade(slotEl.value, 0, 280)
    if (id !== runId) return
    await Promise.all([fade(surfaceEl.value, 1, 520), fade(washEl.value, 0, 520)])
  } catch {
    return
  }
  if (id !== runId) return
  clearDissolveStyle()
  revealKind = ''
  yavisPresent.value = false
  yavisMounted.value = false
  prepPromise = null
  yavisOpen.value = false
  // 芽维斯对话走原生管线，退出后刷新侧边栏与当前会话，避免仍是进待命前的旧记录
  refreshHistory().catch(() => {})
}

/** 安卓返回键 / 边缘滑动：优先关文件页、芽维斯、侧栏，而不是直接杀进程 */
let backButtonHandle = null
async function onAndroidBackButton() {
  if (filesOpen.value) {
    closeFiles()
    return
  }
  if (yavisOpen.value) {
    await closeYavis()
    return
  }
  if (drawerOpen.value) {
    drawerOpen.value = false
    return
  }
  if (confirmDeleteId.value) {
    confirmDeleteId.value = ''
    return
  }
  try {
    await App.exitApp()
  } catch {
    /* web 预览无此能力 */
  }
}

onMounted(async () => {
  if (!Capacitor.isNativePlatform()) return
  try {
    backButtonHandle = await App.addListener('backButton', () => {
      onAndroidBackButton()
    })
  } catch (e) {
    console.warn('[mobile] backButton listener failed', e)
  }
})

onBeforeUnmount(() => {
  backButtonHandle?.remove?.()
  backButtonHandle = null
  runId += 1
  clearDissolveStyle()
})
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

.phone--yavis .phone-surface,
.phone--yavis .water-wash,
.phone--yavis .yavis-slot {
  will-change: opacity;
}

.phone-surface {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.water-wash {
  position: absolute;
  inset: 0;
  z-index: 60;
  pointer-events: none;
  opacity: 0;
  background:
    radial-gradient(80% 55% at 50% 115%, rgba(72, 176, 150, 0.55), transparent 62%),
    radial-gradient(46% 38% at 18% 24%, rgba(255, 255, 255, 0.42), transparent 70%),
    radial-gradient(40% 34% at 84% 16%, rgba(168, 224, 206, 0.48), transparent 72%),
    linear-gradient(180deg, rgba(236, 248, 244, 0.2), rgba(176, 214, 200, 0.34));
}

.yavis-slot {
  position: absolute;
  inset: 0;
  z-index: 80;
  opacity: 0;
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

<template>
  <div v-if="visible" class="bp-block">
    <div class="bp-summaries-row">
      <button
        type="button"
        class="bp-summary-pill"
        :class="{
          'bp-summary-pill--active': expanded,
          'bp-summary-pill--pending': pending,
        }"
        :aria-expanded="expanded"
        :aria-label="pillLabel"
        @click="expanded = !expanded"
      >
        <span class="bp-pill-icon" aria-hidden="true">
          <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
            <path d="M14 2v6h6" />
            <path d="M8 13h8" />
            <path d="M8 17h5" />
          </svg>
        </span>
        <span class="bp-pill-text">{{ pillLabel }}</span>
        <span class="bp-pill-chevron">{{ expanded ? '▴' : '▾' }}</span>
      </button>
    </div>

    <div v-if="expanded" class="bp-detail-panel">
      <section class="bp-detail-section">
        <div
          v-if="pending && (slotTexts[0] || slotTexts[1] || props.progressText)"
          class="bp-progress-wrap"
        >
          <!-- 双槽位常驻 DOM，交替播放渐显/渐隐，避免同一层改文字导致「硬切」 -->
          <div
            v-for="idx in 2"
            :key="idx - 1"
            class="bp-progress-layer"
            :class="slotAnimClass[idx - 1]"
          >{{ slotTexts[idx - 1] }}</div>
        </div>

        <div v-if="content" class="bp-detail-block">
          <div class="bp-detail-block-title">{{ t('blocks.blueprintContent') }}</div>
          <div class="bp-result-wrap">
            <div class="bp-result-content">{{ content }}</div>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<script lang="ts" setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

const props = withDefaults(
  defineProps<{
    content?: string
    progressText?: string
    pending?: boolean
  }>(),
  {
    content: '',
    progressText: '',
    pending: true,
  },
)

const expanded = ref(true)
/** 双槽文本与动画类名 */
const slotTexts = ref<[string, string]>(['', ''])
const slotAnimClass = ref<[string, string]>(['', ''])
/** 当前正在展示的槽位 0 | 1，-1 表示尚无内容 */
let activeSlot = -1
/** 待播队列：只保留最新一段（时间优先），但不打断当前动画 */
let queuedSegment: string | null = null
let ingestBuffer = ''
let playing = false
let playToken = 0

const PROGRESS_SEGMENT_CHARS = 180
const FADE_MS = 850
const HOLD_MS = 450

const visible = computed(
  () =>
    !!(
      props.content ||
      props.progressText ||
      props.pending ||
      slotTexts.value[0] ||
      slotTexts.value[1]
    ),
)

const pillLabel = computed(() =>
  props.pending ? t('blocks.generatingBlueprint') : t('blocks.completedBlueprint'),
)

function sleep(ms: number) {
  return new Promise<void>((resolve) => {
    window.setTimeout(resolve, ms)
  })
}

/** 双 rAF：确保浏览器先绘制初始态，再触发 CSS 动画 */
function waitPaint() {
  return new Promise<void>((resolve) => {
    requestAnimationFrame(() => {
      requestAnimationFrame(() => resolve())
    })
  })
}

function takeLatestFromBuffer() {
  while (ingestBuffer.length >= PROGRESS_SEGMENT_CHARS) {
    queuedSegment = ingestBuffer.slice(0, PROGRESS_SEGMENT_CHARS)
    ingestBuffer = ingestBuffer.slice(PROGRESS_SEGMENT_CHARS)
  }
}

function pullNextSegment(): string | null {
  takeLatestFromBuffer()
  if (queuedSegment) {
    const s = queuedSegment
    queuedSegment = null
    return s
  }
  if (ingestBuffer.trim()) {
    const s = ingestBuffer
    ingestBuffer = ''
    return s
  }
  return null
}

async function playSegment(segment: string, token: number) {
  const prevActive = activeSlot
  const inactive = prevActive === 0 ? 1 : prevActive === 1 ? 0 : 0

  // 1. 新文字写入非活跃槽，先清空动画类
  slotTexts.value[inactive] = segment
  slotAnimClass.value[inactive] = ''
  if (prevActive >= 0) {
    slotAnimClass.value[prevActive] = ''
  }
  await waitPaint()
  if (token !== playToken) return

  if (prevActive === -1) {
    slotAnimClass.value[inactive] = 'anim-fade-in'
    activeSlot = inactive
    await sleep(FADE_MS + HOLD_MS)
    return
  }

  // 2. 交叉：旧槽渐隐 + 新槽渐显（同时进行）
  slotAnimClass.value[prevActive] = 'anim-fade-out'
  slotAnimClass.value[inactive] = 'anim-fade-in'
  await waitPaint()
  if (token !== playToken) return

  activeSlot = inactive
  await sleep(FADE_MS + HOLD_MS)

  // 3. 旧槽复位
  slotAnimClass.value[prevActive] = ''
}

async function drainQueue() {
  if (playing) return
  playing = true
  const token = ++playToken
  try {
    while (true) {
      const next = pullNextSegment()
      if (!next) break
      await playSegment(next, token)
      if (token !== playToken) break
    }
  } finally {
    playing = false
    // 播放期间可能又攒了新段
    if (queuedSegment || ingestBuffer.length > 0) {
      void drainQueue()
    }
  }
}

function enqueueProgress(raw: string) {
  if (!raw) return
  ingestBuffer += raw
  takeLatestFromBuffer()
  void drainQueue()
}

function resetProgressVisual() {
  playToken++
  playing = false
  ingestBuffer = ''
  queuedSegment = null
  activeSlot = -1
  slotTexts.value = ['', '']
  slotAnimClass.value = ['', '']
}

watch(
  () => props.progressText,
  (v, old) => {
    const prev = old || ''
    const next = v || ''
    if (!next) {
      if (ingestBuffer.trim()) {
        queuedSegment = ingestBuffer
        ingestBuffer = ''
      }
      void drainQueue()
      return
    }
    if (next.startsWith(prev)) {
      enqueueProgress(next.slice(prev.length))
    } else {
      resetProgressVisual()
      enqueueProgress(next)
    }
  },
)

watch(
  () => props.content,
  (v, old) => {
    const wasEmpty = !old || old === ''
    if (wasEmpty && v) {
      expanded.value = true
      resetProgressVisual()
    }
  },
)

watch(
  () => props.pending,
  (pending) => {
    if (!pending) resetProgressVisual()
  },
)

onBeforeUnmount(() => {
  playToken++
})
</script>

<style scoped>
.bp-block {
  display: flex;
  flex-direction: column;
  gap: 0;
  width: 100%;
  max-width: 100%;
  margin: 0 0 8px;
  cursor: default;
}

.bp-summaries-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  column-gap: 8px;
  row-gap: 4px;
}

.bp-summary-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 11px 5px 9px;
  border: 1px solid rgba(0, 0, 0, 0.08);
  border-radius: 999px;
  background: #fafafa;
  color: #525252;
  font-size: 12.5px;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.18s ease, border-color 0.18s ease, box-shadow 0.18s ease;
  font-family: inherit;
  line-height: 1.3;
  max-width: 100%;
}

.bp-summary-pill:hover {
  background: #f4f4f5;
  border-color: rgba(0, 0, 0, 0.12);
}

.bp-summary-pill--active {
  background: #f0f0f0;
  border-color: rgba(0, 0, 0, 0.14);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06);
}

.bp-summary-pill--pending {
  position: relative;
  overflow: hidden;
}

.bp-summary-pill--pending::after {
  content: '';
  position: absolute;
  inset: -1px;
  left: -100%;
  width: calc(100% + 2px);
  background: linear-gradient(
    90deg,
    transparent 0%,
    rgba(255, 255, 255, 0.65) 45%,
    rgba(255, 255, 255, 0.85) 50%,
    rgba(255, 255, 255, 0.65) 55%,
    transparent 100%
  );
  animation: bp-pill-shine 2s ease-in-out infinite;
  pointer-events: none;
  border-radius: inherit;
}

@keyframes bp-pill-shine {
  0%, 55% { left: -100%; }
  100% { left: 100%; }
}

.bp-pill-icon {
  display: inline-flex;
  color: #737373;
  flex-shrink: 0;
}

.bp-pill-text {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 280px;
}

.bp-pill-chevron {
  flex-shrink: 0;
  font-size: 8px;
  color: #a3a3a3;
  margin-left: 1px;
}

.bp-detail-panel {
  margin-top: 8px;
  padding: 0;
  border: 1px solid rgba(0, 0, 0, 0.06);
  border-radius: 12px;
  background: #f8f9fa;
  overflow: hidden;
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.04);
  width: 420px;
  max-width: 100%;
  cursor: default;
}

.bp-detail-section {
  padding: 8px 10px 10px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.bp-progress-wrap {
  position: relative;
  width: 100%;
  height: 96px;
  box-sizing: border-box;
  overflow: hidden;
  background: rgba(255, 255, 255, 0.55);
  border: 1px solid rgba(0, 0, 0, 0.04);
  border-radius: 8px;
}

.bp-progress-layer {
  position: absolute;
  inset: 0;
  margin: 0;
  padding: 8px 10px;
  box-sizing: border-box;
  font-size: 12px;
  line-height: 1.55;
  color: rgba(82, 82, 82, 0.55);
  font-family: inherit;
  font-weight: 400;
  white-space: pre-wrap;
  word-break: break-word;
  overflow-wrap: anywhere;
  overflow: hidden;
  opacity: 0;
  transform: translateY(4px);
  pointer-events: none;
}

/* 用 keyframes 代替 transition，避免 Vue 批量更新导致动画被跳过 */
.bp-progress-layer.anim-fade-in {
  animation: bp-progress-fade-in 0.85s ease forwards;
}

.bp-progress-layer.anim-fade-out {
  animation: bp-progress-fade-out 0.85s ease forwards;
}

@keyframes bp-progress-fade-in {
  from {
    opacity: 0;
    transform: translateY(4px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@keyframes bp-progress-fade-out {
  from {
    opacity: 1;
    transform: translateY(0);
  }
  to {
    opacity: 0;
    transform: translateY(-3px);
  }
}

.bp-detail-block-title {
  font-size: 10px;
  font-weight: 600;
  color: #a3a3a3;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  margin-bottom: 5px;
  padding-left: 1px;
}

.bp-result-wrap {
  position: relative;
  width: 100%;
}

.bp-result-content {
  margin: 0;
  padding: 7px 9px;
  font-size: 12px;
  line-height: 1.5;
  color: #3f3f46;
  font-family: inherit;
  font-weight: 400;
  background: #fff;
  border: 1px solid rgba(0, 0, 0, 0.05);
  border-radius: 8px;
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.03);
  white-space: pre-wrap;
  word-break: break-word;
  overflow-wrap: anywhere;
  max-height: 480px;
  overflow-y: auto;
  box-sizing: border-box;
  scrollbar-width: thin;
  scrollbar-color: rgba(0, 0, 0, 0.12) transparent;
}

.bp-result-content::-webkit-scrollbar {
  width: 4px;
}

.bp-result-content::-webkit-scrollbar-thumb {
  background: rgba(0, 0, 0, 0.12);
  border-radius: 999px;
}

@media (max-width: 520px) {
  .bp-pill-text {
    max-width: 200px;
  }

  .bp-detail-panel {
    width: 100%;
  }
}
</style>

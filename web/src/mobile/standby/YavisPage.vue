<template>
  <div class="yavis" :class="rootClass">
    <!-- ============ 权限引导：溶到一半时浮在画面上，不占满屏 ============ -->
    <div v-if="stage === 'gate' && gateVisible" class="gate">
      <header class="gate-head">
        <div>
          <h1>{{ t('standby.title') }}</h1>
          <span class="gate-sub">{{ t('standby.subtitle') }}</span>
        </div>
        <button type="button" class="round-btn" :aria-label="t('standby.close')" @click="emit('close')">
          <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round">
            <path d="M6.5 6.5l11 11M17.5 6.5l-11 11" />
          </svg>
        </button>
      </header>

      <div class="gate-scroll">
        <p class="gate-intro">{{ t('standby.gate.intro') }}</p>

        <p v-if="!supported" class="gate-warn">{{ t('standby.notNative') }}</p>
        <p v-else-if="voiceChecked && !voiceConfigured" class="gate-warn">{{ t('standby.notConfigured') }}</p>
        <p v-if="startError" class="gate-warn">{{ startError }}</p>

        <div class="group-label">{{ t('standby.gate.required') }}</div>
        <div class="group">
          <div v-for="item in requiredItems" :key="item.key" class="row">
            <span class="mark" :class="{ 'mark--ok': item.ok }">
              <svg v-if="item.ok" viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">
                <path d="M5 12.5l4.5 4.5L19 7.5" />
              </svg>
            </span>
            <div class="row-body">
              <b>{{ t(`standby.gate.${item.key}.title`) }}</b>
              <span>{{ t(`standby.gate.${item.key}.desc`, { brand: brandText }) }}</span>
            </div>
            <button v-if="!item.ok" type="button" class="pill" @click="item.action()">{{ t('standby.gate.todo') }}</button>
            <span v-else class="done-text">{{ t('standby.gate.done') }}</span>
          </div>
        </div>

        <div class="group-label">{{ t('standby.gate.recommended') }}</div>
        <div class="group">
          <div v-for="item in recommendedItems" :key="item.key" class="row">
            <span class="mark" :class="{ 'mark--ok': item.ok }">
              <svg v-if="item.ok" viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">
                <path d="M5 12.5l4.5 4.5L19 7.5" />
              </svg>
            </span>
            <div class="row-body">
              <b>{{ t(`standby.gate.${item.key}.title`) }}</b>
              <span>{{ t(`standby.gate.${item.key}.desc`, { brand: brandText }) }}</span>
              <label v-if="item.manual" class="manual">
                <input v-model="manual[item.key]" type="checkbox" />
                {{ t('standby.gate.manualDone') }}
              </label>
            </div>
            <button v-if="item.action && !item.ok" type="button" class="pill pill--ghost" @click="item.action()">
              {{ t('standby.gate.todo') }}
            </button>
          </div>
        </div>

        <button type="button" class="link-btn" @click="refreshStatus">{{ t('standby.gate.recheck') }}</button>
      </div>

      <footer class="gate-foot">
        <p v-if="pendingCount > 0" class="gate-pending">{{ t('standby.gate.pending', { n: pendingCount }) }}</p>
        <button type="button" class="primary-btn" :disabled="!canStart" @click="startStandby">
          {{ busy ? t('standby.gate.starting') : t('standby.gate.start') }}
        </button>
      </footer>
    </div>

    <!-- ============ 待命页 ============ -->
    <div v-else-if="stage === 'standby'" class="stage">
      <div class="stage-bg"></div>

      <div class="stage-actions">
        <button type="button" class="round-btn" :aria-label="t('standby.settings')" @click="openSheet">
          <svg viewBox="0 0 24 24" width="19" height="19" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
            <path d="M4 8h9M17 8h3M4 16h3M11 16h9" />
            <circle cx="15" cy="8" r="2" />
            <circle cx="9" cy="16" r="2" />
          </svg>
        </button>
        <button type="button" class="round-btn" :aria-label="t('standby.exit')" @click="exitStandby">
          <svg viewBox="0 0 24 24" width="19" height="19" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
            <path d="M12 3.5v8" />
            <path d="M7.2 6.6a7.6 7.6 0 1 0 9.6 0" />
          </svg>
        </button>
      </div>

      <div class="stage-orb">
        <SoulOrb :phase="orbPhase" :level="state.level" :out-level="state.outLevel" :pulse="state.wakePulse" />
      </div>

      <div class="stage-text">
        <Transition name="line" mode="out-in">
          <p :key="line" class="line">{{ line }}</p>
        </Transition>
        <Transition name="line">
          <p v-if="state.error" class="line-err">{{ state.error }}</p>
        </Transition>
      </div>

      <!-- 设置弹层 -->
      <Transition name="fade">
        <div v-if="sheetOpen" class="sheet-mask" @click.self="closeSheet"></div>
      </Transition>
      <Transition name="sheet">
        <section v-if="sheetOpen" class="sheet" role="dialog">
          <div class="sheet-grab"></div>
          <header class="sheet-head">
            <strong>{{ t('standby.settingsSheet.title') }}</strong>
            <button type="button" class="sheet-done" @click="closeSheet">{{ t('standby.settingsSheet.done') }}</button>
          </header>

          <div class="sheet-body">
            <div class="group">
              <div class="field">
                <label>{{ t('standby.settingsSheet.word') }}</label>
                <input v-model.trim="wordDraft" class="text-input" maxlength="32" autocomplete="off" autocapitalize="off" />
                <p v-if="!draftCheck.ok" class="field-err">{{ t('standby.settingsSheet.wordError.' + draftCheck.reason) }}</p>
                <div v-else class="chips">
                  <span v-for="(p, i) in draftPieces" :key="i" class="chip">
                    {{ p.text }}<small>{{ p.note }}</small>
                  </span>
                </div>
                <p class="field-hint">{{ t('standby.settingsSheet.wordHint') }} {{ t('standby.settingsSheet.restartHint') }}</p>
              </div>

              <div class="field">
                <div class="field-line">
                  <label>{{ t('standby.settingsSheet.endWindow') }}</label>
                  <span class="field-value">{{ cfg.endWindowMs }} ms</span>
                </div>
                <input v-model.number="cfg.endWindowMs" type="range" min="300" max="1500" step="100" class="slider" />
                <p class="field-hint">{{ t('standby.settingsSheet.endWindowHint') }}</p>
              </div>

              <div class="field field--switch">
                <div class="switch-text">
                  <label>{{ t('standby.settingsSheet.continuous') }}</label>
                  <p class="field-hint">{{ t('standby.settingsSheet.continuousHint') }}</p>
                </div>
                <button
                  type="button"
                  class="switch"
                  :class="{ 'switch--on': cfg.continuous }"
                  role="switch"
                  :aria-checked="cfg.continuous"
                  @click="cfg.continuous = !cfg.continuous"
                >
                  <i></i>
                </button>
              </div>

              <div class="field">
                <label>{{ t('standby.settingsSheet.voice') }}</label>
                <div class="segment">
                  <button type="button" :class="{ 'segment--on': cfg.voice === 'female' }" @click="cfg.voice = 'female'">
                    {{ t('standby.settingsSheet.voiceFemale') }}
                  </button>
                  <button type="button" :class="{ 'segment--on': cfg.voice === 'male' }" @click="cfg.voice = 'male'">
                    {{ t('standby.settingsSheet.voiceMale') }}
                  </button>
                </div>
              </div>

              <div class="field">
                <div class="field-line">
                  <label>{{ t('standby.settingsSheet.speechRate') }}</label>
                  <span class="field-value">{{ rateText }}</span>
                </div>
                <input v-model.number="cfg.speechRate" type="range" min="-50" max="100" step="10" class="slider" />
                <div class="slider-scale">
                  <span>{{ t('standby.settingsSheet.rateSlow') }}</span>
                  <span>{{ t('standby.settingsSheet.rateNormal') }}</span>
                  <span>{{ t('standby.settingsSheet.rateFast') }}</span>
                </div>
              </div>
            </div>

            <div class="group">
              <div class="field">
                <label>{{ t('standby.settingsSheet.revoke') }}</label>
                <p class="field-hint">{{ t('standby.settingsSheet.revokeHint') }}</p>
              </div>
              <div v-for="item in revokeItems" :key="item.target" class="field field--line">
                <label>{{ t(`standby.gate.${item.key}.title`) }}</label>
                <button type="button" class="text-action" @click="revokePermission(item.target)">
                  {{ t('standby.settingsSheet.revokeGo') }}
                </button>
              </div>
            </div>
          </div>
        </section>
      </Transition>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { http } from '../api'
import { buildKeywordLine, normalizeWakeWord, validateWakeWord, wakeWordPieces } from '../wake/ppinyin'
import SoulOrb from './SoulOrb.vue'
import { createStandbyEngine } from './standbyEngine'
import * as native from './standbyNative'

const emit = defineEmits(['close', 'reveal'])
const { t } = useI18n()

const props = defineProps({
  /** 溶到一半之后才把权限卡片显示出来 */
  gateVisible: { type: Boolean, default: true },
  /** 溶解过半，可以画出待命页，但先不占麦克风 */
  present: { type: Boolean, default: false },
  /** 画面停稳后再启动引擎 */
  commit: { type: Boolean, default: false },
})

const supported = native.isStandbySupported()
const engine = createStandbyEngine()
const state = engine.state

// ---------------------------------------------------------------- 本地设置

const CFG_KEY = 'yavis_cfg'
const MANUAL_KEY = 'yavis_manual'
const GATE_SEEN_KEY = 'yavis_gate_seen'

function loadJson(key, fallback) {
  try {
    return { ...fallback, ...(JSON.parse(localStorage.getItem(key) || '{}') || {}) }
  } catch {
    return { ...fallback }
  }
}

const cfg = reactive(
  loadJson(CFG_KEY, {
    // 空表示「跟随默认」：默认唤醒词是「你好」+ 智能体名字
    word: '',
    endWindowMs: 500,
    continuous: true,
    voice: 'female',
    speechRate: 0,
  }),
)
if (cfg.voice !== 'female' && cfg.voice !== 'male') cfg.voice = 'female'
// 旧版本默认写死的「你好小芽」不是用户主动设置的，迁移成「跟随默认」
if (cfg.word === '你好小芽') cfg.word = ''
// 连续对话：新安装默认开启；已保存的用户选择必须保留，不能再强制改成开启。
cfg.continuous = !!cfg.continuous
const manual = reactive(loadJson(MANUAL_KEY, { autostart: false, lock: false }))
watch(cfg, () => localStorage.setItem(CFG_KEY, JSON.stringify(cfg)), { deep: true })
watch(manual, () => localStorage.setItem(MANUAL_KEY, JSON.stringify(manual)), { deep: true })

// 运行中改参数：除唤醒词外都能立即生效
watch(
  () => [cfg.endWindowMs, cfg.continuous, cfg.voice, cfg.speechRate],
  () => {
    engine.updateOptions({
      endWindowMs: Number(cfg.endWindowMs) || 500,
      continuous: !!cfg.continuous,
      voice: cfg.voice,
      speechRate: Number(cfg.speechRate) || 0,
    })
  },
)

// ---------------------------------------------------------------- 默认唤醒词（你好 + 智能体名字）

const FALLBACK_WORD = '你好小芽'
const defaultWord = ref(FALLBACK_WORD)
// 用户自己在设置里填过唤醒词就用它，否则用默认唤醒词
const effectiveWord = computed(() => cfg.word || defaultWord.value)

/** 「你好」+ 智能体名字；名字不适合做唤醒词时退回兜底 */
function buildDefaultWord(profile) {
  const name = (profile?.agentname || '').trim()
  const word = normalizeWakeWord(`你好${name}`)
  if (name && validateWakeWord(word).ok) return word
  return FALLBACK_WORD
}

async function loadDefaultWord() {
  try {
    const res = await http.get('/api/user/profile')
    if (res.data?.success) defaultWord.value = buildDefaultWord(res.data)
  } catch {
    /* 取不到就沿用上一次的默认值 */
  }
}

// ---------------------------------------------------------------- 服务端语音配置

const voiceChecked = ref(false)
const voiceConfigured = ref(false)

async function checkVoiceConfig() {
  try {
    const res = await http.get('/api/voice/config')
    voiceConfigured.value = !!res.data?.configured
  } catch {
    voiceConfigured.value = false
  } finally {
    voiceChecked.value = true
  }
}

// ---------------------------------------------------------------- 权限引导

const stage = ref('checking')
const status = ref(null)
const busy = ref(false)
const startError = ref('')

async function refreshStatus() {
  if (!supported) return
  try {
    status.value = await native.getStandbyStatus()
  } catch {
    /* ignore */
  }
}

async function grant(kind) {
  try {
    await native.requestStandbyPermissions()
  } catch {
    /* ignore */
  }
  await refreshStatus()
  const s = status.value || {}
  // 被「不再询问」拒绝后系统不会再弹框，只能引导去设置页
  if (kind === 'mic' && !s.microphone) await openSettings('app')
  else if (kind === 'notification' && !s.notifications) await openSettings('notification')
  else if (kind === 'bluetooth' && !s.bluetooth) await openSettings('app')
}

async function openSettings(target) {
  try {
    await native.openStandbySettings(target)
  } catch {
    /* ignore */
  }
}

const brandText = computed(() => {
  const s = status.value
  if (!s) return '-'
  return [s.manufacturer, s.model].filter(Boolean).join(' ')
})

const requiredItems = computed(() => {
  const s = status.value || {}
  return [
    { key: 'mic', ok: !!s.microphone, action: () => grant('mic') },
    { key: 'notification', ok: !!s.notifications, action: () => grant('notification') },
    { key: 'battery', ok: !!s.batteryUnrestricted, action: () => openSettings('battery') },
  ]
})
const recommendedItems = computed(() => {
  const s = status.value || {}
  return [
    { key: 'autostart', ok: !!manual.autostart, manual: true, action: () => openSettings('autostart') },
    { key: 'lock', ok: !!manual.lock, manual: true },
    { key: 'bluetooth', ok: !!s.bluetooth, action: () => grant('bluetooth') },
  ]
})
const pendingCount = computed(() => requiredItems.value.filter((i) => !i.ok).length)
const canStart = computed(
  () => supported && voiceConfigured.value && pendingCount.value === 0 && !busy.value,
)

function onVisible() {
  if (document.visibilityState !== 'visible') return
  clearTimeout(resumeTimer)
  resumeTimer = setTimeout(() => {
    refreshStatus().then(applyResume)
  }, 280)
}

function applyResume() {
  if (pausingForSettings) {
    pausingForSettings = false
    transitioning = false
    if (stage.value !== 'standby' || busy.value) return
    if (pendingCount.value > 0) {
      dropToGate()
      return
    }
    if (state.phase === 'off') startStandby()
    return
  }
  if (transitioning || busy.value || stage.value !== 'standby') return
  if (pendingCount.value === 0 && state.phase === 'off') startStandby()
}

// ---------------------------------------------------------------- 启动 / 退出

/** 启动或重启期间，引擎会短暂回到 off，不能当成「被外部停止」 */
let transitioning = false
/** 去系统页关权限时先停引擎，回来之前不要把页面关掉 */
let pausingForSettings = false
let resumeTimer = 0

const revokeItems = [
  { key: 'mic', target: 'app' },
  { key: 'notification', target: 'notification' },
  { key: 'battery', target: 'batteryList' },
]

async function revokePermission(target) {
  sheetOpen.value = false
  pausingForSettings = true
  transitioning = true
  try {
    await engine.stop()
    await native.openStandbySettings(target)
    await new Promise((resolve) => setTimeout(resolve, 700))
    if (document.visibilityState === 'visible') {
      pausingForSettings = false
      transitioning = false
      if (stage.value === 'standby' && state.phase === 'off' && pendingCount.value === 0) startStandby()
    }
  } catch {
    pausingForSettings = false
    transitioning = false
    if (stage.value === 'standby' && state.phase === 'off' && pendingCount.value === 0) {
      startStandby()
    }
  }
}

async function dropToGate() {
  if (transitioning || stage.value !== 'standby') return
  transitioning = true
  try {
    await engine.stop()
  } catch {
    /* ignore */
  }
  stage.value = 'gate'
  transitioning = false
}

watch(pendingCount, (n) => {
  if (!status.value || n === 0 || stage.value !== 'standby' || transitioning || busy.value) return
  dropToGate()
})

async function resolveUserId() {
  const res = await http.get('/api/user/me')
  if (!res.data?.success) throw new Error('请先登录')
  return String(res.data.user_id)
}

function buildOptions(userId) {
  return {
    keywords: buildKeywordLine(effectiveWord.value, { score: 1.5, threshold: 0.25 }),
    userId,
    // 固定默认：连蓝牙用蓝牙否则手机麦克风；播报中可语音打断；唤醒后等 4 秒
    source: 'auto',
    bargeIn: true,
    noSpeechSec: 4,
    endWindowMs: Number(cfg.endWindowMs) || 500,
    continuous: !!cfg.continuous,
    voice: cfg.voice,
    speechRate: Number(cfg.speechRate) || 0,
    notification: {
      title: t('standby.notification.title'),
      text: t('standby.notification.text'),
      stopLabel: t('standby.notification.stopLabel'),
    },
  }
}

async function startStandby() {
  if (busy.value) return
  if (!props.commit) {
    emit('reveal', 'standby')
    return
  }
  busy.value = true
  transitioning = true
  startError.value = ''
  try {
    const [userId] = await Promise.all([resolveUserId(), loadDefaultWord()])
    localStorage.setItem(GATE_SEEN_KEY, '1')
    stage.value = 'standby'
    console.log('[yavis-perf] ' + Math.round(performance.now()) + ' engine.start begin')
    await engine.start(buildOptions(userId))
    console.log('[yavis-perf] ' + Math.round(performance.now()) + ' engine.start end')
    if (engine.state.phase === 'off') {
      startError.value = engine.state.error || ''
      stage.value = 'gate'
    }
  } catch (e) {
    startError.value = e?.message || String(e)
    stage.value = 'gate'
  } finally {
    busy.value = false
    transitioning = false
    refreshStatus()
  }
}

async function restartStandby() {
  transitioning = true
  try {
    await engine.stop()
  } finally {
    transitioning = false
  }
  await startStandby()
}

async function exitStandby() {
  transitioning = true
  emit('close')
  try {
    await engine.stop()
  } catch {
    /* ignore */
  }
}

// 用户在通知栏点了「停止」等外部原因导致引擎停下：直接收起页面
watch(
  () => state.phase,
  (p) => {
    if (p === 'off' && stage.value === 'standby' && !transitioning) emit('close')
  },
)

watch(stage, (s) => {
  if (s === 'standby' || s === 'gate') emit('reveal', s)
})

const rootClass = computed(() => (stage.value === 'standby' ? 'yavis--live' : 'yavis--gate'))

// ---------------------------------------------------------------- 待命页文案与光感

const orbPhase = computed(() => (state.phase === 'off' ? 'starting' : state.phase))

// 只有这一行提示，状态变化交给光感表达
const line = computed(() => t('standby.wakeLine', { word: effectiveWord.value }))

// ---------------------------------------------------------------- 设置弹层

const sheetOpen = ref(false)
const wordDraft = ref('')
const draftCheck = computed(() => validateWakeWord(wordDraft.value))
const draftPieces = computed(() => (draftCheck.value.ok ? wakeWordPieces(wordDraft.value) : []))

const rateText = computed(() => {
  const v = Number(cfg.speechRate) || 0
  if (v === 0) return t('standby.settingsSheet.rateNormal')
  return v > 0 ? `+${v}` : String(v)
})

function openSheet() {
  wordDraft.value = effectiveWord.value
  sheetOpen.value = true
}

async function closeSheet() {
  sheetOpen.value = false
  const next = normalizeWakeWord(wordDraft.value)
  const prev = effectiveWord.value
  if (!next) {
    // 清空 = 恢复默认（你好 + 智能体名字）
    cfg.word = ''
  } else if (validateWakeWord(next).ok) {
    // 和默认值一样就继续跟随默认，之后改了智能体名字唤醒词会跟着变
    cfg.word = next === defaultWord.value ? '' : next
  }
  // 唤醒词有效且改了才重启；无效就保留原来的
  if (effectiveWord.value !== prev) await restartStandby()
}

// ---------------------------------------------------------------- 生命周期

watch(
  () => props.present,
  (v) => {
    if (v && canStart.value && stage.value !== 'standby') stage.value = 'standby'
  },
)

watch(
  () => props.commit,
  (v) => {
    if (v && stage.value === 'standby' && state.phase === 'off' && !busy.value) startStandby()
  },
)

onMounted(async () => {
  console.log('[yavis-perf] ' + Math.round(performance.now()) + ' page onMounted')
  document.addEventListener('visibilitychange', onVisible)
  await Promise.all([refreshStatus(), checkVoiceConfig(), loadDefaultWord()])
  console.log('[yavis-perf] ' + Math.round(performance.now()) + ' page checks done canStart=' + canStart.value)
  // 先只告诉外面该溶进去还是停在权限卡片。引擎等画面停稳再开。
  if (canStart.value) {
    if (props.present && stage.value !== 'standby') stage.value = 'standby'
    else emit('reveal', 'standby')
    if (props.commit && state.phase === 'off') startStandby()
  } else {
    stage.value = 'gate'
    transitioning = false
  }
})

onBeforeUnmount(() => {
  document.removeEventListener('visibilitychange', onVisible)
  clearTimeout(resumeTimer)
  transitioning = true
  pausingForSettings = false
  engine.stop()
})
</script>

<style scoped>
.yavis {
  position: fixed;
  inset: 0;
  z-index: 100;
  color: #1d1d1f;
  font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Text', 'PingFang SC', 'Helvetica Neue', sans-serif;
  -webkit-font-smoothing: antialiased;
  overflow: hidden;
}

.yavis--gate {
  background: transparent;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: max(22px, env(safe-area-inset-top)) 16px max(22px, env(safe-area-inset-bottom));
  pointer-events: auto;
  overflow: visible;
}

.yavis--live {
  background: #f5f5f7;
}

.yavis--gate .gate {
  pointer-events: auto;
  width: min(100%, 430px);
  max-height: 100%;
  height: auto;
  margin: 0;
  padding-top: 0;
  border-radius: 28px;
  overflow: hidden;
  background: rgba(247, 250, 249, 0.98);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.75),
    0 28px 70px rgba(16, 42, 36, 0.22);
  animation: yavis-card-in 0.48s cubic-bezier(0.22, 1, 0.36, 1);
}

.yavis--gate .gate-head {
  padding: 16px 16px 0 18px;
}

.yavis--gate .gate-head h1 {
  font-size: 22px;
}

.yavis--gate .gate-foot {
  border-radius: 0 0 28px 28px;
  background: linear-gradient(to top, rgba(247, 250, 249, 0.98) 68%, rgba(247, 250, 249, 0));
}

@keyframes yavis-card-in {
  from {
    opacity: 0;
    transform: translateY(16px) scale(0.975);
  }
  to {
    opacity: 1;
    transform: none;
  }
}

/* ---------- 通用 ---------- */
.round-btn {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  border: 1px solid rgba(0, 0, 0, 0.06);
  background: rgba(255, 255, 255, 0.72);
  -webkit-backdrop-filter: blur(14px);
  backdrop-filter: blur(14px);
  color: #3a3a3c;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  transition: transform 0.15s ease, background 0.2s ease;
}

.round-btn:active {
  transform: scale(0.93);
  background: rgba(255, 255, 255, 0.95);
}

.group-label {
  margin: 22px 4px 8px;
  font-size: 12px;
  letter-spacing: 0.08em;
  color: #86868b;
}

.group {
  background: #fff;
  border-radius: 18px;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.03);
  overflow: hidden;
}

/* ---------- 权限引导 ---------- */
.gate {
  height: 100%;
  display: flex;
  flex-direction: column;
  padding-top: env(safe-area-inset-top);
}

.gate-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  padding: 18px 20px 0;
}

.gate-head h1 {
  margin: 0;
  font-size: 30px;
  font-weight: 650;
  letter-spacing: 0.02em;
}

.gate-sub {
  display: block;
  margin-top: 2px;
  font-size: 12px;
  letter-spacing: 0.32em;
  color: #86868b;
}

.gate-scroll {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 0 16px 16px;
}

.gate-intro {
  margin: 18px 4px 0;
  font-size: 14px;
  line-height: 1.65;
  color: #6e6e73;
}

.gate-warn {
  margin: 14px 4px 0;
  padding: 10px 12px;
  border-radius: 12px;
  background: rgba(255, 59, 48, 0.08);
  color: #c62828;
  font-size: 13px;
  line-height: 1.5;
}

.row {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 14px 14px 14px 16px;
}

.row + .row {
  border-top: 1px solid rgba(0, 0, 0, 0.06);
}

.mark {
  flex-shrink: 0;
  width: 22px;
  height: 22px;
  margin-top: 1px;
  border-radius: 50%;
  border: 1.5px solid #c7c7cc;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  transition: all 0.25s ease;
}

.mark--ok {
  border-color: transparent;
  background: linear-gradient(135deg, #1eb48c, #22c99d);
}

.row-body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.row-body b {
  font-size: 15px;
  font-weight: 600;
}

.row-body span {
  font-size: 12.5px;
  line-height: 1.55;
  color: #86868b;
}

.manual {
  margin-top: 6px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12.5px;
  color: #3a3a3c;
}

.manual input {
  accent-color: #1d1d1f;
}

.pill {
  flex-shrink: 0;
  align-self: center;
  height: 30px;
  padding: 0 14px;
  border: none;
  border-radius: 999px;
  background: #1d1d1f;
  color: #fff;
  font-size: 12.5px;
  font-weight: 560;
}

.pill--ghost {
  background: rgba(0, 0, 0, 0.06);
  color: #1d1d1f;
}

.done-text {
  flex-shrink: 0;
  align-self: center;
  font-size: 12.5px;
  color: #1eb48c;
}

.link-btn {
  display: block;
  margin: 18px auto 0;
  border: none;
  background: transparent;
  color: #6e6e73;
  font-size: 13px;
}

.gate-foot {
  padding: 10px 16px calc(14px + env(safe-area-inset-bottom));
  background: linear-gradient(to top, #f5f5f7 70%, rgba(245, 245, 247, 0));
}

.gate-pending {
  margin: 0 0 8px;
  text-align: center;
  font-size: 12.5px;
  color: #86868b;
}

.primary-btn {
  width: 100%;
  height: 50px;
  border: none;
  border-radius: 999px;
  background: #1d1d1f;
  color: #fff;
  font-size: 16px;
  font-weight: 560;
  letter-spacing: 0.06em;
  transition: opacity 0.2s ease, transform 0.15s ease;
}

.primary-btn:active:not(:disabled) {
  transform: scale(0.985);
}

.primary-btn:disabled {
  opacity: 0.32;
}

/* ---------- 待命页 ---------- */
.stage {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
}

.stage-bg {
  position: absolute;
  inset: 0;
  background:
    radial-gradient(80% 50% at 50% 38%, #ffffff 0%, rgba(255, 255, 255, 0) 70%),
    linear-gradient(180deg, #f8fbfa 0%, #eaf4f1 100%);
}

.stage-actions {
  position: absolute;
  top: calc(env(safe-area-inset-top) + 14px);
  right: 16px;
  display: flex;
  gap: 10px;
  z-index: 3;
}

.stage-orb {
  position: absolute;
  top: 40%;
  left: 50%;
  transform: translate(-50%, -50%);
  z-index: 1;
}

.stage-text {
  position: absolute;
  left: 0;
  right: 0;
  top: calc(40% + min(44vw, 190px) + 28px);
  padding: 0 28px;
  text-align: center;
  z-index: 2;
}

.line {
  margin: 0;
  font-size: 17px;
  font-weight: 300;
  letter-spacing: 0.1em;
  color: rgba(29, 29, 31, 0.72);
}

.line-err {
  margin: 12px 0 0;
  font-size: 12.5px;
  letter-spacing: 0.02em;
  color: rgba(198, 40, 40, 0.8);
}

.line-enter-active,
.line-leave-active {
  transition: opacity 0.35s ease, transform 0.35s ease;
}

.line-enter-from {
  opacity: 0;
  transform: translateY(6px);
}

.line-leave-to {
  opacity: 0;
  transform: translateY(-6px);
}

/* ---------- 设置弹层 ---------- */
.sheet-mask {
  position: absolute;
  inset: 0;
  z-index: 10;
  background: rgba(0, 0, 0, 0.18);
  -webkit-backdrop-filter: blur(6px);
  backdrop-filter: blur(6px);
}

.sheet {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 11;
  max-height: 84%;
  display: flex;
  flex-direction: column;
  border-radius: 26px 26px 0 0;
  background: #f5f5f7;
  box-shadow: 0 -10px 40px rgba(0, 0, 0, 0.1);
  padding-bottom: env(safe-area-inset-bottom);
}

.sheet-grab {
  width: 38px;
  height: 4px;
  margin: 8px auto 0;
  border-radius: 2px;
  background: rgba(0, 0, 0, 0.14);
}

.sheet-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 20px 8px;
}

.sheet-head strong {
  font-size: 17px;
  font-weight: 650;
}

.sheet-done {
  border: none;
  background: transparent;
  color: #1eb48c;
  font-size: 15px;
  font-weight: 560;
}

.sheet-body {
  overflow-y: auto;
  padding: 4px 16px 20px;
}

.field {
  padding: 14px 16px;
}

.field + .field {
  border-top: 1px solid rgba(0, 0, 0, 0.06);
}

.field label {
  font-size: 14px;
  font-weight: 560;
}

.field-line {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
}

.field-value {
  font-size: 13px;
  color: #86868b;
  font-variant-numeric: tabular-nums;
}

.field-hint {
  margin: 6px 0 0;
  font-size: 12px;
  line-height: 1.55;
  color: #8e8e93;
}

.field-err {
  margin: 8px 0 0;
  font-size: 12.5px;
  color: #c62828;
}

.text-input {
  display: block;
  width: 100%;
  box-sizing: border-box;
  margin-top: 8px;
  height: 42px;
  padding: 0 14px;
  border: 1px solid rgba(0, 0, 0, 0.08);
  border-radius: 12px;
  background: #f5f5f7;
  font-size: 17px;
  letter-spacing: 0.1em;
  color: #1d1d1f;
  outline: none;
  transition: border-color 0.2s ease, background 0.2s ease;
}

.text-input:focus {
  border-color: rgba(30, 180, 140, 0.7);
  background: #fff;
}

.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 10px;
}

.chip {
  display: inline-flex;
  flex-direction: column;
  align-items: center;
  min-width: 40px;
  padding: 5px 8px;
  border-radius: 10px;
  background: linear-gradient(135deg, rgba(30, 180, 140, 0.12), rgba(34, 201, 157, 0.16));
  font-size: 16px;
  line-height: 1.2;
}

.chip small {
  font-size: 11px;
  color: #6e6e73;
}

.slider {
  width: 100%;
  margin: 12px 0 0;
  height: 24px;
  accent-color: #1d1d1f;
}

.slider-scale {
  display: flex;
  justify-content: space-between;
  font-size: 11px;
  color: #8e8e93;
}

.field--line {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.text-action {
  flex-shrink: 0;
  border: none;
  background: transparent;
  padding: 8px 2px;
  color: #c45c5c;
  font-size: 14px;
  letter-spacing: 0.04em;
}

.field--switch {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
}

.switch-text {
  flex: 1;
  min-width: 0;
}

.switch {
  flex-shrink: 0;
  position: relative;
  width: 50px;
  height: 30px;
  border: none;
  border-radius: 15px;
  background: #d1d1d6;
  transition: background 0.25s ease;
}

.switch i {
  position: absolute;
  top: 2px;
  left: 2px;
  width: 26px;
  height: 26px;
  border-radius: 50%;
  background: #fff;
  box-shadow: 0 2px 5px rgba(0, 0, 0, 0.22);
  transition: transform 0.25s cubic-bezier(0.3, 1.3, 0.5, 1);
}

.switch--on {
  background: linear-gradient(135deg, #1eb48c, #22c99d);
}

.switch--on i {
  transform: translateX(20px);
}

.segment {
  display: flex;
  margin-top: 10px;
  padding: 3px;
  border-radius: 11px;
  background: rgba(118, 118, 128, 0.12);
}

.segment button {
  flex: 1;
  height: 34px;
  border: none;
  border-radius: 9px;
  background: transparent;
  color: #3a3a3c;
  font-size: 13.5px;
  transition: all 0.2s ease;
}

.segment .segment--on {
  background: #fff;
  font-weight: 600;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.12);
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.25s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

.sheet-enter-active,
.sheet-leave-active {
  transition: transform 0.38s cubic-bezier(0.22, 1, 0.36, 1);
}

.sheet-enter-from,
.sheet-leave-to {
  transform: translateY(100%);
}
</style>

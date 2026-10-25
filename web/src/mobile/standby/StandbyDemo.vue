<template>
  <div class="standby">
    <header class="sb-head">
      <strong>{{ t('standby.title') }} · Standby</strong>
      <button type="button" class="sb-close" @click="close">{{ t('standby.close') }}</button>
    </header>

    <div v-if="!supported" class="sb-warn">{{ t('standby.notNative') }}</div>
    <div v-else-if="voiceCfg.checked && !voiceCfg.configured" class="sb-warn">{{ t('standby.notConfigured') }}</div>
    <div v-else-if="voiceCfg.checked" class="sb-ok">
      {{ t('standby.configOk', { asr: voiceCfg.asr, tts: voiceCfg.tts }) }}
    </div>
    <div v-else class="sb-tip">{{ t('standby.configChecking') }}</div>

    <!-- 主控制 -->
    <section class="sb-card sb-center">
      <div class="sb-orb" :class="'sb-orb--' + orbKind">
        <span>{{ phaseText }}</span>
      </div>
      <div class="sb-btns">
        <button
          type="button"
          class="sb-main-btn"
          :class="{ 'sb-main-btn--stop': running }"
          :disabled="!supported || busy || (!running && !canStart)"
          @click="toggle"
        >
          {{ busy ? t('standby.busy') : running ? t('standby.stop') : t('standby.start') }}
        </button>
        <button
          v-if="state.phase === 'thinking' || state.phase === 'speaking'"
          type="button"
          class="sb-sub-btn"
          @click="engine.interrupt()"
        >
          {{ t('standby.interrupt') }}
        </button>
      </div>
      <div v-if="state.error" class="sb-err">{{ state.error }}</div>
      <div v-if="state.note" class="sb-tip">{{ state.note }}</div>
      <div v-if="running" class="sb-tip">{{ t('standby.runningHint') }}</div>
    </section>

    <!-- 权限与保活引导 -->
    <section class="sb-card">
      <div class="sb-card-title">
        <span>{{ t('standby.guide.title') }}</span>
        <button type="button" class="sb-link" @click="refreshStatus">{{ t('standby.guide.refresh') }}</button>
      </div>
      <div class="sb-tip">{{ t('standby.guide.intro') }}</div>

      <div v-for="item in guideItems" :key="item.key" class="sb-guide" :class="{ 'sb-guide--ok': item.ok }">
        <div class="sb-guide-head">
          <span class="sb-badge" :class="item.ok ? 'sb-badge--ok' : 'sb-badge--todo'">
            {{ item.ok ? t('standby.guide.done') : t('standby.guide.todo') }}
          </span>
          <b>{{ t(`standby.guide.${item.key}.title`) }}</b>
        </div>
        <div class="sb-guide-desc">
          {{ t(`standby.guide.${item.key}.desc`, { brand: brandText }) }}
        </div>
        <div class="sb-guide-ops">
          <button v-if="item.action" type="button" class="sb-small-btn" @click="item.action()">
            {{ t(`standby.guide.${item.key}.action`) }}
          </button>
          <label v-if="item.manual" class="sb-check">
            <input v-model="manual[item.key]" type="checkbox" />
            {{ t('standby.guide.manualDone') }}
          </label>
        </div>
      </div>

      <div v-if="pendingCount > 0" class="sb-err">{{ t('standby.guide.pending', { n: pendingCount }) }}</div>
      <div v-else class="sb-good">{{ t('standby.guide.allGood') }}</div>
    </section>

    <!-- 实时状态 -->
    <section class="sb-card">
      <div class="sb-card-title">{{ t('standby.live.title') }}</div>
      <div class="sb-level"><div class="sb-level-bar" :style="{ width: state.level + '%' }"></div></div>
      <div class="sb-db">
        <span>{{ t('standby.live.volume') }} {{ state.peakDb }} dB</span>
        <span>{{ t('standby.live.wakeCount') }} {{ state.wakeCount }}</span>
      </div>
      <div v-if="state.input" class="sb-tip">{{ t('standby.live.input') }}：{{ state.input }}</div>

      <div class="sb-field">{{ t('standby.live.heard') }}</div>
      <div class="sb-box">{{ state.partial || '—' }}</div>

      <div class="sb-field">{{ t('standby.live.sent') }}</div>
      <ul v-if="state.sent.length" class="sb-list">
        <li v-for="(s, i) in state.sent.slice(0, 5)" :key="i">{{ s.time }} · {{ s.text }}</li>
      </ul>
      <div v-else class="sb-box">{{ t('standby.live.empty') }}</div>

      <div class="sb-field">{{ t('standby.live.reply') }}</div>
      <div class="sb-box">{{ state.reply || '—' }}</div>

      <div class="sb-field">{{ t('standby.live.speaking') }}</div>
      <div class="sb-box">{{ state.speaking || '—' }}</div>

      <div class="sb-field">{{ t('standby.live.metrics') }}</div>
      <div class="sb-metrics">
        <div><b>{{ fmt(state.metrics.endpointToSend) }}</b><span>{{ t('standby.live.endpointToSend') }}</span></div>
        <div><b>{{ fmt(state.metrics.sendToFirstText) }}</b><span>{{ t('standby.live.sendToFirstText') }}</span></div>
        <div>
          <b>{{ fmt(state.metrics.firstTextToFirstAudio) }}</b><span>{{ t('standby.live.firstTextToFirstAudio') }}</span>
        </div>
      </div>
    </section>

    <!-- 参数 -->
    <section class="sb-card">
      <div class="sb-card-title">{{ t('standby.settings.title') }}</div>
      <div v-if="running" class="sb-tip">{{ t('standby.settings.lockedHint') }}</div>

      <label class="sb-field">{{ t('standby.settings.word') }}</label>
      <input v-model.trim="cfg.word" class="sb-input" :disabled="running" maxlength="8" />
      <div v-if="!wordCheck.ok" class="sb-err">{{ wordCheck.message }}</div>
      <div v-else class="sb-chips">
        <span v-for="(s, i) in syllables" :key="i" class="sb-chip">{{ cfg.word[i] }}<small>{{ s }}</small></span>
      </div>

      <label class="sb-field">{{ t('standby.settings.endWindow') }}</label>
      <input v-model.number="cfg.endWindowMs" type="number" step="100" min="200" max="3000" class="sb-input" :disabled="running" />
      <div class="sb-tip">{{ t('standby.settings.endWindowHint') }}</div>

      <label class="sb-field">{{ t('standby.settings.noSpeech') }}</label>
      <input v-model.number="cfg.noSpeechSec" type="number" min="2" max="30" class="sb-input" :disabled="running" />

      <label class="sb-check sb-check--block">
        <input v-model="cfg.continuous" type="checkbox" :disabled="running" />
        {{ t('standby.settings.continuous') }}
      </label>
      <label class="sb-field">{{ t('standby.settings.followUp') }}</label>
      <input v-model.number="cfg.followUpSec" type="number" min="2" max="30" class="sb-input" :disabled="running || !cfg.continuous" />

      <label class="sb-field">{{ t('standby.settings.voice') }}</label>
      <select v-model="cfg.voice" class="sb-input" :disabled="running">
        <option value="female">{{ t('standby.settings.voiceFemale') }}</option>
        <option value="male">{{ t('standby.settings.voiceMale') }}</option>
      </select>

      <label class="sb-field">{{ t('standby.settings.speechRate') }}</label>
      <input v-model.number="cfg.speechRate" type="number" min="-50" max="100" class="sb-input" :disabled="running" />

      <label class="sb-field">{{ t('standby.settings.source') }}</label>
      <select v-model="cfg.source" class="sb-input" :disabled="running">
        <option value="auto">{{ t('standby.settings.sourceAuto') }}</option>
        <option value="phone">{{ t('standby.settings.sourcePhone') }}</option>
      </select>
    </section>

    <!-- 日志 -->
    <section class="sb-card">
      <div class="sb-card-title">{{ t('standby.live.logs') }}</div>
      <div v-if="!state.logs.length" class="sb-tip">{{ t('standby.live.empty') }}</div>
      <ul v-else class="sb-logs">
        <li v-for="(l, i) in state.logs" :key="i">{{ l.time }} · {{ l.msg }}</li>
      </ul>
    </section>

    <p class="sb-foot">{{ t('standby.risks') }}</p>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { http } from '../api'
import { buildKeywordLine, toSyllables, validateWakeWord } from '../wake/ppinyin'
import { createStandbyEngine } from './standbyEngine'
import * as native from './standbyNative'

const emit = defineEmits(['close'])
const { t } = useI18n()

const supported = native.isStandbySupported()
const engine = createStandbyEngine()
const state = engine.state

// ---------------------------------------------------------------- 参数（本地保存）

const CFG_KEY = 'standby_cfg'
const MANUAL_KEY = 'standby_manual'

function loadJson(key, fallback) {
  try {
    return { ...fallback, ...(JSON.parse(localStorage.getItem(key) || '{}') || {}) }
  } catch {
    return { ...fallback }
  }
}

const cfg = reactive(
  loadJson(CFG_KEY, {
    word: '你好灵芽',
    endWindowMs: 800,
    noSpeechSec: 8,
    continuous: true,
    followUpSec: 6,
    voice: 'female',
    speechRate: 0,
    source: 'auto',
  }),
)
// 旧版本存过自由文本音色，改成固定两个后要纠正
if (cfg.voice !== 'female' && cfg.voice !== 'male') cfg.voice = 'female'
const manual = reactive(loadJson(MANUAL_KEY, { autostart: false, lock: false }))
watch(cfg, () => localStorage.setItem(CFG_KEY, JSON.stringify(cfg)), { deep: true })
watch(manual, () => localStorage.setItem(MANUAL_KEY, JSON.stringify(manual)), { deep: true })

const wordCheck = computed(() => validateWakeWord(cfg.word))
const syllables = computed(() => (wordCheck.value.ok ? toSyllables(cfg.word) : []))

// ---------------------------------------------------------------- 服务端语音配置

const voiceCfg = reactive({ checked: false, configured: false, asr: '', tts: '' })

async function checkVoiceConfig() {
  try {
    const res = await http.get('/api/voice/config')
    voiceCfg.configured = !!res.data?.configured
    voiceCfg.asr = res.data?.asr_resource_id || ''
    voiceCfg.tts = res.data?.tts_resource_id || ''
  } catch {
    voiceCfg.configured = false
  } finally {
    voiceCfg.checked = true
  }
}

// ---------------------------------------------------------------- 权限与保活引导

const status = ref(null)

async function refreshStatus() {
  if (!supported) return
  try {
    status.value = await native.getStandbyStatus()
  } catch {
    /* ignore */
  }
}

async function grantPermissions() {
  try {
    await native.requestStandbyPermissions()
  } catch {
    /* ignore */
  }
  await refreshStatus()
  // 被「不再询问」拒绝后系统不会再弹框，只能引导去设置页
  if (status.value && !status.value.microphone) await native.openStandbySettings('app')
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

const guideItems = computed(() => {
  const s = status.value || {}
  return [
    { key: 'mic', ok: !!s.microphone, action: grantPermissions },
    { key: 'notification', ok: !!s.notifications, action: () => openSettings('notification') },
    { key: 'battery', ok: !!s.batteryUnrestricted, action: () => openSettings('battery') },
    { key: 'autostart', ok: !!manual.autostart, manual: true, action: () => openSettings('autostart') },
    { key: 'lock', ok: !!manual.lock, manual: true },
    { key: 'bluetooth', ok: !!s.bluetooth, optional: true, action: grantPermissions },
  ]
})
const pendingCount = computed(() => guideItems.value.filter((i) => !i.optional && !i.ok).length)

function onVisible() {
  if (document.visibilityState === 'visible') refreshStatus()
}

// ---------------------------------------------------------------- 开始 / 结束

const busy = ref(false)
const running = computed(() => state.phase !== 'off')
const canStart = computed(() => wordCheck.value.ok)

const orbKind = computed(() => {
  if (state.phase === 'listening') return 'listen'
  if (state.phase === 'thinking') return 'think'
  if (state.phase === 'speaking') return 'speak'
  if (state.phase === 'standby') return 'standby'
  return 'off'
})
const phaseText = computed(() =>
  state.phase === 'listening' && state.followUp ? t('standby.phase.followUp') : t(`standby.phase.${state.phase}`),
)

function fmt(v) {
  return v == null ? '—' : v
}

async function resolveUserId() {
  const res = await http.get('/api/user/me')
  if (!res.data?.success) throw new Error('请先登录')
  return String(res.data.user_id)
}

async function toggle() {
  if (busy.value) return
  busy.value = true
  try {
    if (running.value) {
      await engine.stop()
      return
    }
    const userId = await resolveUserId()
    const syl = toSyllables(cfg.word)
    await engine.start({
      keywords: buildKeywordLine(cfg.word, { score: 1.5, threshold: 0.25, syllables: syl }),
      source: cfg.source,
      userId,
      endWindowMs: Number(cfg.endWindowMs) || 800,
      noSpeechSec: Number(cfg.noSpeechSec) || 8,
      continuous: !!cfg.continuous,
      followUpSec: Number(cfg.followUpSec) || 6,
      voice: cfg.voice,
      speechRate: Number(cfg.speechRate) || 0,
      notification: {
        title: t('standby.notification.title'),
        text: t('standby.notification.text'),
        stopLabel: t('standby.notification.stopLabel'),
      },
    })
  } catch (e) {
    state.error = e?.message || String(e)
  } finally {
    busy.value = false
    refreshStatus()
  }
}

async function close() {
  await engine.stop()
  emit('close')
}

onMounted(() => {
  refreshStatus()
  checkVoiceConfig()
  document.addEventListener('visibilitychange', onVisible)
})

onBeforeUnmount(() => {
  document.removeEventListener('visibilitychange', onVisible)
  engine.stop()
})
</script>

<style scoped>
.standby {
  position: fixed;
  inset: 0;
  z-index: 9999;
  overflow-y: auto;
  background: #f2f2f2;
  padding: calc(env(safe-area-inset-top, 0px) + 8px) 12px calc(env(safe-area-inset-bottom, 0px) + 20px);
  color: #1f2937;
  font-size: 14px;
}
.sb-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 2px 12px;
  font-size: 17px;
}
.sb-close {
  border: 0;
  background: #e5e7eb;
  border-radius: 8px;
  padding: 6px 14px;
  font-size: 14px;
}
.sb-card {
  background: #fff;
  border-radius: 12px;
  padding: 14px;
  margin-bottom: 12px;
}
.sb-center {
  text-align: center;
}
.sb-card-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-weight: 600;
  margin-bottom: 8px;
}
.sb-link {
  border: 0;
  background: none;
  color: #047857;
  font-size: 13px;
}
.sb-warn {
  background: #fef3c7;
  color: #92400e;
  border-radius: 10px;
  padding: 10px 12px;
  margin-bottom: 12px;
}
.sb-ok {
  background: #ecfdf5;
  color: #047857;
  border-radius: 10px;
  padding: 8px 12px;
  margin-bottom: 12px;
  font-size: 12px;
}
.sb-tip {
  color: #6b7280;
  font-size: 12px;
  margin-top: 6px;
  line-height: 1.6;
}
.sb-err {
  color: #dc2626;
  margin-top: 8px;
  word-break: break-all;
}
.sb-good {
  color: #047857;
  margin-top: 8px;
}
.sb-orb {
  min-width: 150px;
  max-width: 90%;
  min-height: 96px;
  padding: 12px 18px;
  border-radius: 48px;
  margin: 6px auto 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-size: 16px;
  font-weight: 600;
  transition: background 0.2s;
  box-sizing: border-box;
}
.sb-orb--off {
  background: #9ca3af;
}
.sb-orb--standby {
  background: #10b981;
  animation: sb-pulse 1.8s ease-in-out infinite;
}
.sb-orb--listen {
  background: #f59e0b;
  animation: sb-pulse-warm 1s ease-in-out infinite;
}
.sb-orb--think {
  background: #6366f1;
}
.sb-orb--speak {
  background: #0ea5e9;
  animation: sb-pulse-blue 1.2s ease-in-out infinite;
}
@keyframes sb-pulse {
  0%,
  100% {
    box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.45);
  }
  50% {
    box-shadow: 0 0 0 16px rgba(16, 185, 129, 0);
  }
}
@keyframes sb-pulse-warm {
  0%,
  100% {
    box-shadow: 0 0 0 0 rgba(245, 158, 11, 0.5);
  }
  50% {
    box-shadow: 0 0 0 16px rgba(245, 158, 11, 0);
  }
}
@keyframes sb-pulse-blue {
  0%,
  100% {
    box-shadow: 0 0 0 0 rgba(14, 165, 233, 0.5);
  }
  50% {
    box-shadow: 0 0 0 16px rgba(14, 165, 233, 0);
  }
}
.sb-btns {
  display: flex;
  justify-content: center;
  gap: 10px;
}
.sb-main-btn {
  min-width: 55%;
  border: 0;
  border-radius: 24px;
  padding: 12px 0;
  font-size: 16px;
  font-weight: 600;
  color: #fff;
  background: #10b981;
}
.sb-main-btn--stop {
  background: #ef4444;
}
.sb-main-btn:disabled {
  opacity: 0.5;
}
.sb-sub-btn {
  border: 0;
  border-radius: 24px;
  padding: 12px 18px;
  font-size: 15px;
  color: #fff;
  background: #6366f1;
}
.sb-guide {
  margin-top: 10px;
  padding: 10px 12px;
  border-radius: 10px;
  background: #fff7ed;
}
.sb-guide--ok {
  background: #f0fdf4;
}
.sb-guide-head {
  display: flex;
  align-items: center;
  gap: 8px;
}
.sb-badge {
  font-size: 11px;
  border-radius: 8px;
  padding: 1px 8px;
  color: #fff;
}
.sb-badge--ok {
  background: #10b981;
}
.sb-badge--todo {
  background: #f59e0b;
}
.sb-guide-desc {
  margin-top: 6px;
  color: #4b5563;
  font-size: 12px;
  line-height: 1.6;
}
.sb-guide-ops {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 8px;
}
.sb-small-btn {
  border: 0;
  border-radius: 8px;
  padding: 6px 12px;
  font-size: 13px;
  color: #fff;
  background: #10b981;
}
.sb-check {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: #374151;
}
.sb-check--block {
  display: flex;
  margin-top: 14px;
}
.sb-level {
  height: 8px;
  background: #e5e7eb;
  border-radius: 4px;
  overflow: hidden;
}
.sb-level-bar {
  height: 100%;
  background: #10b981;
  transition: width 0.12s linear;
}
.sb-db {
  display: flex;
  justify-content: space-between;
  margin-top: 6px;
  font-size: 12px;
  color: #374151;
}
.sb-field {
  display: block;
  margin-top: 14px;
  margin-bottom: 6px;
  font-weight: 600;
  font-size: 13px;
}
.sb-box {
  min-height: 20px;
  background: #f9fafb;
  border-radius: 8px;
  padding: 8px 10px;
  line-height: 1.6;
  word-break: break-all;
}
.sb-list {
  margin: 0;
  padding-left: 18px;
  line-height: 1.8;
}
.sb-metrics {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 8px;
  text-align: center;
}
.sb-metrics b {
  display: block;
  font-size: 18px;
}
.sb-metrics span {
  font-size: 11px;
  color: #6b7280;
}
.sb-input {
  width: 100%;
  box-sizing: border-box;
  border: 1px solid #d1d5db;
  border-radius: 8px;
  padding: 9px 12px;
  font-size: 16px;
  background: #fff;
}
.sb-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 8px;
}
.sb-chip {
  display: inline-flex;
  flex-direction: column;
  align-items: center;
  background: #ecfdf5;
  border-radius: 8px;
  padding: 4px 10px;
  font-size: 16px;
}
.sb-chip small {
  font-size: 11px;
  color: #047857;
}
.sb-logs {
  margin: 0;
  padding-left: 18px;
  line-height: 1.7;
  font-size: 12px;
  word-break: break-all;
}
.sb-foot {
  color: #9ca3af;
  font-size: 12px;
  line-height: 1.6;
}
</style>

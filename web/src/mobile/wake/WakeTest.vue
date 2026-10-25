<template>
  <div class="wake-test">
    <header class="wt-head">
      <strong>唤醒词测试</strong>
      <button type="button" class="wt-close" @click="close">关闭</button>
    </header>

    <div v-if="!supported" class="wt-warn">
      当前不是安卓原生环境（或插件未注册），无法测试。请用 <code>npm run build:mobile</code> + <code>npx cap sync android</code> 后在手机上运行。
    </div>

    <section class="wt-card">
      <label class="wt-label">唤醒词（只能是汉字，建议 4 个字以上）</label>
      <input v-model.trim="word" class="wt-input" :disabled="running" maxlength="8" placeholder="例如：灵芽灵芽" />

      <div v-if="check.ok" class="wt-pinyin">
        <span v-for="(s, i) in syllables" :key="i" class="wt-chip">{{ word[i] }}<small>{{ s }}</small></span>
      </div>
      <div v-if="!check.ok && word" class="wt-err">{{ check.message }}</div>
      <div v-else-if="check.ok && word.length < 4" class="wt-tip">字数偏少，容易被日常说话误唤醒，建议 4 个字以上。</div>
      <div v-else-if="check.ok && hasRepeat" class="wt-tip">
        词里有重复的读音（如「灵芽灵芽」），快速说时两遍容易糊成一团，识别会变差。建议用不重复的词，例如「你好灵芽」。
      </div>

      <details class="wt-more">
        <summary>多音字读音不对？手动指定读音</summary>
        <input
          v-model.trim="manualPinyin"
          class="wt-input"
          :disabled="running"
          placeholder="带声调拼音，空格分隔，例如：xiǎo lè"
        />
        <div v-if="manualPinyin && !manualOk" class="wt-err">读音个数要和字数一致（{{ word.length }} 个）</div>
      </details>

      <div class="wt-row">
        <label>
          触发阈值 <small>（越小越容易唤醒）</small>
          <input v-model.number="threshold" type="number" step="0.05" min="0.05" max="0.9" :disabled="running" />
        </label>
        <label>
          增强分数 <small>（越大越容易唤醒）</small>
          <input v-model.number="score" type="number" step="0.1" min="0.1" max="5" :disabled="running" />
        </label>
      </div>
      <div class="wt-tip">修改参数后需要先「停止」再「开始」才会生效。</div>

      <label class="wt-label wt-label--gap">麦克风来源</label>
      <select v-model="source" class="wt-input wt-select" :disabled="running">
        <option value="auto">自动：连着蓝牙耳机就用耳机麦克风</option>
        <option value="phone">只用手机自带麦克风</option>
      </select>
      <div class="wt-tip">用耳机麦克风时，耳机会切到「通话模式」，这期间耳机放音乐的音质会变差，停止监听后自动恢复。</div>
    </section>

    <section class="wt-card wt-center">
      <div class="wt-orb" :class="orbClass">
        <span>{{ orbText }}</span>
      </div>
      <button
        type="button"
        class="wt-main-btn"
        :class="{ 'wt-main-btn--stop': running }"
        :disabled="busy || !supported || (!running && !check.ok)"
        @click="toggle"
      >
        {{ busy ? '处理中…' : running ? '停止监听' : '开始监听' }}
      </button>
      <div v-if="running && inputLabel" class="wt-input-label" :class="{ 'wt-input-label--bt': inputBt }">
        当前麦克风：{{ inputLabel }}
      </div>
      <div v-if="startNote" class="wt-tip wt-note">{{ startNote }}</div>
      <div v-if="errorMsg" class="wt-err">{{ errorMsg }}</div>
    </section>

    <section class="wt-card">
      <div class="wt-stats">
        <div><b>{{ fmtTime(stats.elapsedSec) }}</b><span>已运行</span></div>
        <div><b>{{ wakeCount }}</b><span>唤醒次数</span></div>
        <div><b>{{ stats.avgProcMs.toFixed(1) }} ms</b><span>每 100ms 音频的处理耗时</span></div>
        <div><b>{{ stats.loadPct.toFixed(1) }}%</b><span>模型线程占用（估算）</span></div>
      </div>
      <div class="wt-level"><div class="wt-level-bar" :style="{ width: level + '%' }"></div></div>
      <div class="wt-db">
        <span>当前 {{ peakDb }} dB</span>
        <span>本次最大 {{ maxPeakDb }} dB</span>
      </div>
      <div class="wt-tip">
        条是麦克风音量（分贝刻度，满格约 -10 dB，空格约 -60 dB）。正常说话时「本次最大」一般在 -30 ~ -10 dB；
        如果说话时最大值也低于 -45 dB，说明麦克风收音偏小，会影响唤醒；一直是 -60 dB 左右说明没收到声音。
      </div>
    </section>

    <section class="wt-card">
      <div class="wt-label">唤醒记录</div>
      <div v-if="!logs.length" class="wt-tip">还没有唤醒。开始监听后，对着手机喊唤醒词。</div>
      <ul v-else class="wt-logs">
        <li v-for="(l, i) in logs" :key="i">{{ l.time }} · 第 {{ l.count }} 次 · {{ l.keyword }}</li>
      </ul>
    </section>

    <p class="wt-foot">
      当前为最小测试版：只在 App 前台可用，运行期间会保持屏幕常亮。切到后台/息屏后系统会限制麦克风，这是正常现象，后续用前台服务解决。
    </p>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { buildKeywordLine, toSyllables, validateWakeWord } from './ppinyin'
import { isWakeSupported, onWake, onWakeError, onWakeLevel, onWakeStatus, startWake, stopWake } from './wakeWord'

const emit = defineEmits(['close'])

const supported = isWakeSupported()
const word = ref('灵芽灵芽')
const manualPinyin = ref('')
const threshold = ref(0.25)
const score = ref(1.5)
const source = ref('auto')
const inputLabel = ref('')
const inputBt = ref(false)
const startNote = ref('')

const running = ref(false)
const busy = ref(false)
const woke = ref(false)
const errorMsg = ref('')
const wakeCount = ref(0)
const logs = ref([])
const stats = ref({ elapsedSec: 0, avgProcMs: 0, loadPct: 0 })
const level = ref(0)
const peakDb = ref(-60)
const maxPeakDb = ref(-60)

const check = computed(() => validateWakeWord(word.value))

const manualList = computed(() => manualPinyin.value.split(/\s+/).filter(Boolean))
const manualOk = computed(() => manualList.value.length === word.value.length)

const syllables = computed(() => {
  if (!check.value.ok) return []
  if (manualPinyin.value && manualOk.value) return manualList.value
  return toSyllables(word.value)
})

/** 相邻读音相同，或前半段和后半段读音一样（ABAB），快读时容易糊在一起 */
const hasRepeat = computed(() => {
  const s = syllables.value.map((x) => x.replace(/[^a-züāáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜ]/gi, ''))
  if (s.length < 2) return false
  for (let i = 1; i < s.length; i++) if (s[i] === s[i - 1]) return true
  if (s.length % 2 === 0) {
    const h = s.length / 2
    if (s.slice(0, h).join('|') === s.slice(h).join('|')) return true
  }
  return false
})

const orbClass = computed(() => ({
  'wt-orb--idle': !running.value,
  'wt-orb--listen': running.value && !woke.value,
  'wt-orb--woke': woke.value,
}))
const orbText = computed(() => (woke.value ? '已唤醒！' : running.value ? '监听中…' : '未开始'))

let handles = []
let wokeTimer = null

function fmtTime(sec) {
  const s = Math.floor(sec || 0)
  const mm = String(Math.floor(s / 60)).padStart(2, '0')
  const ss = String(s % 60).padStart(2, '0')
  return `${mm}:${ss}`
}

function nowStr() {
  const d = new Date()
  return [d.getHours(), d.getMinutes(), d.getSeconds()].map((n) => String(n).padStart(2, '0')).join(':')
}

async function toggle() {
  errorMsg.value = ''
  busy.value = true
  try {
    if (running.value) {
      await stopWake()
      running.value = false
      return
    }
    const line = buildKeywordLine(word.value, {
      score: score.value,
      threshold: threshold.value,
      syllables: manualPinyin.value && manualOk.value ? manualList.value : undefined,
    })
    console.log('[wake] keywords:', line)
    wakeCount.value = 0
    logs.value = []
    startNote.value = ''
    level.value = 0
    peakDb.value = -60
    maxPeakDb.value = -60
    const res = await startWake(line, source.value)
    inputLabel.value = res?.input || ''
    inputBt.value = !!res?.bluetooth
    startNote.value = res?.note || ''
    running.value = true
  } catch (e) {
    running.value = false
    errorMsg.value = e?.message || String(e)
  } finally {
    busy.value = false
  }
}

async function close() {
  if (running.value) {
    try {
      await stopWake()
    } catch {
      /* ignore */
    }
  }
  emit('close')
}

onMounted(async () => {
  if (!supported) return
  handles = await Promise.all([
    onWake((e) => {
      wakeCount.value = e.count
      logs.value.unshift({ time: nowStr(), count: e.count, keyword: e.keyword })
      woke.value = true
      clearTimeout(wokeTimer)
      wokeTimer = setTimeout(() => (woke.value = false), 1500)
    }),
    onWakeStatus((e) => {
      if (e.running === false) {
        running.value = false
        return
      }
      stats.value = {
        elapsedSec: e.elapsedSec || 0,
        avgProcMs: e.avgProcMs || 0,
        loadPct: e.loadPct || 0,
      }
      if (e.input) {
        inputLabel.value = e.input
        inputBt.value = !!e.bluetooth
      }
    }),
    onWakeLevel((e) => {
      level.value = e.level || 0
      peakDb.value = e.peakDb
      if (e.peakDb > maxPeakDb.value) maxPeakDb.value = e.peakDb
    }),
    onWakeError((e) => {
      errorMsg.value = e.message
    }),
  ])
})

onBeforeUnmount(() => {
  clearTimeout(wokeTimer)
  handles.forEach((h) => h?.remove?.())
  if (running.value) stopWake().catch(() => {})
})
</script>

<style scoped>
.wake-test {
  position: fixed;
  inset: 0;
  z-index: 9999;
  overflow-y: auto;
  background: #f2f2f2;
  padding: calc(env(safe-area-inset-top, 0px) + 8px) 12px calc(env(safe-area-inset-bottom, 0px) + 20px);
  color: #1f2937;
  font-size: 14px;
}
.wt-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 2px 12px;
  font-size: 17px;
}
.wt-close {
  border: 0;
  background: #e5e7eb;
  border-radius: 8px;
  padding: 6px 14px;
  font-size: 14px;
}
.wt-card {
  background: #fff;
  border-radius: 12px;
  padding: 14px;
  margin-bottom: 12px;
}
.wt-center {
  text-align: center;
}
.wt-label {
  font-weight: 600;
  margin-bottom: 8px;
}
.wt-label--gap {
  display: block;
  margin-top: 14px;
}
.wt-select {
  font-size: 15px;
  background: #fff;
}
.wt-input-label {
  margin-top: 12px;
  font-size: 13px;
  color: #4b5563;
}
.wt-input-label--bt {
  color: #047857;
  font-weight: 600;
}
.wt-note {
  color: #b45309;
}
.wt-input {
  width: 100%;
  box-sizing: border-box;
  border: 1px solid #d1d5db;
  border-radius: 8px;
  padding: 10px 12px;
  font-size: 18px;
}
.wt-pinyin {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 10px;
}
.wt-chip {
  display: inline-flex;
  flex-direction: column;
  align-items: center;
  background: #ecfdf5;
  border-radius: 8px;
  padding: 4px 10px;
  font-size: 18px;
}
.wt-chip small {
  font-size: 12px;
  color: #047857;
}
.wt-err {
  color: #dc2626;
  margin-top: 8px;
  word-break: break-all;
}
.wt-tip {
  color: #6b7280;
  font-size: 12px;
  margin-top: 8px;
}
.wt-warn {
  background: #fef3c7;
  color: #92400e;
  border-radius: 10px;
  padding: 10px 12px;
  margin-bottom: 12px;
}
.wt-more {
  margin-top: 10px;
  font-size: 13px;
  color: #4b5563;
}
.wt-more .wt-input {
  margin-top: 8px;
  font-size: 15px;
}
.wt-row {
  display: flex;
  gap: 10px;
  margin-top: 12px;
}
.wt-row label {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 13px;
}
.wt-row input {
  border: 1px solid #d1d5db;
  border-radius: 8px;
  padding: 8px;
  font-size: 16px;
}
.wt-orb {
  width: 132px;
  height: 132px;
  border-radius: 50%;
  margin: 6px auto 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-size: 18px;
  font-weight: 600;
  transition: background 0.2s;
}
.wt-orb--idle {
  background: #9ca3af;
}
.wt-orb--listen {
  background: #10b981;
  animation: wt-pulse 1.6s ease-in-out infinite;
}
.wt-orb--woke {
  background: #f59e0b;
  transform: scale(1.08);
}
@keyframes wt-pulse {
  0%,
  100% {
    box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.45);
  }
  50% {
    box-shadow: 0 0 0 18px rgba(16, 185, 129, 0);
  }
}
.wt-main-btn {
  width: 70%;
  border: 0;
  border-radius: 24px;
  padding: 12px 0;
  font-size: 16px;
  font-weight: 600;
  color: #fff;
  background: #10b981;
}
.wt-main-btn--stop {
  background: #ef4444;
}
.wt-main-btn:disabled {
  opacity: 0.5;
}
.wt-stats {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
.wt-stats b {
  display: block;
  font-size: 18px;
}
.wt-stats span {
  font-size: 12px;
  color: #6b7280;
}
.wt-level {
  height: 8px;
  background: #e5e7eb;
  border-radius: 4px;
  margin-top: 12px;
  overflow: hidden;
}
.wt-level-bar {
  height: 100%;
  background: #10b981;
  transition: width 0.12s linear;
}
.wt-db {
  display: flex;
  justify-content: space-between;
  margin-top: 6px;
  font-size: 12px;
  color: #374151;
}
.wt-logs {
  margin: 0;
  padding-left: 18px;
  line-height: 1.8;
}
.wt-foot {
  color: #9ca3af;
  font-size: 12px;
  line-height: 1.6;
}
</style>

/**
 * 待命（Standby）状态机 —— JS 只负责配置与界面。
 *
 * 对话全在原生 StandbyOrchestrator：唤醒 → 识别 → Agent → 合成 → 播放。
 * 息屏不依赖 WebView。
 */
import { reactive } from 'vue'
import { configureNativePipeline } from './nativePipeline'
import * as native from './standbyNative'

const DEFAULT_OPTIONS = {
  source: 'auto',
  endWindowMs: 500,
  continuous: true,
  bargeIn: true,
  speechRate: 0,
}

function nowStr() {
  const d = new Date()
  return [d.getHours(), d.getMinutes(), d.getSeconds()].map((n) => String(n).padStart(2, '0')).join(':')
}

/**
 * @typedef {object} StandbyOptions
 * @property {string} keywords
 * @property {'auto'|'phone'} source
 * @property {string} userId
 * @property {number} endWindowMs
 * @property {boolean} bargeIn
 * @property {boolean} continuous
 * @property {string} voice
 * @property {number} speechRate
 * @property {{title:string,text:string,stopLabel:string}} notification
 */

export function createStandbyEngine() {
  const state = reactive({
    /** off | starting | standby | listening | thinking | speaking */
    phase: 'off',
    followUp: false,
    error: '',
    note: '',
    input: '',
    level: 0,
    peakDb: -60,
    outLevel: 0,
    wakePulse: 0,
    wakeCount: 0,
    partial: '',
    sent: [],
    reply: '',
    speaking: '',
    logs: [],
    metrics: { endpointToSend: null, sendToFirstText: null, firstTextToFirstAudio: null },
  })

  /** @type {StandbyOptions|null} */
  let opts = null
  let handles = []

  function log(msg) {
    state.logs.unshift({ time: nowStr(), msg })
    if (state.logs.length > 120) state.logs.length = 120
    console.log('[yavis]', msg)
    try {
      native.debugLog?.(String(msg))
    } catch {
      /* ignore */
    }
  }

  async function start(options) {
    if (state.phase !== 'off') return
    opts = { ...DEFAULT_OPTIONS, ...options }
    state.error = ''
    state.note = ''
    state.phase = 'starting'
    state.wakeCount = 0
    state.sent = []
    state.reply = ''
    state.partial = ''
    state.logs = []
    try {
      await attachListeners()
      const perm = await native.requestStandbyPermissions()
      if (!perm.microphone) throw new Error('没有麦克风权限，无法待命')
      await native.startStandbyService(opts.notification)
      await configureNativePipeline({
        userId: opts.userId,
        continuous: !!opts.continuous,
        voice: opts.voice,
        speechRate: opts.speechRate,
        endWindowMs: opts.endWindowMs,
      })
      log('对话管线：全原生（息屏可用）')
      const res = await native.startWake(opts.keywords, opts.source, !!opts.bargeIn)
      state.input = res?.input || ''
      state.note = res?.note || ''
      state.phase = 'standby'
      document.addEventListener('visibilitychange', onVisibility)
      log(`待命已开始，麦克风：${state.input || '未知'}`)
      if (opts.bargeIn) log(`语音打断：已开启，回声消除 ${res?.aec || '未知'}`)
    } catch (e) {
      state.error = e?.message || String(e)
      log(`启动失败：${state.error}`)
      await teardown()
    }
  }

  /**
   * 运行中改参数。音色 / 语速下一轮播报生效，断句时长下一次聆听生效，
   * 连续对话开关立即生效。唤醒词、麦克风来源需要重启待命（由界面负责）。
   */
  async function updateOptions(partial) {
    if (!opts) return
    opts = { ...opts, ...partial }
    native.setPipelineContinuous(!!opts.continuous).catch(() => {})
    if (partial.endWindowMs != null || partial.voice != null || partial.speechRate != null || partial.continuous != null) {
      configureNativePipeline({
        userId: opts.userId,
        continuous: !!opts.continuous,
        voice: opts.voice,
        speechRate: opts.speechRate,
        endWindowMs: opts.endWindowMs,
      }).catch(() => {})
    }
  }

  async function stop() {
    if (state.phase === 'off') return
    log('结束待命')
    await teardown()
  }

  async function interrupt() {
    if (state.phase !== 'thinking' && state.phase !== 'speaking') return
    log('已打断')
    await native.pipelineInterrupt()
  }

  function onPipelineEvent(e) {
    const phase = e.phase || state.phase
    const key = e.key || ''
    const value = e.value || ''
    if (phase && phase !== 'off') state.phase = phase
    if (key === 'partial') state.partial = value
    else if (key === 'sent') {
      state.sent.unshift({ time: nowStr(), text: value })
      state.reply = ''
      state.partial = value
      log(`原生断句→Agent：「${value.slice(0, 40)}」`)
    } else if (key === 'replyAppend') state.reply += value
    else if (key === 'speakingText') state.speaking = value
    else if (key === 'speaking') state.speaking = state.speaking || ''
    else if (key === 'wake') {
      state.wakeCount++
      state.wakePulse++
      state.partial = ''
      log(`原生唤醒：「${value}」`)
    } else if (key === 'bargeIn') {
      state.wakePulse++
      log(`原生打断：「${value}」`)
    } else if (key === 'error' || key === 'errorDone') {
      state.error = value
      log(`原生管线错误：${value}`)
    } else if (key === 'continue' || key === 'standby') {
      state.speaking = ''
      state.partial = ''
    }
  }

  async function attachListeners() {
    handles = await Promise.all([
      native.onWake((e) => {
        state.wakeCount = e.count || state.wakeCount + 1
        state.wakePulse++
        if (state.phase === 'standby' || state.phase === 'off') state.phase = 'listening'
      }),
      native.onPipeline((e) => onPipelineEvent(e)),
      native.onLevel((e) => {
        state.level = e.level || 0
        state.peakDb = e.peakDb
      }),
      native.onStatus((e) => {
        if (e.input) state.input = e.input
        if (e.running === false && state.phase !== 'off') {
          log('原生录音引擎已停止')
          teardown()
        }
      }),
      native.onNativeError((e) => {
        log(`原生错误：${e.message}`)
        state.error = e.message
      }),
      native.onServiceStopped(() => {
        log('常驻服务已停止（通知栏停止 / 被系统结束）')
        teardown({ skipService: true })
      }),
    ])
  }

  async function teardown({ skipService = false } = {}) {
    document.removeEventListener('visibilitychange', onVisibility)
    handles.forEach((h) => h?.remove?.())
    handles = []
    try {
      await native.stopWake()
    } catch {
      /* ignore */
    }
    if (!skipService) {
      try {
        await native.stopStandbyService()
      } catch {
        /* ignore */
      }
    }
    state.phase = 'off'
    state.partial = ''
    state.level = 0
    state.outLevel = 0
    state.speaking = ''
  }

  function onVisibility() {
    log(`页面${document.visibilityState === 'hidden' ? '进入后台 / 息屏' : '回到前台'}`)
  }

  return { state, start, stop, interrupt, updateOptions }
}

/**
 * 待命（Standby）状态机。
 *
 *   off ─start→ standby ─唤醒词→ listening ─豆包断句→ thinking ─首句→ speaking ─播完→ listening(连续对话) ─超时→ standby
 *
 * 分工：
 *   原生（WakeWord 插件）：麦克风 + 离线唤醒；唤醒后把 PCM 以 audio 事件上送；用 AudioTrack 播放合成音频。
 *   这里（JS）：串起 豆包识别(WS) → Agent(SSE) → 豆包合成(WS) → 原生播放，并维护界面要显示的状态。
 */
import { reactive } from 'vue'
import { streamAgentReply } from './agentStream'
import { createSentenceSplitter } from './sentenceSplitter'
import * as native from './standbyNative'
import { AsrClient, TtsClient } from './voiceClients'

const MAX_UTTERANCE_MS = 60_000
/** 少于这么多个有效字的识别结果视为噪声，不发给 Agent */
const MIN_VALID_CHARS = 2
const TTS_SAMPLE_RATE = 24000

function nowStr() {
  const d = new Date()
  return [d.getHours(), d.getMinutes(), d.getSeconds()].map((n) => String(n).padStart(2, '0')).join(':')
}

function validChars(text) {
  return (text || '').replace(/[\s\p{P}\p{S}]/gu, '').length
}

/**
 * @typedef {object} StandbyOptions
 * @property {string} keywords      sherpa 关键词行（见 ppinyin.buildKeywordLine）
 * @property {'auto'|'phone'} source 麦克风来源
 * @property {string} userId        当前用户 id（Soul 会话 id）
 * @property {number} endWindowMs   断句静音时长（毫秒）
 * @property {number} noSpeechSec   唤醒后多久没人说话就放弃
 * @property {boolean} continuous   播报后是否继续听（连续对话）
 * @property {number} followUpSec   连续对话窗口（秒）
 * @property {string} voice         合成音色，空=后端默认
 * @property {number} speechRate    语速 -50~100
 * @property {{title:string,text:string,stopLabel:string}} notification 常驻通知文案
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
    wakeCount: 0,
    partial: '',
    /** 本轮已发送给 Agent 的句子（最近在前） */
    sent: [],
    reply: '',
    speaking: '',
    logs: [],
    /** 调试用时延，毫秒 */
    metrics: { endpointToSend: null, sendToFirstText: null, firstTextToFirstAudio: null },
  })

  /** @type {StandbyOptions|null} */
  let opts = null
  let handles = []
  let asr = null
  let tts = null
  let abortCtl = null
  let splitter = null
  let noSpeechTimer = null
  let maxUtteranceTimer = null
  let heardSpeech = false
  /** 播放分片按顺序写入原生，避免异步写入乱序 */
  let playChain = Promise.resolve()
  let playStarted = false
  let turnId = 0
  const t = { final: 0, sent: 0, firstText: 0 }

  function log(msg) {
    state.logs.unshift({ time: nowStr(), msg })
    if (state.logs.length > 80) state.logs.length = 80
    console.log('[standby]', msg)
  }

  function clearTimers() {
    clearTimeout(noSpeechTimer)
    clearTimeout(maxUtteranceTimer)
    noSpeechTimer = null
    maxUtteranceTimer = null
  }

  // ------------------------------------------------------------ 公共入口

  async function start(options) {
    if (state.phase !== 'off') return
    opts = options
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
      const res = await native.startWake(opts.keywords, opts.source)
      state.input = res?.input || ''
      state.note = res?.note || ''
      state.phase = 'standby'
      log(`待命已开始，麦克风：${state.input || '未知'}`)
    } catch (e) {
      state.error = e?.message || String(e)
      log(`启动失败：${state.error}`)
      await teardown()
    }
  }

  async function stop() {
    if (state.phase === 'off') return
    log('结束待命')
    await teardown()
  }

  /** 打断：停掉思考 / 播报；开了连续对话就直接转入聆听，否则回到待命 */
  async function interrupt() {
    if (state.phase !== 'thinking' && state.phase !== 'speaking') return
    log('已打断')
    await cancelTurn()
    if (opts?.continuous) await beginListening({ followUp: true })
    else await backToStandby()
  }

  // ------------------------------------------------------------ 原生事件

  async function attachListeners() {
    handles = await Promise.all([
      native.onWake((e) => onWake(e)),
      native.onAudio((e) => {
        if (state.phase !== 'listening' || !asr) return
        asr.sendAudio(native.base64ToBytes(e.pcm))
      }),
      native.onPlayEnd((e) => {
        if (state.phase === 'speaking' && !e.interrupted) afterSpeak()
      }),
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
    clearTimers()
    await cancelTurn()
    closeAsr()
    handles.forEach((h) => h?.remove?.())
    handles = []
    try {
      await native.endCapture()
    } catch {
      /* ignore */
    }
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
  }

  // ------------------------------------------------------------ 聆听 + 断句

  async function onWake(e) {
    if (state.phase === 'listening') return
    state.wakeCount = e.count || state.wakeCount + 1
    log(`唤醒：${e.keyword}`)
    // 思考 / 播报期间再次唤醒 = 语音打断
    if (state.phase === 'thinking' || state.phase === 'speaking') await cancelTurn()
    await beginListening({ followUp: false, captureAlreadyOn: true })
  }

  async function beginListening({ followUp, captureAlreadyOn = false }) {
    clearTimers()
    closeAsr()
    state.phase = 'listening'
    state.followUp = followUp
    state.partial = ''
    heardSpeech = false

    asr = new AsrClient({
      onReady: () => log('识别通道就绪'),
      onPartial: (text) => {
        heardSpeech = true
        state.partial = text
      },
      onFinal: (text) => onFinalSentence(text),
      onError: (msg) => {
        if (state.phase !== 'listening') return
        log(`识别出错：${msg}`)
        state.error = msg
        backToStandby()
      },
      onClose: () => {},
    })
    asr.open({ endWindowMs: opts.endWindowMs })

    try {
      if (!captureAlreadyOn) await native.beginCapture()
    } catch (e) {
      state.error = e?.message || String(e)
      await backToStandby()
      return
    }

    const waitSec = followUp ? opts.followUpSec : opts.noSpeechSec
    noSpeechTimer = setTimeout(() => {
      if (state.phase === 'listening' && !heardSpeech) {
        log(followUp ? '连续对话窗口内无人说话，回到待命' : '唤醒后没听到说话，回到待命')
        backToStandby()
      }
    }, waitSec * 1000)
    maxUtteranceTimer = setTimeout(() => {
      if (state.phase === 'listening') {
        log('单次说话超过上限，结束聆听')
        asr?.finish()
      }
    }, MAX_UTTERANCE_MS)
  }

  function onFinalSentence(text) {
    if (state.phase !== 'listening') return
    if (validChars(text) < MIN_VALID_CHARS) {
      log(`忽略过短的识别结果：「${text}」`)
      state.partial = ''
      return
    }
    t.final = performance.now()
    clearTimers()
    log(`断句：「${text}」`)
    state.partial = text
    closeAsr()
    native.endCapture().catch(() => {})
    sendToAgent(text)
  }

  function closeAsr() {
    if (asr) {
      asr.close()
      asr = null
    }
  }

  async function backToStandby() {
    clearTimers()
    closeAsr()
    try {
      await native.endCapture()
    } catch {
      /* ignore */
    }
    if (state.phase !== 'off') {
      state.phase = 'standby'
      state.followUp = false
      state.partial = ''
    }
  }

  // ------------------------------------------------------------ Agent + 合成播报

  async function sendToAgent(text) {
    const myTurn = ++turnId
    state.phase = 'thinking'
    state.sent.unshift({ time: nowStr(), text })
    state.reply = ''
    state.speaking = ''
    state.metrics = { endpointToSend: null, sendToFirstText: null, firstTextToFirstAudio: null }
    t.sent = performance.now()
    t.firstText = 0
    state.metrics.endpointToSend = Math.round(t.sent - t.final)
    playStarted = false
    playChain = Promise.resolve()
    abortCtl = new AbortController()

    splitter = createSentenceSplitter((sentence) => {
      if (myTurn !== turnId) return
      ensureTts()
      state.reply += sentence
      tts.sendText(sentence)
    })

    try {
      await streamAgentReply({
        message: text,
        userId: opts.userId,
        signal: abortCtl.signal,
        onDelta: (delta) => {
          if (myTurn !== turnId) return
          if (!t.firstText) {
            t.firstText = performance.now()
            state.metrics.sendToFirstText = Math.round(t.firstText - t.sent)
          }
          splitter.push(delta)
        },
      })
      if (myTurn !== turnId) return
      splitter.flush()
      if (tts) {
        tts.finish()
      } else {
        log('Agent 没有可朗读的文字回复')
        await afterSpeak()
      }
    } catch (e) {
      if (myTurn !== turnId || e?.name === 'AbortError') return
      log(`Agent 请求失败：${e?.message || e}`)
      state.error = e?.message || String(e)
      await cancelTurn()
      await backToStandby()
    }
  }

  function ensureTts() {
    if (tts) return
    const myTurn = turnId
    tts = new TtsClient({
      onReady: () => log('合成通道就绪'),
      onAudio: (buf) => {
        if (myTurn !== turnId) return
        const bytes = new Uint8Array(buf)
        playChain = playChain.then(async () => {
          if (myTurn !== turnId) return
          if (!playStarted) {
            playStarted = true
            await native.playStart(TTS_SAMPLE_RATE)
            state.phase = 'speaking'
            state.metrics.firstTextToFirstAudio = Math.round(performance.now() - t.firstText)
          }
          await native.playWrite(bytes)
        })
      },
      onSentenceStart: (s) => {
        if (myTurn === turnId) state.speaking = s
      },
      onDone: () => {
        if (myTurn !== turnId) return
        // 等已排队的音频都写进播放器，再告诉原生「没有更多了」
        playChain = playChain.then(async () => {
          if (myTurn !== turnId) return
          if (playStarted) await native.playFinish()
          else await afterSpeak()
        })
      },
      onCanceled: () => {},
      onError: async (msg) => {
        if (myTurn !== turnId) return
        log(`合成出错：${msg}`)
        state.error = msg
        await cancelTurn()
        await backToStandby()
      },
      onClose: () => {},
    })
    tts.open({ voice: opts.voice, speechRate: opts.speechRate })
  }

  /** 一轮播报结束（自然播完 / 没有可播内容） */
  async function afterSpeak() {
    if (state.phase === 'off') return
    turnId++
    closeTts()
    state.speaking = ''
    if (opts?.continuous && opts.followUpSec > 0) {
      log(`播报结束，继续听 ${opts.followUpSec} 秒`)
      await beginListening({ followUp: true })
    } else {
      await backToStandby()
    }
  }

  function closeTts() {
    if (tts) {
      tts.close()
      tts = null
    }
  }

  /** 作废当前这一轮：断开 Agent 流与合成，停止播放 */
  async function cancelTurn() {
    turnId++
    abortCtl?.abort()
    abortCtl = null
    splitter?.reset()
    if (tts) {
      tts.cancel()
      closeTts()
    }
    playChain = Promise.resolve()
    if (playStarted) {
      playStarted = false
      try {
        await native.playStop()
      } catch {
        /* ignore */
      }
    }
    state.speaking = ''
  }

  return { state, start, stop, interrupt }
}

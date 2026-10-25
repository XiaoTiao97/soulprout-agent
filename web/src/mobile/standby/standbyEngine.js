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
/** 连续聆听自动重连的频率保护：这段时间内重连超过 N 次就放弃，回到待命 */
const RESTART_WINDOW_MS = 15_000
const RESTART_MAX = 4
/** 输出音量按这个粒度（毫秒）切片 */
const OUT_LEVEL_STEP_MS = 60

const DEFAULT_OPTIONS = {
  source: 'auto',
  endWindowMs: 500,
  noSpeechSec: 4,
  continuous: false,
  bargeIn: true,
  speechRate: 0,
}
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
 * @property {boolean} bargeIn      播报期间保持待命，可用唤醒词打断（依赖回声消除）
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
    /** 播放输出音量 0-100（按播放进度对齐，给光感动效用） */
    outLevel: 0,
    /** 每次唤醒自增，界面据此触发一次「被唤醒」的动效 */
    wakePulse: 0,
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
  /** 本轮是否已经有句子送去合成（提前建通道时，没用到就不能当成「合成出错」处理） */
  let ttsUsed = false
  let turnId = 0
  /** 输出音量时间轴：播放起点与已排入的音频时长 */
  let outT0 = 0
  let outAcc = 0
  let restartTimes = []
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
    opts = { ...DEFAULT_OPTIONS, ...options }
    restartTimes = []
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
      const res = await native.startWake(opts.keywords, opts.source, !!opts.bargeIn)
      state.input = res?.input || ''
      state.note = res?.note || ''
      state.phase = 'standby'
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
    const prevContinuous = opts.continuous
    opts = { ...opts, ...partial }
    if (prevContinuous && !opts.continuous && state.phase === 'listening' && state.followUp) {
      log('连续对话已关闭，回到待命')
      await backToStandby()
    } else if (prevContinuous && !opts.continuous && (state.phase === 'thinking' || state.phase === 'speaking')) {
      // 本轮不再监听说话；之后靠唤醒词打断
      closeAsr()
      native.endCapture().catch(() => {})
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
        if (!asr || (state.phase !== 'listening' && !monitoring())) return
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
    state.wakePulse++
    log(`唤醒：${e.keyword}`)
    // 思考 / 播报期间再次唤醒 = 语音打断（播报中原生已先就地停掉了播放）
    if (state.phase === 'thinking' || state.phase === 'speaking') {
      log(e.interrupted ? '播报中被唤醒词打断' : '处理中被唤醒词打断')
      await cancelTurn()
    }
    await beginListening({ followUp: false, captureAlreadyOn: true })
  }

  /** 识别客户端：各阶段（聆听 / 连续对话里思考播报时的监听）共用同一套事件处理 */
  function newAsrClient() {
    const client = new AsrClient({
      onReady: () => log('识别通道就绪'),
      onPartial: (text) => {
        if (asr !== client) return
        // 连续对话里思考 / 播报时识别通道仍开着：听到人声就打断
        if (monitoring()) {
          maybeBargeIn(text)
          return
        }
        heardSpeech = true
        state.partial = text
      },
      onFinal: (text) => {
        if (asr === client) onFinalSentence(text)
      },
      onError: (msg) => {
        if (asr === client && monitoring()) {
          restartMonitor(`识别通道断开（${msg}）`)
          return
        }
        if (asr !== client || state.phase !== 'listening') return
        // 连续对话里还没人说话时，识别通道被服务端因空闲断开很正常，悄悄重连即可
        if (continuousIdle()) {
          restartContinuous(`识别通道断开（${msg}）`)
          return
        }
        log(`识别出错：${msg}`)
        state.error = msg
        backToStandby()
      },
      onEnd: () => {
        if (asr === client && monitoring()) {
          restartMonitor('识别已结束')
          return
        }
        if (asr !== client || state.phase !== 'listening') return
        if (opts.continuous && state.followUp) restartContinuous('识别已结束')
        else backToStandby()
      },
      onClose: () => {
        if (asr === client && monitoring()) {
          restartMonitor('识别通道关闭')
          return
        }
        if (asr !== client || state.phase !== 'listening') return
        if (continuousIdle()) restartContinuous('识别通道关闭')
      },
    })
    return client
  }

  async function beginListening({ followUp, captureAlreadyOn = false }) {
    clearTimers()
    closeAsr()
    state.phase = 'listening'
    state.followUp = followUp
    state.partial = ''
    heardSpeech = false

    const client = newAsrClient()
    asr = client
    client.open({ endWindowMs: opts.endWindowMs })

    try {
      if (!captureAlreadyOn) await native.beginCapture()
    } catch (e) {
      state.error = e?.message || String(e)
      await backToStandby()
      return
    }

    // 连续对话：没有等待窗口，一直听到用户说话或关掉开关；其余情况唤醒后只等 noSpeechSec 秒
    if (!(followUp && opts.continuous)) {
      noSpeechTimer = setTimeout(() => {
        if (state.phase === 'listening' && !heardSpeech) {
          log('唤醒后没听到说话，回到待命')
          backToStandby()
        }
      }, opts.noSpeechSec * 1000)
    }
    armMaxUtterance()
  }

  function armMaxUtterance() {
    clearTimeout(maxUtteranceTimer)
    maxUtteranceTimer = setTimeout(() => {
      if (state.phase !== 'listening') return
      if (continuousIdle()) {
        restartContinuous('单次聆听到时，重新开始')
        return
      }
      log('单次说话超过上限，结束聆听')
      asr?.finish()
    }, MAX_UTTERANCE_MS)
  }

  // ------------------------------------------------------------ 连续对话：说话打断

  /** 连续对话里，思考 / 播报期间识别通道一直开着，用来听用户是不是开口了 */
  function monitoring() {
    return !!(asr && opts?.continuous && (state.phase === 'thinking' || state.phase === 'speaking'))
  }

  /** 去掉标点空白，只留文字，用来比较 */
  function plain(text) {
    return (text || '').replace(/[\s\p{P}\p{S}]/gu, '')
  }

  function bigrams(s) {
    const out = new Set()
    for (let i = 0; i < s.length - 1; i++) out.add(s.slice(i, i + 2))
    return out
  }

  /**
   * 听到的内容是不是扬声器漏回麦克风的回声：回声消除再好也会残留一点，识别出来的字
   * 基本都在刚刚播的那段话里。和已播内容的双字重合度高，就当作回声，不打断。
   */
  function looksLikeEcho(text) {
    const heard = plain(text)
    const spoken = plain(state.reply)
    if (!spoken) return false
    if (heard.length < 2) return spoken.includes(heard)
    const hb = bigrams(heard)
    const sb = bigrams(spoken)
    let hit = 0
    for (const g of hb) if (sb.has(g)) hit++
    return hit / hb.size >= 0.6
  }

  let promoting = false

  async function maybeBargeIn(text) {
    if (promoting || !monitoring()) return
    if (validChars(text) < MIN_VALID_CHARS) return
    if (looksLikeEcho(text)) return
    promoting = true
    try {
      log(`听到说话，打断：「${text}」`)
      clearTimers()
      await cancelTurn()
      if (state.phase === 'off' || !asr) return
      // 沿用这条识别通道：已经识别到的内容接着往下听，断句后照常发给 Agent
      state.phase = 'listening'
      state.followUp = true
      heardSpeech = true
      state.partial = text
      state.wakePulse++
      armMaxUtterance()
    } finally {
      promoting = false
    }
  }

  /** 监听通道断了：重连，但不改变思考 / 播报状态 */
  function restartMonitor(reason) {
    const now = Date.now()
    restartTimes = restartTimes.filter((x) => now - x < RESTART_WINDOW_MS)
    closeAsr()
    if (restartTimes.length >= RESTART_MAX) {
      log('说话监听反复断开，本轮不再监听')
      return
    }
    restartTimes.push(now)
    log(`${reason}，重新建立说话监听`)
    openMonitor()
  }

  /** 思考 / 播报期间保持识别通道 */
  function openMonitor() {
    const client = newAsrClient()
    asr = client
    client.open({ endWindowMs: opts.endWindowMs })
  }

  /** 连续对话中、还没有人开口 */
  function continuousIdle() {
    return !!(opts.continuous && state.followUp && !heardSpeech)
  }

  /** 连续聆听里重新建立识别通道（原生采集不中断）；过于频繁说明有问题，退回待命 */
  async function restartContinuous(reason) {
    const now = Date.now()
    restartTimes = restartTimes.filter((x) => now - x < RESTART_WINDOW_MS)
    if (restartTimes.length >= RESTART_MAX) {
      log('连续聆听反复断开，回到待命')
      state.error = '识别通道反复断开'
      await backToStandby()
      return
    }
    restartTimes.push(now)
    log(`${reason}，重新连接继续听`)
    await beginListening({ followUp: true, captureAlreadyOn: true })
  }

  function onFinalSentence(text) {
    if (state.phase !== 'listening') return
    if (validChars(text) < MIN_VALID_CHARS) {
      log(`忽略过短的识别结果：「${text}」`)
      state.partial = ''
      heardSpeech = false
      return
    }
    t.final = performance.now()
    clearTimers()
    log(`断句：「${text}」`)
    state.partial = text
    if (opts.continuous) {
      // 连续对话：识别通道和采集都不关，思考 / 播报期间继续听，听到人声就打断
      sendToAgent(text)
    } else {
      closeAsr()
      native.endCapture().catch(() => {})
      sendToAgent(text)
    }
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
    ttsUsed = false
    playChain = Promise.resolve()
    abortCtl = new AbortController()

    splitter = createSentenceSplitter((sentence) => {
      if (myTurn !== turnId) return
      ttsUsed = true
      ensureTts()
      state.reply += sentence
      tts.sendText(sentence)
    })

    // 和请求 Agent 并行，提前把合成通道建好：等第一句出来时已经就绪，省掉建连的几百毫秒
    ensureTts()

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
      if (ttsUsed && tts) {
        tts.finish()
      } else {
        // 没有任何可朗读的文字：提前建好的合成通道用不上，直接收尾
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
    const openedAt = performance.now()
    const client = new TtsClient({
      onReady: () => log(`合成通道就绪（建连 ${Math.round(performance.now() - openedAt)} ms）`),
      onAudio: (buf) => {
        if (myTurn !== turnId) return
        const bytes = new Uint8Array(buf)
        enqueuePlay(myTurn, async () => {
          if (!playStarted) {
            playStarted = true
            await native.playStart(TTS_SAMPLE_RATE)
            outT0 = performance.now()
            outAcc = 0
            state.phase = 'speaking'
            state.metrics.firstTextToFirstAudio = Math.round(performance.now() - t.firstText)
          }
          scheduleOutLevel(myTurn, bytes)
          await native.playWrite(bytes)
        })
      },
      onSentenceStart: (s) => {
        if (myTurn === turnId) state.speaking = s
      },
      onDone: () => {
        if (myTurn !== turnId) return
        // 等已排队的音频都写进播放器，再告诉原生「没有更多了」
        enqueuePlay(myTurn, async () => {
          if (playStarted) await native.playFinish()
          else await afterSpeak()
        })
      },
      onCanceled: () => {},
      onError: async (msg) => {
        if (myTurn !== turnId || tts !== client) return
        if (!ttsUsed) {
          // 提前建的通道在等 Agent 期间出错 / 被断开：还没用到，丢掉，等第一句出来时重建
          log(`预建合成通道失效，稍后重连：${msg}`)
          closeTts()
          return
        }
        log(`合成出错：${msg}`)
        state.error = msg
        await cancelTurn()
        await backToStandby()
      },
      onClose: () => {
        if (tts === client && !ttsUsed) tts = null
      },
    })
    tts = client
    client.open({ voice: opts.voice, speechRate: opts.speechRate })
  }

  /**
   * 按播放进度给输出音量打点：TTS 返回比实时播放快，音频先到先排队，
   * 这里把每个 60ms 切片的响度延迟到它真正播放的时刻再写入 state.outLevel。
   */
  function scheduleOutLevel(myTurn, bytes) {
    const samples = bytes.length >> 1
    const step = Math.round((TTS_SAMPLE_RATE * OUT_LEVEL_STEP_MS) / 1000)
    const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength)
    for (let i = 0; i < samples; i += step) {
      const end = Math.min(samples, i + step)
      let sum = 0
      for (let j = i; j < end; j++) {
        const v = view.getInt16(j * 2, true) / 32768
        sum += v * v
      }
      const rms = Math.sqrt(sum / Math.max(1, end - i))
      const level = Math.min(100, Math.round(rms * 600))
      const delay = Math.max(0, outT0 + outAcc - performance.now())
      outAcc += ((end - i) * 1000) / TTS_SAMPLE_RATE
      setTimeout(() => {
        if (myTurn === turnId && playStarted) state.outLevel = level
      }, delay)
    }
  }

  /**
   * 把一步播放操作排进队列（保证顺序）。单步失败只记日志，不能让整条链报废，
   * 否则后面的 playFinish 被跳过，界面会一直停在「播报中」。
   */
  function enqueuePlay(myTurn, step) {
    playChain = playChain.then(async () => {
      if (myTurn !== turnId) return
      try {
        await step()
      } catch (e) {
        log(`播放出错：${e?.message || e}`)
      }
    })
  }

  /** 一轮播报结束（自然播完 / 没有可播内容） */
  async function afterSpeak() {
    if (state.phase === 'off') return
    turnId++
    closeTts()
    state.speaking = ''
    state.outLevel = 0
    if (opts?.continuous) {
      log('播报结束，连续对话继续听')
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
    state.outLevel = 0
  }

  return { state, start, stop, interrupt, updateOptions }
}

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
/** Agent 流这么久没有任何字节（服务端每 15 秒发一次心跳），视为断流 */
const AGENT_STALL_MS = 50_000
/** 语音通道（识别 / 合成）的应用层心跳：多久发一次 ping，多久没收到任何消息就判定连接已死 */
const VOICE_PING_INTERVAL_MS = 10_000
const VOICE_DEAD_MS = 30_000
/** 合成通道这么久没有收发，豆包那边的会话会被回收（Agent 查网页时很常见），下一句换新通道 */
const TTS_IDLE_REFRESH_MS = 8_000
/** 一轮里合成通道最多自动重建几次 */
const TTS_MAX_RECOVER = 2
/** 原生状态事件本应每秒一次，间隔超过这个值说明 WebView 被挂起 / 降频了，记一条日志留证 */
const JS_STALL_LOG_MS = 3_000
/** 连续聆听自动重连的频率保护：这段时间内重连超过 N 次就放弃，回到待命 */
const RESTART_WINDOW_MS = 15_000
const RESTART_MAX = 4
/** 输出音量按这个粒度（毫秒）切片 */
const OUT_LEVEL_STEP_MS = 60

const DEFAULT_OPTIONS = {
  source: 'auto',
  endWindowMs: 500,
  noSpeechSec: 4,
  continuous: true,
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
  // ---- 本轮 Agent / 合成的健康度（看门狗用）
  let agentRunning = false
  let agentStalled = false
  let lastAgentAt = 0
  /** 已送去合成、但还没有收到任何回应的句子；合成通道出问题时用它们在新通道上续播 */
  let unacked = []
  /** 送了文字后，等第一个回应的起始时间；0 = 没有在等 */
  /** 合成通道最近一次收发的时间 */
  let ttsIoAt = 0
  /** Agent 已说完，合成通道已发过 finish */
  let ttsFinishSent = false
  let ttsRecovers = 0
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
      lastTickAt = 0
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
        tick()
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
    document.removeEventListener('visibilitychange', onVisibility)
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
    if (state.phase === 'off' || state.phase === 'starting') return
    state.wakeCount = e.count || state.wakeCount + 1
    state.wakePulse++
    log(`唤醒：${e.keyword}`)
    // 唤醒事件是原生唤醒引擎发的，不依赖云端识别，在任何阶段都以它为准：
    // 此刻识别通道里已经收进去的内容就是「唤醒词本身」，不是指令，整段丢掉，
    // 从唤醒之后的音频重新开一轮识别。连续对话里采集一直开着，这一步才能保证
    // 唤醒词不会被当成指令发给 Agent，通道卡住时也能靠唤醒词恢复。
    if (state.phase === 'listening') {
      log('聆听中被唤醒词重置，丢弃唤醒词本身的识别内容')
    } else if (state.phase === 'thinking' || state.phase === 'speaking') {
      // 思考 / 播报期间再次唤醒 = 语音打断（播报中原生已先就地停掉了播放）
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
        // 通道被直接掐断（没有 end 事件）。以前只有「还没人开口」才会重连，用户说到一半断开就会
        // 一直停在聆听里，唤醒词也不再处理。现在不管有没有开口，都重连或回到待命。
        if (opts.continuous && state.followUp) restartContinuous('识别通道关闭')
        else if (continuousIdle()) restartContinuous('识别通道关闭')
        else backToStandby()
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

  /** 思考期间的浅背景音。失败不影响对话本身。 */
  async function startThinkingBed() {
    try {
      await native.thinkStart()
    } catch {
      /* 背景音失败不影响对话 */
    }
  }

  async function stopThinkingBed() {
    try {
      await native.thinkStop()
    } catch {
      /* ignore */
    }
  }

  async function sendToAgent(text) {
    const myTurn = ++turnId
    state.phase = 'thinking'
    await startThinkingBed()
    state.sent.unshift({ time: nowStr(), text })
    state.reply = ''
    state.speaking = ''
    state.metrics = { endpointToSend: null, sendToFirstText: null, firstTextToFirstAudio: null }
    t.sent = performance.now()
    t.firstText = 0
    state.metrics.endpointToSend = Math.round(t.sent - t.final)
    playStarted = false
    ttsUsed = false
    unacked = []
    ttsFinishSent = false
    ttsRecovers = 0
    agentStalled = false
    agentRunning = true
    lastAgentAt = Date.now()
    playChain = Promise.resolve()
    abortCtl = new AbortController()

    splitter = createSentenceSplitter((sentence) => {
      if (myTurn !== turnId) return
      state.reply += sentence
      // Agent 先去查网页、隔了很久才出下一句时，合成会话多半已被服务端回收；
      // 往死通道里发字不会报错，只会永远没声音。闲置太久就先换一条新通道。
      if (tts && Date.now() - ttsIoAt > TTS_IDLE_REFRESH_MS) {
        log(`合成通道闲置 ${Math.round((Date.now() - ttsIoAt) / 1000)} 秒，换新通道`)
        reopenTts()
      }
      ttsUsed = true
      ensureTts()
      unacked.push(sentence)
      ttsIoAt = Date.now()
      tts.sendText(sentence)
    })

    // 和请求 Agent 并行，提前把合成通道建好：等第一句出来时已经就绪，省掉建连的几百毫秒
    ensureTts()

    try {
      await streamAgentReply({
        message: text,
        userId: opts.userId,
        signal: abortCtl.signal,
        onActivity: () => {
          if (myTurn === turnId) lastAgentAt = Date.now()
        },
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
      agentRunning = false
      splitter.flush()
      if (ttsUsed && tts) {
        ttsFinishSent = true
        ttsIoAt = Date.now()
        tts.finish()
      } else {
        // 没有任何可朗读的文字：提前建好的合成通道用不上，直接收尾
        log('Agent 没有可朗读的文字回复')
        await afterSpeak()
      }
    } catch (e) {
      if (myTurn !== turnId) return
      if (e?.name === 'AbortError' && !agentStalled) return
      agentRunning = false
      const msg = agentStalled ? 'Agent 连接中断（长时间没有数据，可能是息屏 / 切换网络导致）' : e?.message || String(e)
      log(`Agent 请求失败：${msg}`)
      state.error = msg
      await cancelTurn()
      await backToStandby()
    } finally {
      if (myTurn === turnId) agentRunning = false
    }
  }

  /**
   * 合成通道坏了（服务端回收 / 断网 / 无响应）：在新通道上把还没得到回应的句子补发，
   * 已经说完的 Agent 回复也要补发 finish，这样本轮才能正常收尾，而不是静默卡住。
   */
  function reopenTts() {
    const resend = unacked.slice()
    closeTts()
    ensureTts()
    ttsIoAt = Date.now()
    for (const s of resend) tts.sendText(s)
    if (ttsFinishSent) tts.finish()
  }

  function recoverTts(reason) {
    if (!ttsUsed) return
    if (ttsRecovers >= TTS_MAX_RECOVER) {
      log(`合成通道反复出错（${reason}），放弃本轮播报`)
      state.error = reason
      cancelTurn().then(() => backToStandby())
      return
    }
    ttsRecovers++
    log(`合成通道异常（${reason}），重建并续播（第 ${ttsRecovers} 次）`)
    reopenTts()
  }

  function ensureTts() {
    if (tts) return
    const myTurn = turnId
    const openedAt = performance.now()
    const client = new TtsClient({
      onReady: () => {
        if (tts === client) ttsIoAt = Date.now()
        log(`合成通道就绪（建连 ${Math.round(performance.now() - openedAt)} ms）`)
      },
      onAudio: (buf) => {
        if (myTurn !== turnId || tts !== client) return
        ttsIoAt = Date.now()
        const bytes = new Uint8Array(buf)
        enqueuePlay(myTurn, async () => {
          if (!playStarted) {
            playStarted = true
            await stopThinkingBed()
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
        if (myTurn !== turnId || tts !== client) return
        ttsIoAt = Date.now()
        // 这一句已经有回应，不用在换通道时补发
        unacked.shift()
        state.speaking = s
      },
      onDone: () => {
        if (myTurn !== turnId || tts !== client) return
        client.doneSeen = true
        // 等已排队的音频都写进播放器，再告诉原生「没有更多了」
        enqueuePlay(myTurn, async () => {
          if (playStarted) await native.playFinish()
          else await afterSpeak()
        })
      },
      onCanceled: () => {},
      onError: (msg) => {
        if (myTurn !== turnId || tts !== client || client.doneSeen) return
        if (!ttsUsed) {
          // 提前建的通道在等 Agent 期间出错 / 被断开：还没用到，丢掉，等第一句出来时重建
          log(`预建合成通道失效，稍后重连：${msg}`)
          closeTts()
          return
        }
        recoverTts(msg)
      },
      onClose: () => {
        if (myTurn !== turnId || tts !== client || client.doneSeen) return
        if (!ttsUsed) tts = null
        // 已经在用却被关了（没有 error 事件的静默断开）：以前这里什么都不做，
        // 之后的文字和 finish 都被丢弃，界面就一直停在「思考 / 播报」里。
        else recoverTts('合成通道被关闭')
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
    await stopThinkingBed()
    if (state.phase === 'off') return
    turnId++
    agentRunning = false
    unacked = []
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
    await stopThinkingBed()
    turnId++
    agentRunning = false
    unacked = []
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

  // ------------------------------------------------------------ 看门狗

  /**
   * 后台 / 息屏时的连接保活与存活检查。由原生状态事件（原生线程每秒一次）驱动，
   * 不用 JS 定时器：WebView 隐藏后 JS 定时器会被降频到每秒甚至每分钟一次，
   * 而原生事件的节奏不受影响。
   *
   * 根因：息屏后手机的无线电进入省电、运营商 / 路由器的 NAT 会回收长时间没有数据的连接，
   * TCP 连接就变成「两头都以为还连着」的半死状态——不报错、不关闭，往里发数据像石沉大海。
   * 浏览器 WebSocket 发不了协议层 ping，所以语音通道在应用层互发 ping / pong：
   *   1. 周期性的小包让连接保持活跃；
   *   2. 一旦超时没有回应，就能确认连接已死，立刻走重连，而不是静默卡住。
   */
  function onVisibility() {
    log(`页面${document.visibilityState === 'hidden' ? '进入后台 / 息屏' : '回到前台'}`)
  }

  let lastTickAt = 0
  function tick() {
    const now = Date.now()
    if (lastTickAt && now - lastTickAt > JS_STALL_LOG_MS) {
      log(`JS 事件停顿了 ${Math.round((now - lastTickAt) / 1000)} 秒（WebView 被系统挂起或降频）`)
    }
    lastTickAt = now
    if (state.phase === 'off' || state.phase === 'starting') return
    for (const c of [asr, tts]) {
      if (!c || c.closed) continue
      c.heartbeat(now, VOICE_PING_INTERVAL_MS, VOICE_DEAD_MS)
    }
    // Agent 流：服务端每 15 秒发一次心跳，连心跳都没有了，说明连接已断
    if (agentRunning && abortCtl && now - lastAgentAt > AGENT_STALL_MS) {
      log(`Agent 连接 ${Math.round((now - lastAgentAt) / 1000)} 秒没有任何数据，判定断流`)
      agentStalled = true
      abortCtl.abort()
    }
  }

  return { state, start, stop, interrupt, updateOptions }
}

/**
 * 待命语音通道的 WebSocket 客户端（对接后端 /api/voice/asr 与 /api/voice/tts）。
 * 后端再代理到豆包流式识别 / 双向流式合成，密钥不出后端。
 */
import { getToken, resolveApi } from '../api'

function wsUrl(path, params = {}) {
  const resolved = resolveApi(path)
  let base = resolved
  if (!/^https?:/i.test(resolved)) base = window.location.origin + resolved
  base = base.replace(/^http/i, 'ws')
  const qs = new URLSearchParams({ token: getToken(), ...params })
  return `${base}?${qs.toString()}`
}

/** 连接建立前最多缓存的音频包数（200ms 一包，约 10 秒） */
const MAX_PENDING_AUDIO = 50

/**
 * 流式识别。
 * handlers: onReady, onPartial(text), onFinal(text), onError(message), onEnd(), onClose()
 */
export class AsrClient {
  constructor(handlers = {}) {
    this.h = handlers
    this.ws = null
    this.ready = false
    this.closed = false
    this.pending = []
    this.finishRequested = false
  }

  open({ endWindowMs = 800 } = {}) {
    this.ws = new WebSocket(wsUrl('/api/voice/asr', { end_window_ms: String(endWindowMs) }))
    this.ws.binaryType = 'arraybuffer'
    this.ws.onmessage = (e) => {
      if (typeof e.data !== 'string') return
      let ev
      try {
        ev = JSON.parse(e.data)
      } catch {
        return
      }
      if (ev.type === 'ready') {
        this.ready = true
        for (const chunk of this.pending) this.ws.send(chunk)
        this.pending = []
        if (this.finishRequested) this.ws.send(JSON.stringify({ type: 'finish' }))
        this.h.onReady?.(ev)
      } else if (ev.type === 'partial') this.h.onPartial?.(ev.text || '')
      else if (ev.type === 'final') this.h.onFinal?.(ev.text || '')
      else if (ev.type === 'error') this.h.onError?.(ev.message || '识别服务出错')
      else if (ev.type === 'end') this.h.onEnd?.()
    }
    this.ws.onerror = () => this.h.onError?.('识别通道连接失败')
    this.ws.onclose = () => {
      this.closed = true
      this.h.onClose?.()
    }
  }

  /** @param {Uint8Array} bytes 16k / 16bit / 单声道 PCM */
  sendAudio(bytes) {
    if (this.closed || !this.ws) return
    if (this.ready) {
      if (this.ws.readyState === WebSocket.OPEN) this.ws.send(bytes)
      return
    }
    this.pending.push(bytes)
    if (this.pending.length > MAX_PENDING_AUDIO) this.pending.shift()
  }

  /** 告诉服务端音频结束，让它把没判停的内容收尾 */
  finish() {
    this.finishRequested = true
    if (this.ready && this.ws?.readyState === WebSocket.OPEN) this.ws.send(JSON.stringify({ type: 'finish' }))
  }

  close() {
    this.closed = true
    this.pending = []
    try {
      this.ws?.close()
    } catch {
      /* ignore */
    }
  }
}

/**
 * 双向流式合成。
 * handlers: onReady, onAudio(ArrayBuffer), onSentenceStart(text), onDone(), onCanceled(), onError(message), onClose()
 */
export class TtsClient {
  constructor(handlers = {}) {
    this.h = handlers
    this.ws = null
    this.ready = false
    this.closed = false
    this.queue = []
  }

  open({ voice = '', speechRate = 0 } = {}) {
    const params = { speech_rate: String(speechRate) }
    if (voice) params.voice = voice
    this.ws = new WebSocket(wsUrl('/api/voice/tts', params))
    this.ws.binaryType = 'arraybuffer'
    this.ws.onmessage = (e) => {
      if (typeof e.data !== 'string') {
        this.h.onAudio?.(e.data)
        return
      }
      let ev
      try {
        ev = JSON.parse(e.data)
      } catch {
        return
      }
      if (ev.type === 'ready') {
        this.ready = true
        for (const m of this.queue) this.ws.send(m)
        this.queue = []
        this.h.onReady?.()
      } else if (ev.type === 'sentence_start') this.h.onSentenceStart?.(ev.text || '')
      else if (ev.type === 'done') this.h.onDone?.()
      else if (ev.type === 'canceled') this.h.onCanceled?.()
      else if (ev.type === 'error') this.h.onError?.(ev.message || '合成服务出错')
    }
    this.ws.onerror = () => this.h.onError?.('合成通道连接失败')
    this.ws.onclose = () => {
      this.closed = true
      this.h.onClose?.()
    }
  }

  _send(obj) {
    if (this.closed || !this.ws) return
    const msg = JSON.stringify(obj)
    if (this.ready && this.ws.readyState === WebSocket.OPEN) this.ws.send(msg)
    else this.queue.push(msg)
  }

  sendText(text) {
    if (text && text.trim()) this._send({ type: 'text', text })
  }

  finish() {
    this._send({ type: 'finish' })
  }

  cancel() {
    // 取消不排队：连接还没好就直接关掉
    if (this.ready && this.ws?.readyState === WebSocket.OPEN) this.ws.send(JSON.stringify({ type: 'cancel' }))
    else this.close()
  }

  close() {
    this.closed = true
    this.queue = []
    try {
      this.ws?.close()
    } catch {
      /* ignore */
    }
  }
}

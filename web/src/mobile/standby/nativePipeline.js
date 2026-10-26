/**
 * 把待命对话的识别 / Agent / 合成地址交给原生。
 * 密钥仍在后端；这里只传用户登录 token 与自家 API 地址。
 */
import { getToken, resolveApi } from '../api'
import * as native from './standbyNative'

function absHttp(path) {
  const resolved = resolveApi(path)
  if (/^https?:/i.test(resolved)) return resolved
  return window.location.origin + resolved
}

function absWs(path, params = {}) {
  let base = absHttp(path).replace(/^http/i, 'ws')
  const qs = new URLSearchParams(params)
  return `${base}?${qs.toString()}`
}

/**
 * @param {object} opts
 * @param {string} opts.userId
 * @param {boolean} [opts.continuous]
 * @param {string} [opts.voice]
 * @param {number} [opts.speechRate]
 * @param {number} [opts.endWindowMs]
 */
export async function configureNativePipeline(opts) {
  const token = getToken()
  const endWindowMs = Number(opts.endWindowMs) || 500
  const speechRate = Number(opts.speechRate) || 0
  const voice = opts.voice || 'female'
  const ttsParams = { token, speech_rate: String(speechRate) }
  if (voice) ttsParams.voice = voice

  await native.configurePipeline({
    asrUrl: absWs('/api/voice/asr', { token, end_window_ms: String(endWindowMs) }),
    ttsUrl: absWs('/api/voice/tts', ttsParams),
    chatUrl: absHttp('/api/message/chat'),
    token,
    userId: String(opts.userId || ''),
    continuous: !!opts.continuous,
    voice,
    speechRate,
  })
}

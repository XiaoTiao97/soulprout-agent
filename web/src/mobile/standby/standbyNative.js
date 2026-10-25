/**
 * 待命（Standby）原生能力封装。
 *  - WakeWord 插件：麦克风 + 离线唤醒 + 采集上送 + AudioTrack 播放
 *  - Standby 插件：前台服务、权限状态、设置页跳转
 * 只在 Capacitor 原生环境可用。
 */
import { Capacitor, registerPlugin } from '@capacitor/core'
import { WakeWordPlugin as WakeWord } from '../wake/wakeWord'

const Standby = registerPlugin('Standby')

export function isStandbySupported() {
  return (
    Capacitor.isNativePlatform() && Capacitor.isPluginAvailable('WakeWord') && Capacitor.isPluginAvailable('Standby')
  )
}

// ---------------------------------------------------------------- base64 <-> bytes

export function base64ToBytes(b64) {
  const bin = atob(b64)
  const out = new Uint8Array(bin.length)
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i)
  return out
}

export function bytesToBase64(bytes) {
  const u8 = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes)
  let bin = ''
  const step = 0x8000
  for (let i = 0; i < u8.length; i += step) {
    bin += String.fromCharCode.apply(null, u8.subarray(i, i + step))
  }
  return btoa(bin)
}

// ---------------------------------------------------------------- 唤醒 / 采集 / 播放

export const startWake = (keywords, source = 'auto', bargeIn = false) =>
  WakeWord.start({ keywords, source, bargeIn })
export const stopWake = () => WakeWord.stop()
export const beginCapture = () => WakeWord.beginCapture()
export const endCapture = () => WakeWord.endCapture()

export const playStart = (sampleRate = 24000) => WakeWord.playStart({ sampleRate })
/** @param {Uint8Array|ArrayBuffer} pcm 16bit 小端单声道 */
export const playWrite = (pcm) => WakeWord.playWrite({ pcm: bytesToBase64(pcm) })
export const playFinish = () => WakeWord.playFinish()
export const playStop = () => WakeWord.playStop()

export const onWake = (cb) => WakeWord.addListener('wake', cb)
/** { pcm: base64 的 200ms PCM16 16k 单声道, seq } */
export const onAudio = (cb) => WakeWord.addListener('audio', cb)
export const onPlayEnd = (cb) => WakeWord.addListener('playEnd', cb)
export const onLevel = (cb) => WakeWord.addListener('level', cb)
export const onStatus = (cb) => WakeWord.addListener('status', cb)
export const onNativeError = (cb) => WakeWord.addListener('error', cb)

// ---------------------------------------------------------------- 常驻 / 权限

export const getStandbyStatus = () => Standby.getStatus()
export const requestStandbyPermissions = () => Standby.requestPermissions()
export const startStandbyService = (opts) => Standby.startService(opts)
export const stopStandbyService = () => Standby.stopService()
/** @param {'app'|'notification'|'battery'|'autostart'} target */
export const openStandbySettings = (target) => Standby.openSettings({ target })
export const onServiceStopped = (cb) => Standby.addListener('serviceStopped', cb)

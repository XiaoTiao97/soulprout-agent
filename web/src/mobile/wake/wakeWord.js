/**
 * 原生唤醒词插件（android/app/src/main/java/com/soulprout/agent/WakeWordPlugin.java）的 JS 封装。
 * 只有在 Capacitor 原生环境下才可用，浏览器里 isWakeSupported() 为 false。
 */
import { Capacitor, registerPlugin } from '@capacitor/core'

const WakeWord = registerPlugin('WakeWord')

/** 待命模块直接用同一个插件实例（采集 / 播放等扩展方法） */
export const WakeWordPlugin = WakeWord

export function isWakeSupported() {
  return Capacitor.isNativePlatform() && Capacitor.isPluginAvailable('WakeWord')
}

/**
 * @param {string} keywords 一行或多行（用 / 分隔）关键词，见 ppinyin.js 的 buildKeywordLine
 * @param {'auto'|'phone'} [source] auto=有蓝牙耳机就用耳机麦克风；phone=始终用手机麦克风
 * @returns {Promise<{input: string, bluetooth: boolean, note: string}>} 实际使用的麦克风
 */
export function startWake(keywords, source = 'auto') {
  return WakeWord.start({ keywords, source })
}

export function stopWake() {
  return WakeWord.stop()
}

/** @returns {Promise<{remove: () => Promise<void>}>} */
export function onWake(cb) {
  return WakeWord.addListener('wake', cb)
}

export function onWakeStatus(cb) {
  return WakeWord.addListener('status', cb)
}

/** 音量，每 200ms 一次：{ peakDb, rmsDb, level(0-100) } */
export function onWakeLevel(cb) {
  return WakeWord.addListener('level', cb)
}

export function onWakeError(cb) {
  return WakeWord.addListener('error', cb)
}

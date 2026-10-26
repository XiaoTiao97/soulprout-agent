/**
 * 待命（Standby）原生能力封装。
 *  - WakeWord 插件：麦克风 + 离线唤醒 + 全原生对话管线
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

// ---------------------------------------------------------------- 唤醒

export const startWake = (keywords, source = 'auto', bargeIn = false) =>
  WakeWord.start({ keywords, source, bargeIn })
export const stopWake = () => WakeWord.stop()

export const onWake = (cb) => WakeWord.addListener('wake', cb)
export const onLevel = (cb) => WakeWord.addListener('level', cb)
export const onStatus = (cb) => WakeWord.addListener('status', cb)
export const onNativeError = (cb) => WakeWord.addListener('error', cb)

// ---------------------------------------------------------------- 全原生对话管线

export const configurePipeline = (opts) => WakeWord.configurePipeline(opts)
export const setPipelineContinuous = (continuous) => WakeWord.setPipelineContinuous({ continuous: !!continuous })
export const pipelineInterrupt = () => WakeWord.pipelineInterrupt()
/** { phase, key, value } — 仅供界面；对话本身不依赖这些事件 */
export const onPipeline = (cb) => WakeWord.addListener('pipeline', cb)

// ---------------------------------------------------------------- 常驻 / 权限

export const getStandbyStatus = () => Standby.getStatus()
export const requestStandbyPermissions = () => Standby.requestPermissions()
export const startStandbyService = (opts) => Standby.startService(opts)
export const stopStandbyService = () => Standby.stopService()
/** 写入 Android logcat（tag=Yavis），供电脑 adb 调试 */
export const debugLog = (message) => Standby.debugLog({ message: String(message || '') })
/** @param {'app'|'notification'|'battery'|'batteryList'|'autostart'} target */
export const openStandbySettings = (target) => Standby.openSettings({ target })
export const onServiceStopped = (cb) => Standby.addListener('serviceStopped', cb)

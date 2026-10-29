// 与本机 sidecar（/__desktop/*）和 Tauri 窗口的小封装。

async function request(method, url, body) {
  const resp = await fetch(url, {
    method,
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
    credentials: 'same-origin',
  })
  let data = null
  try {
    data = await resp.json()
  } catch {
    /* 非 JSON 响应 */
  }
  if (!resp.ok) {
    const err = new Error((data && (data.message || data.detail || data.error)) || `HTTP ${resp.status}`)
    err.status = resp.status
    throw err
  }
  return data
}

export const getState = () => request('GET', '/__desktop/state')

export const OFFICIAL_CLOUD_URL = 'https://www.soulprout.com'
export const OFFICIAL_DOCS_URL = `${OFFICIAL_CLOUD_URL}/docs`

function normUrl(value) {
  return String(value || '').replace(/\/+$/, '').toLowerCase()
}

function isLocalHostUrl(value) {
  return /^(https?:\/\/)?(127\.0\.0\.1|localhost)(:|\/|$)/i.test(String(value || ''))
}

/** 官方云服务域名。接口若误把 localhost 当成默认值，这里仍回落到官网。 */
export function officialCloudUrl(cloud) {
  const reported = String(cloud?.default_url || '').trim().replace(/\/+$/, '')
  if (reported && !isLocalHostUrl(reported)) return reported
  return OFFICIAL_CLOUD_URL
}

/** 当前连的是自定义/本地服务，而不是官方云服务。 */
export function isCustomCloud(cloud) {
  if (!cloud) return false
  return normUrl(cloud.url) !== normUrl(officialCloudUrl(cloud))
}

export const setPreset = (preset) => request('POST', '/__desktop/policy', { preset })
export const decideApproval = (id, decision) => request('POST', `/__desktop/approvals/${encodeURIComponent(id)}`, { decision })
export const openWorkspaceFolder = () => request('POST', '/__desktop/open-folder', {})

/** 用系统默认浏览器打开官网产品文档。 */
export async function openOfficialDocs() {
  const url = OFFICIAL_DOCS_URL
  try {
    if (window.__TAURI__?.shell?.open) {
      await window.__TAURI__.shell.open(url)
      return
    }
  } catch {
    /* 没有 shell 权限时走 sidecar */
  }
  try {
    await request('POST', '/__desktop/open-url', { url })
  } catch {
    window.open(url, '_blank', 'noopener,noreferrer')
  }
}
export const setCloudUrl = (url) => request('POST', '/__desktop/cloud', { url })
export const testCloudUrl = (url) => request('POST', '/__desktop/cloud/test', { url })

/** 多端互联（gateway）的接口：由 sidecar 转发到本机 gateway，只开放渠道相关的路径。 */
export const gateway = {
  get: (path) => request('GET', `/__gateway/${path}`),
  post: (path, body) => request('POST', `/__gateway/${path}`, body === undefined ? {} : body),
}

/**
 * 订阅「需要用户批准」的事件。EventSource 断线会自动重连，重连时 sidecar 会把仍待决的请求重发一遍。
 * 返回取消订阅的函数。
 */
export function subscribeApprovals(onEvent) {
  const source = new EventSource('/__desktop/approvals/stream')
  source.onmessage = (event) => {
    try {
      onEvent(JSON.parse(event.data))
    } catch {
      /* 忽略坏帧 */
    }
  }
  return () => source.close()
}

// ---- 窗口控制（Tauri）。没有 Tauri（比如在浏览器里调试）时都是空操作。

function currentWindow() {
  const tauri = window.__TAURI__
  try {
    return tauri?.window?.getCurrentWindow?.() ?? null
  } catch {
    return null
  }
}

export const hasNativeWindow = () => currentWindow() !== null
export const minimizeWindow = () => currentWindow()?.minimize()
export const toggleMaximizeWindow = () => currentWindow()?.toggleMaximize()
export const closeWindow = () => currentWindow()?.close()
export const isWindowMaximized = async () => (await currentWindow()?.isMaximized()) ?? false

export async function onWindowResized(callback) {
  const win = currentWindow()
  if (!win?.onResized) return () => {}
  return win.onResized(callback)
}

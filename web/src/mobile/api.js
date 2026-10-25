import axios from 'axios'

/**
 * 为空时走 Vite 代理（开发：/api → 本机 8080）。
 * 打包进安卓时设成官网域名（见 .env.mobile），请求形如 https://www.soulprout.com/api/...，
 * 与网页端一样由线上反向代理去掉 /api 前缀。
 */
const origin = (import.meta.env.VITE_API_ORIGIN || '').replace(/\/$/, '')

const TOKEN_KEY = 'soulprout_token'

/**
 * 手机 App 跨域访问官网，WebView 里 Cookie 不可靠，所以登录后把 token 存下来，
 * 之后每个请求用 Authorization: Bearer 带上（后端同时认 Cookie 和 Bearer）。
 */
export function getToken() {
  return localStorage.getItem(TOKEN_KEY) || ''
}

export function setToken(token) {
  if (token) localStorage.setItem(TOKEN_KEY, token)
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY)
}

export function resolveApi(path) {
  if (!origin || typeof path !== 'string' || !path.startsWith('/api')) return path
  return origin + path
}

function withAuthHeaders(headers) {
  const next = new Headers(headers || {})
  // Cache-Control 不在服务端放行的请求头里，带上会导致预检失败。
  // 不走缓存由 fetch 的 cache: 'no-store' 负责。
  next.delete('Cache-Control')
  const token = getToken()
  if (token && !next.has('Authorization')) next.set('Authorization', `Bearer ${token}`)
  return next
}

/** 跨域访问官网时不能带 Cookie。后端未开 credentials，带上会被浏览器直接丢弃。 */
function crossOriginInit(options = {}) {
  return { ...options, headers: withAuthHeaders(options.headers), credentials: 'omit' }
}

export const http = axios.create()

http.interceptors.request.use((config) => {
  if (typeof config.url === 'string') {
    config.url = resolveApi(config.url)
  }
  const token = getToken()
  if (token) config.headers.set('Authorization', `Bearer ${token}`)
  return config
})

export function apiFetch(path, options = {}) {
  return fetch(resolveApi(path), crossOriginInit(options))
}

/** 只在安卓入口调用。让聊天组件里写死的 /api 请求（axios 与 fetch）在直连服务器时也能用。 */
export function installMobileApiShim() {
  axios.interceptors.request.use((config) => {
    if (typeof config.url === 'string') config.url = resolveApi(config.url)
    const token = getToken()
    if (token) config.headers.set('Authorization', `Bearer ${token}`)
    return config
  })

  const nativeFetch = window.fetch.bind(window)
  window.fetch = (input, init) => {
    if (typeof input === 'string' && input.startsWith('/api')) {
      return nativeFetch(resolveApi(input), crossOriginInit(init || {}))
    }
    return nativeFetch(input, init)
  }
}

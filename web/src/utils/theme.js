import { ref, computed } from 'vue'

export const THEME_STORAGE_KEY = 'soulprout-theme-mode'

/**
 * 支持的主题模式：
 * - 'system': 跟随系统（默认）
 * - 'light':  白天模式
 * - 'dark':   夜晚模式
 */
export const VALID_THEME_MODES = ['system', 'light', 'dark']

function readStoredThemeMode() {
  if (typeof window === 'undefined') return 'system'
  try {
    const raw = window.localStorage.getItem(THEME_STORAGE_KEY)
    if (raw && VALID_THEME_MODES.includes(raw)) {
      return raw
    }
  } catch {
    // ignore storage errors
  }
  return 'system'
}

function getSystemTheme() {
  if (typeof window === 'undefined' || !window.matchMedia) return 'light'
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

export const themeMode = ref(readStoredThemeMode())
export const systemTheme = ref(getSystemTheme())

export const resolvedTheme = computed(() => {
  return themeMode.value === 'system' ? systemTheme.value : themeMode.value
})

export const isDark = computed(() => resolvedTheme.value === 'dark')

export function applyThemeToDom() {
  if (typeof document === 'undefined') return
  const root = document.documentElement
  const current = resolvedTheme.value
  root.setAttribute('data-theme', current)
  root.setAttribute('data-theme-mode', themeMode.value)
  root.classList.toggle('dark', current === 'dark')
  root.style.colorScheme = current
  const metaTheme = document.querySelector('meta[name="theme-color"]')
  if (metaTheme) {
    metaTheme.setAttribute('content', current === 'dark' ? '#171717' : '#f2f2f2')
  }
}

export function setThemeMode(mode) {
  const next = VALID_THEME_MODES.includes(mode) ? mode : 'system'
  themeMode.value = next
  if (typeof window !== 'undefined') {
    try {
      window.localStorage.setItem(THEME_STORAGE_KEY, next)
    } catch {
      // ignore storage errors
    }
  }
  applyThemeToDom()
}

export function cycleThemeMode() {
  const order = ['system', 'light', 'dark']
  const idx = order.indexOf(themeMode.value)
  const next = order[(idx + 1) % order.length]
  setThemeMode(next)
  return next
}

let initialized = false

export function initTheme() {
  if (typeof window === 'undefined') return
  systemTheme.value = getSystemTheme()
  themeMode.value = readStoredThemeMode()
  applyThemeToDom()

  if (initialized) return
  initialized = true

  if (window.matchMedia) {
    const mq = window.matchMedia('(prefers-color-scheme: dark)')
    const handleChange = (e) => {
      systemTheme.value = e.matches ? 'dark' : 'light'
      if (themeMode.value === 'system') {
        applyThemeToDom()
      }
    }
    if (typeof mq.addEventListener === 'function') {
      mq.addEventListener('change', handleChange)
    } else if (typeof mq.addListener === 'function') {
      mq.addListener(handleChange)
    }
  }

  window.addEventListener('storage', (e) => {
    if (e.key === THEME_STORAGE_KEY) {
      const next = e.newValue && VALID_THEME_MODES.includes(e.newValue) ? e.newValue : 'system'
      themeMode.value = next
      applyThemeToDom()
    }
  })
}

// 模块加载时立即初始化，避免首屏闪烁
initTheme()

const SUPPORTED = ['zh-CN', 'en']
const STORAGE_KEY = 'locale'

export function detectDefaultLocale() {
  const saved = localStorage.getItem(STORAGE_KEY)
  if (saved && SUPPORTED.includes(saved)) return saved

  const lang = (navigator.language || 'en').toLowerCase()
  if (lang.startsWith('zh')) return 'zh-CN'
  return 'en'
}

export function persistLocale(locale) {
  localStorage.setItem(STORAGE_KEY, locale)
}

export { SUPPORTED, STORAGE_KEY }

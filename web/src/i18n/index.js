import { createI18n } from 'vue-i18n'
import zhCN from '../locales/zh-CN.js'
import en from '../locales/en.js'
import { detectDefaultLocale, persistLocale } from '../utils/detectLocale.js'

function htmlLang(locale) {
  return locale === 'zh-CN' ? 'zh-CN' : 'en'
}

const i18n = createI18n({
  legacy: false,
  locale: detectDefaultLocale(),
  fallbackLocale: 'en',
  messages: {
    'zh-CN': zhCN,
    en,
  },
})

document.documentElement.lang = htmlLang(i18n.global.locale.value)

export function setLocale(locale) {
  i18n.global.locale.value = locale
  persistLocale(locale)
  document.documentElement.lang = htmlLang(locale)
}

export default i18n

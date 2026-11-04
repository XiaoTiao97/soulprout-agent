import { createApp } from 'vue'
import App from './App.vue'
import i18n from '@/i18n'
import { initTheme } from '@/utils/theme.js'
import { installMobileApiShim } from './api'
import './mobile.css'
import '@/assets/css/dark.css'

initTheme()
installMobileApiShim()

createApp(App).use(i18n).mount('#app')

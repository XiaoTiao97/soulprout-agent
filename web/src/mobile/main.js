import { createApp } from 'vue'
import App from './App.vue'
import i18n from '@/i18n'
import { installMobileApiShim } from './api'
import './mobile.css'

installMobileApiShim()

createApp(App).use(i18n).mount('#app')

import { createApp } from 'vue'
import DesktopApp from './DesktopApp.vue'
import router from './router'
import i18n from '@/i18n'
import '@/assets/css/init.css'
import './desktop.css'

document.documentElement.classList.add('soulprout-desktop')

createApp(DesktopApp).use(router).use(i18n).mount('#app')

// 与网页端一致：把 title 提示换成统一样式的悬浮提示（web/src/main.js）
document.body.addEventListener('mouseover', (event) => {
  const el = event.target instanceof Element ? event.target.closest('[title], [data-tip]') : null
  if (!(el instanceof HTMLElement)) return

  if (el.hasAttribute('title')) {
    const text = el.getAttribute('title')?.trim() ?? ''
    if (text) {
      el.dataset.tip = text
    } else {
      delete el.dataset.tip
    }
    el.removeAttribute('title')
  }

  if (el.dataset.tip?.trim()) {
    el.classList.add('hover-hint')
  } else {
    el.classList.remove('hover-hint')
  }
}, true)

// 桌面应用不需要网页的右键「重新加载 / 查看源代码」菜单
document.addEventListener('contextmenu', (event) => {
  const target = event.target
  const editable = target instanceof Element && target.closest('input, textarea, [contenteditable="true"], .markdown-body, pre, code')
  if (!editable) event.preventDefault()
})

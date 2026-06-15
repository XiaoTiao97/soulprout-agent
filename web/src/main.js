import { createApp } from 'vue'
import App from './App.vue'
import router from './router'
import './assets/css/init.css'

createApp(App).use(router).mount('#app')

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

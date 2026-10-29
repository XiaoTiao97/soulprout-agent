<template>
  <!-- 没有独立的标题栏：窗口按钮直接浮在页面右上角，页面从窗口最顶端开始，所以不会有色差和分隔线。
       顶部一条很窄的透明区域用来拖动窗口（双击最大化 / 还原）。 -->
  <div class="dk-titlebar">
    <div class="dk-drag" data-tauri-drag-region />
    <div v-if="native" class="dk-win-controls">
      <button class="dk-win-btn" :aria-label="s.minimize" @click="minimizeWindow()">
        <svg width="10" height="10" viewBox="0 0 10 10"><path d="M0 5h10" stroke="currentColor" stroke-width="1" /></svg>
      </button>
      <button class="dk-win-btn" :aria-label="maximized ? s.restore : s.maximize" @click="toggleMaximizeWindow()">
        <svg v-if="!maximized" width="10" height="10" viewBox="0 0 10 10"><rect x="0.5" y="0.5" width="9" height="9" rx="1.5" fill="none" stroke="currentColor" /></svg>
        <svg v-else width="10" height="10" viewBox="0 0 10 10">
          <path d="M2.5 2.5V1.5a1 1 0 0 1 1-1h5a1 1 0 0 1 1 1v5a1 1 0 0 1-1 1h-1" fill="none" stroke="currentColor" />
          <rect x="0.5" y="2.5" width="7" height="7" rx="1.2" fill="none" stroke="currentColor" />
        </svg>
      </button>
      <button class="dk-win-btn is-close" :aria-label="s.close" @click="closeWindow()">
        <svg width="10" height="10" viewBox="0 0 10 10"><path d="M0.5 0.5l9 9M9.5 0.5l-9 9" stroke="currentColor" stroke-width="1" /></svg>
      </button>
    </div>
  </div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { useStrings } from '../strings.js'
import {
  closeWindow,
  hasNativeWindow,
  isWindowMaximized,
  minimizeWindow,
  onWindowResized,
  toggleMaximizeWindow,
} from '../desktopApi.js'

const s = useStrings()
const native = hasNativeWindow()
const maximized = ref(false)
let stopResize = null

async function refreshMaximized() {
  maximized.value = await isWindowMaximized()
  document.documentElement.classList.toggle('dk-maximized', maximized.value)
}

onMounted(async () => {
  if (!native) return
  await refreshMaximized()
  stopResize = await onWindowResized(refreshMaximized)
})
onBeforeUnmount(() => {
  if (typeof stopResize === 'function') stopResize()
})
</script>

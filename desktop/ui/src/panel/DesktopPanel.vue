<template>
  <div class="dk-panel" role="dialog" aria-modal="true">
    <div class="dk-panel-drag" data-tauri-drag-region />
    <div class="dk-panel-toolbar">
      <button class="dk-back" @click="$emit('close')">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M15 18l-6-6 6-6" />
        </svg>
        {{ s.back }}
      </button>
    </div>
    <div class="dk-panel-scroll">
      <div class="dk-panel-inner">
        <SettingsPage v-if="page === 'settings'" :state="state" @refresh="$emit('refresh')" />
        <ConnectPage v-else-if="page === 'connect'" :state="state" @refresh="$emit('refresh')" />
      </div>
    </div>
  </div>
</template>

<script setup>
import { onBeforeUnmount, onMounted } from 'vue'
import { useStrings } from '../strings.js'
import SettingsPage from './SettingsPage.vue'
import ConnectPage from './ConnectPage.vue'

const emit = defineEmits(['close', 'refresh'])
defineProps({
  page: { type: String, required: true },
  state: { type: Object, default: null },
})

const s = useStrings()

function onKey(event) {
  // 有弹窗（服务设置等）打开时，Esc 先交给弹窗
  if (event.key === 'Escape' && !document.querySelector('.dk-overlay')) emit('close')
}
onMounted(() => window.addEventListener('keydown', onKey))
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))
</script>

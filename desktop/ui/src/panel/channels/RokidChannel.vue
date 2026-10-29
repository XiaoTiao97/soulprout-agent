<template>
  <div class="dk-detail">
    <p class="dk-block-desc dk-tight">{{ s.rokidHint }}</p>

    <template v-if="status?.configured">
      <div class="dk-list is-flat">
        <div v-for="row in rows" :key="row.key" class="dk-list-row">
          <span class="dk-row-label">{{ row.label }}</span>
          <span class="dk-row-value dk-mono">{{ row.shown }}</span>
          <button class="dk-link" @click="copy(row)">{{ copiedKey === row.key ? s.copied : s.copy }}</button>
        </div>
      </div>
    </template>
    <p v-else-if="status" class="dk-note">{{ s.rokidNotConfigured }}</p>

    <p v-if="status && !status.logged_in" class="dk-note">{{ s.rokidNeedLogin }}</p>
    <p v-else-if="status?.remote_error" class="dk-note">{{ s.rokidRemoteError }}</p>

    <div class="dk-form-actions">
      <button v-if="!status?.configured" class="dk-btn is-primary is-sm" :disabled="busy || !status?.logged_in" @click="run('ensure-key')">
        {{ busy ? s.rokidWorking : s.rokidGenerate }}
      </button>
      <button v-else class="dk-btn is-sm" :disabled="busy" @click="regenerate">{{ busy ? s.rokidWorking : s.rokidRegenerate }}</button>
      <span v-if="message" class="dk-small" :class="ok ? 'dk-ok' : 'dk-error'">{{ message }}</span>
    </div>
    <a v-if="status?.rokid_home_url" class="dk-link-a" :href="status.rokid_home_url" target="_blank" rel="noopener noreferrer">{{ s.rokidOpen }}</a>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, ref } from 'vue'
import { gateway } from '../../desktopApi.js'
import { useStrings } from '../../strings.js'

const props = defineProps({ status: { type: Object, default: null } })
const emit = defineEmits(['watch', 'refresh'])

const s = useStrings()
const busy = ref(false)
const message = ref('')
const ok = ref(true)
const copiedKey = ref('')
let copyTimer = null

const mask = (value) => (value && value.length > 12 ? `${value.slice(0, 6)}••••••${value.slice(-4)}` : value || '')

const rows = computed(() => {
  const st = props.status || {}
  return [
    { key: 'agent', label: s.value.rokidAgentId, value: st.agent_id || '', shown: st.agent_id || '' },
    { key: 'ak', label: s.value.rokidApiKey, value: st.api_key || '', shown: mask(st.api_key) },
    { key: 'sse', label: s.value.rokidSse, value: st.sse_url || '', shown: st.sse_url || '' },
  ]
})

async function copy(row) {
  try {
    await navigator.clipboard.writeText(row.value)
    copiedKey.value = row.key
    clearTimeout(copyTimer)
    copyTimer = setTimeout(() => (copiedKey.value = ''), 1500)
  } catch {
    /* 剪贴板不可用时忽略 */
  }
}

async function run(action) {
  busy.value = true
  message.value = ''
  try {
    const result = await gateway.post(`api/rokid/${action}`)
    ok.value = result.success !== false
    message.value = result.message || ''
    emit('refresh')
  } catch (err) {
    ok.value = false
    message.value = err.message
  } finally {
    busy.value = false
  }
}

function regenerate() {
  if (window.confirm(s.value.rokidRegenerateConfirm)) run('regenerate-key')
}

onBeforeUnmount(() => clearTimeout(copyTimer))
</script>

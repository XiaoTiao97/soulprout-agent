<template>
  <div class="dk-detail">
    <QrLogin platform="wecom" @connected="$emit('watch')" />

    <details class="dk-fold">
      <summary>{{ s.manualConfig }}</summary>
      <div class="dk-form">
        <label class="dk-label">{{ s.botId }}</label>
        <input v-model.trim="botId" class="dk-input dk-mono" type="text" autocomplete="off" spellcheck="false" />
        <label class="dk-label">{{ s.botSecret }}</label>
        <input v-model.trim="secret" class="dk-input dk-mono" type="password" autocomplete="off" />
        <div class="dk-form-actions">
          <button class="dk-btn is-primary is-sm" :disabled="saving" @click="save">{{ saving ? s.saving : s.saveConnect }}</button>
          <span v-if="message" class="dk-small" :class="ok ? 'dk-ok' : 'dk-error'">{{ message }}</span>
        </div>
      </div>
    </details>

    <ReconnectBar v-if="status?.configured" platform="wecom" @watch="$emit('watch')" />
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'
import { gateway } from '../../desktopApi.js'
import { useStrings } from '../../strings.js'
import QrLogin from './QrLogin.vue'
import ReconnectBar from './ReconnectBar.vue'

const props = defineProps({ status: { type: Object, default: null } })
const emit = defineEmits(['watch'])

const s = useStrings()
const botId = ref(props.status?.bot_id || '')
const secret = ref('')
const saving = ref(false)
const message = ref('')
const ok = ref(true)

watch(
  () => props.status?.bot_id,
  (value) => {
    if (value && !botId.value) botId.value = value
  },
)

async function save() {
  if (!botId.value || !secret.value) {
    ok.value = false
    message.value = s.value.fillRequired
    return
  }
  saving.value = true
  message.value = ''
  try {
    const result = await gateway.post('api/wecom/settings', { bot_id: botId.value, secret: secret.value })
    ok.value = true
    message.value = result.message || s.value.saved
    secret.value = ''
    emit('watch')
  } catch (err) {
    ok.value = false
    message.value = err.message
  } finally {
    saving.value = false
  }
}
</script>

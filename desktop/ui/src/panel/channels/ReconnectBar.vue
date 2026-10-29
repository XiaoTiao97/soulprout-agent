<template>
  <div class="dk-reconnect">
    <button class="dk-btn is-sm" :disabled="busy" @click="reconnect">{{ busy ? s.reconnecting : s.reconnect }}</button>
    <span v-if="message" class="dk-small" :class="ok ? 'dk-ok' : 'dk-error'">{{ message }}</span>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { gateway } from '../../desktopApi.js'
import { useStrings } from '../../strings.js'

const props = defineProps({ platform: { type: String, required: true } })
const emit = defineEmits(['watch'])

const s = useStrings()
const busy = ref(false)
const message = ref('')
const ok = ref(true)

async function reconnect() {
  busy.value = true
  message.value = ''
  try {
    await gateway.post(`api/${props.platform}/reload`)
    ok.value = true
    emit('watch')
  } catch (err) {
    ok.value = false
    message.value = err.message
  } finally {
    busy.value = false
  }
}
</script>

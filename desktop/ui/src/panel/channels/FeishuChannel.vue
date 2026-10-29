<template>
  <div class="dk-detail">
    <div class="dk-field-line">
      <span class="dk-row-label">{{ s.feishuDomain }}</span>
      <div class="dk-segment is-inline">
        <button type="button" :class="{ 'is-active': domain === 'feishu' }" @click="domain = 'feishu'">{{ s.feishuCn }}</button>
        <button type="button" :class="{ 'is-active': domain === 'lark' }" @click="domain = 'lark'">{{ s.feishuLark }}</button>
      </div>
    </div>
    <QrLogin platform="feishu" :body="{ domain }" @connected="$emit('watch')" />

    <details class="dk-fold">
      <summary>{{ s.manualConfig }}</summary>
      <div class="dk-form">
        <label class="dk-label">{{ s.appId }}</label>
        <input v-model.trim="appId" class="dk-input dk-mono" type="text" autocomplete="off" spellcheck="false" />
        <label class="dk-label">{{ s.appSecret }}</label>
        <input v-model.trim="appSecret" class="dk-input dk-mono" type="password" autocomplete="off" />
        <div class="dk-form-actions">
          <button class="dk-btn is-primary is-sm" :disabled="saving" @click="save">{{ saving ? s.saving : s.saveConnect }}</button>
          <span v-if="message" class="dk-small" :class="ok ? 'dk-ok' : 'dk-error'">{{ message }}</span>
        </div>
      </div>
    </details>

    <ReconnectBar v-if="status?.configured" platform="feishu" @watch="$emit('watch')" />
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
const domain = ref(props.status?.domain === 'lark' ? 'lark' : 'feishu')
const appId = ref(props.status?.app_id || '')
const appSecret = ref('')
const saving = ref(false)
const message = ref('')
const ok = ref(true)

watch(
  () => props.status?.app_id,
  (value) => {
    if (value && !appId.value) appId.value = value
  },
)

async function save() {
  if (!appId.value || !appSecret.value) {
    ok.value = false
    message.value = s.value.fillRequired
    return
  }
  saving.value = true
  message.value = ''
  try {
    const result = await gateway.post('api/feishu/settings', { app_id: appId.value, app_secret: appSecret.value, domain: domain.value })
    ok.value = true
    message.value = result.message || s.value.saved
    appSecret.value = ''
    emit('watch')
  } catch (err) {
    ok.value = false
    message.value = err.message
  } finally {
    saving.value = false
  }
}
</script>

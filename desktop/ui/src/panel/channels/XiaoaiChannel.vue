<template>
  <div class="dk-detail">
    <div class="dk-form">
      <label class="dk-label">{{ s.xiaomiId }}</label>
      <input v-model.trim="form.user_id" class="dk-input dk-mono" type="text" autocomplete="off" spellcheck="false" />
      <label class="dk-label">{{ s.xiaomiDid }}</label>
      <input v-model.trim="form.did" class="dk-input" type="text" autocomplete="off" spellcheck="false" />
      <label class="dk-label">{{ s.xiaomiPassword }}</label>
      <input v-model="form.password" class="dk-input" type="password" autocomplete="new-password" />
      <p v-if="hints.has_password" class="dk-hint is-visible">{{ s.xiaomiPasswordSaved }}</p>

      <details class="dk-fold">
        <summary>{{ s.xiaomiAdvanced }}</summary>
        <div class="dk-form">
          <label class="dk-label">{{ s.xiaomiPassToken }}</label>
          <input v-model.trim="form.pass_token" class="dk-input dk-mono" type="password" autocomplete="off" />
          <p v-if="hints.has_pass_token" class="dk-hint is-visible">{{ s.xiaomiTokenSaved }}</p>
          <label class="dk-label">{{ s.xiaomiKeywords }}</label>
          <input v-model.trim="form.call_ai_keywords" class="dk-input" type="text" autocomplete="off" />
          <label class="dk-label">{{ s.xiaomiHeartbeat }}</label>
          <input v-model.number="form.heartbeat_ms" class="dk-input" type="number" min="200" step="100" />
          <label class="dk-inline-check">
            <input v-model="form.debug" type="checkbox" />
            <span>{{ s.xiaomiDebug }}</span>
          </label>
        </div>
      </details>

      <div class="dk-form-actions">
        <button class="dk-btn is-primary is-sm" :disabled="busy" @click="save">{{ saving ? s.saving : s.saveConnect }}</button>
        <button class="dk-btn is-sm" :disabled="busy" @click="test">{{ testing ? s.xiaomiTesting : s.xiaomiTest }}</button>
        <span v-if="message" class="dk-small" :class="ok ? 'dk-ok' : 'dk-error'">{{ message }}</span>
      </div>
      <p v-if="status?.last_error" class="dk-small dk-note">{{ s.xiaomiLastError }}：{{ status.last_error }}</p>
    </div>

    <ReconnectBar v-if="status?.configured" platform="xiaoai" @watch="$emit('watch')" />
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { gateway } from '../../desktopApi.js'
import { useStrings } from '../../strings.js'
import ReconnectBar from './ReconnectBar.vue'

defineProps({ status: { type: Object, default: null } })
const emit = defineEmits(['watch'])

const s = useStrings()
const form = reactive({ user_id: '', did: '', password: '', pass_token: '', call_ai_keywords: '请,你', heartbeat_ms: 1000, debug: false })
const hints = reactive({ has_password: false, has_pass_token: false })
const saving = ref(false)
const testing = ref(false)
const busy = computed(() => saving.value || testing.value)
const message = ref('')
const ok = ref(true)

async function load() {
  try {
    const data = await gateway.get('api/xiaoai/config')
    const cfg = data.config || {}
    form.user_id = cfg.user_id || ''
    form.did = cfg.did || ''
    form.call_ai_keywords = (cfg.call_ai_keywords || ['请', '你']).join(',')
    form.heartbeat_ms = cfg.heartbeat_ms || 1000
    form.debug = !!cfg.debug
    hints.has_password = !!cfg.has_password
    hints.has_pass_token = !!cfg.has_pass_token
  } catch (err) {
    ok.value = false
    message.value = err.message
  }
}

function checkBasic() {
  if (form.user_id && form.did) return true
  ok.value = false
  message.value = s.value.xiaomiNeedBasic
  return false
}

async function save() {
  if (!checkBasic()) return
  saving.value = true
  message.value = ''
  try {
    const result = await gateway.post('api/xiaoai/settings', { ...form })
    ok.value = true
    message.value = result.message || s.value.saved
    form.password = ''
    await load()
    emit('watch')
  } catch (err) {
    ok.value = false
    message.value = err.message
  } finally {
    saving.value = false
  }
}

async function test() {
  if (!checkBasic()) return
  testing.value = true
  message.value = ''
  try {
    const result = await gateway.post('api/xiaoai/test', { ...form })
    ok.value = !!result.success
    message.value = result.message || ''
  } catch (err) {
    ok.value = false
    message.value = err.message
  } finally {
    testing.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="dk-overlay" @mousedown.self="$emit('close')">
    <div class="dk-dialog" role="dialog" aria-modal="true">
      <div class="dk-dialog-head">
        <h3>{{ s.serviceDialogTitle }}</h3>
        <button class="dk-icon-btn" :aria-label="s.close" @click="$emit('close')">
          <svg width="14" height="14" viewBox="0 0 10 10"><path d="M0.5 0.5l9 9M9.5 0.5l-9 9" stroke="currentColor" stroke-width="1.2" /></svg>
        </button>
      </div>
      <p class="dk-block-desc">{{ s.serviceDialogDesc }}</p>

      <div class="dk-segment" role="tablist">
        <button type="button" role="tab" :class="{ 'is-active': mode === 'official' }" @click="mode = 'official'">{{ s.serviceOfficial }}</button>
        <button type="button" role="tab" :class="{ 'is-active': mode === 'custom' }" @click="mode = 'custom'">{{ s.serviceCustom }}</button>
      </div>

      <p v-if="mode === 'official'" class="dk-mono dk-small dk-muted-line">{{ officialUrl }}</p>
      <input
        v-else
        ref="urlInput"
        v-model.trim="url"
        class="dk-input dk-mono"
        type="text"
        spellcheck="false"
        :placeholder="s.serviceUrlPlaceholder"
        @keydown.enter="save"
      />

      <p v-if="testMessage" class="dk-small" :class="testOk ? 'dk-ok' : 'dk-error'">{{ testMessage }}</p>
      <p v-if="error" class="dk-error dk-small">{{ error }}</p>
      <p class="dk-hint is-visible">{{ s.serviceSwitchNote }}</p>

      <div class="dk-dialog-actions">
        <button class="dk-btn" :disabled="testing || busy" @click="test">
          {{ testing ? s.serviceTesting : s.serviceTest }}
        </button>
        <span class="dk-spacer" />
        <button class="dk-btn" @click="$emit('close')">{{ s.cancel }}</button>
        <button class="dk-btn is-primary" :disabled="busy" @click="save">{{ s.save }}</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { nextTick, ref, watch } from 'vue'
import { isCustomCloud, officialCloudUrl, setCloudUrl, testCloudUrl } from '../desktopApi.js'
import { useStrings } from '../strings.js'

const props = defineProps({ state: { type: Object, required: true } })
const emit = defineEmits(['close', 'changed'])

const s = useStrings()
const officialUrl = officialCloudUrl(props.state.cloud)
const startedCustom = isCustomCloud(props.state.cloud)
const mode = ref(startedCustom ? 'custom' : 'official')
const url = ref(startedCustom ? props.state.cloud.url : 'http://localhost:8080')
const urlInput = ref(null)
const busy = ref(false)
const testing = ref(false)
const testMessage = ref('')
const testOk = ref(false)
const error = ref('')

watch(mode, async (value) => {
  testMessage.value = ''
  error.value = ''
  if (value === 'custom') {
    if (!url.value) url.value = 'http://localhost:8080'
    await nextTick()
    urlInput.value?.focus()
  }
})

const target = () => (mode.value === 'official' ? '' : url.value)

async function test() {
  if (mode.value === 'custom' && !url.value) {
    error.value = s.value.serviceInvalid
    return
  }
  testing.value = true
  error.value = ''
  testMessage.value = ''
  try {
    const result = await testCloudUrl(target())
    testOk.value = !!result.success
    testMessage.value = result.success ? s.value.serviceTestOk : result.message
  } catch (err) {
    testOk.value = false
    testMessage.value = err.message
  } finally {
    testing.value = false
  }
}

async function save() {
  if (mode.value === 'custom' && !url.value) {
    error.value = s.value.serviceInvalid
    return
  }
  busy.value = true
  error.value = ''
  try {
    const result = await setCloudUrl(target())
    emit('changed')
    emit('close')
    // 换了服务器，旧的登录态已被清掉：回到登录页重新登录
    if (result.changed) window.location.assign('/register')
  } catch (err) {
    error.value = err.message
  } finally {
    busy.value = false
  }
}
</script>

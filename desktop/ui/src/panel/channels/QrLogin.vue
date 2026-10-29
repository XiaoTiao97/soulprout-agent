<template>
  <div class="dk-qr">
    <div v-if="!active" class="dk-qr-idle">
      <button class="dk-btn is-primary" :disabled="loading" @click="start">
        {{ loading ? s.gettingQr : s.scanConnect }}
      </button>
    </div>

    <div v-else class="dk-qr-live">
      <div class="dk-qr-frame">
        <img v-if="showImage" :src="image" alt="QR" @error="imageFailed = true" />
        <div v-else class="dk-qr-fallback">{{ s.qrImageFailed }}</div>
      </div>
      <div class="dk-qr-side">
        <p class="dk-qr-msg">{{ message }}</p>
        <a v-if="link" class="dk-qr-link dk-mono" :href="link" target="_blank" rel="noopener noreferrer">{{ link }}</a>
        <button class="dk-btn is-sm" @click="cancel">{{ s.qrCancel }}</button>
      </div>
    </div>

    <p v-if="error" class="dk-error dk-small">{{ error }}</p>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, ref } from 'vue'
import QRCode from 'qrcode'

const toDataURL = QRCode.toDataURL || QRCode.default?.toDataURL
import { gateway } from '../../desktopApi.js'
import { useStrings } from '../../strings.js'

const props = defineProps({
  platform: { type: String, required: true }, // weixin | feishu | wecom
  body: { type: Object, default: () => ({}) },
})
const emit = defineEmits(['connected'])

const s = useStrings()
const active = ref(false)
const loading = ref(false)
const image = ref('')
const link = ref('')
const message = ref('')
const error = ref('')
const imageFailed = ref(false)
let timer = null

const showImage = computed(() => /^(https?:|data:image\/)/i.test(image.value) && !imageFailed.value)

function stop() {
  clearInterval(timer)
  timer = null
}

function payloadOf(data) {
  return data.scan_url || data.qr_url || data.qrcode_value || data.auth_url || ''
}

async function applyQr(data) {
  const payload = payloadOf(data)
  const href = data.scan_url || data.qr_url || data.auth_url || ''
  link.value = /^https?:/i.test(href) ? href : ''
  imageFailed.value = false
  if (payload) {
    try {
      image.value = await toDataURL(payload, { width: 192, margin: 1, errorCorrectionLevel: 'M' })
      return
    } catch {
      /* 本机生成失败时再试远端图片 */
    }
  }
  const remote = data.qrcode_url || ''
  image.value = /^(https?:|data:image\/)/i.test(remote) ? remote : ''
}

async function start() {
  loading.value = true
  error.value = ''
  try {
    const data = await gateway.post(`api/${props.platform}/login/start`, props.body)
    if (data.success === false) throw new Error(data.error || s.value.qrFailed)
    await applyQr(data)
    message.value = s.value.waitingScan
    active.value = true
    stop()
    timer = setInterval(poll, 2000)
  } catch (err) {
    error.value = err.message
  } finally {
    loading.value = false
  }
}

async function poll() {
  try {
    const data = await gateway.get(`api/${props.platform}/login/poll`)
    if (data.status === 'wait') {
      message.value = s.value.waitingScan
    } else if (data.status === 'scaned') {
      message.value = s.value.scanned
    } else if (data.status === 'refreshed') {
      message.value = s.value.qrRefreshed
      await applyQr(data)
    } else if (data.status === 'confirmed') {
      stop()
      active.value = false
      error.value = ''
      emit('connected')
    } else if (data.status === 'error') {
      stop()
      active.value = false
      error.value = `${s.value.qrFailed}：${data.error || ''}`
    }
  } catch (err) {
    error.value = err.message
  }
}

function cancel() {
  stop()
  active.value = false
  error.value = ''
}

onBeforeUnmount(stop)
</script>

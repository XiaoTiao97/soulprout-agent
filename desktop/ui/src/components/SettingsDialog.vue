<template>
  <div class="dk-overlay" @mousedown.self="$emit('close')">
    <div class="dk-dialog dk-settings" role="dialog" aria-modal="true">
      <div class="dk-dialog-head">
        <h3>{{ s.settingsTitle }}</h3>
        <button class="dk-icon-btn" :title="s.close" @click="$emit('close')">
          <svg width="14" height="14" viewBox="0 0 10 10"><path d="M0.5 0.5l9 9M9.5 0.5l-9 9" stroke="currentColor" stroke-width="1.2" /></svg>
        </button>
      </div>

      <p v-if="error" class="dk-error">{{ error }}</p>

      <div v-if="state" class="dk-settings-body">
        <!-- 本机权限 -->
        <section class="dk-section">
          <h4>{{ s.permission }}</h4>
          <p class="dk-muted dk-small">{{ s.permissionDesc }}</p>
          <label
            v-for="preset in state.policy.presets"
            :key="preset.name"
            class="dk-radio"
            :class="{ 'is-active': preset.name === state.policy.preset, 'is-danger': preset.danger }"
          >
            <input type="radio" name="preset" :checked="preset.name === state.policy.preset" @change="choose(preset)" />
            <span class="dk-radio-main">
              <span class="dk-radio-label">{{ preset.label }}</span>
              <span class="dk-radio-desc">{{ preset.description }}</span>
            </span>
          </label>
          <p v-if="savedHint" class="dk-ok dk-small">{{ s.saved }}</p>
        </section>

        <!-- 连接状态 -->
        <section class="dk-section">
          <h4>{{ s.cloudServer }}</h4>
          <dl class="dk-kv">
            <dt>{{ s.connection }}</dt>
            <dd><span class="dk-dot" :class="`is-${state.cloud.state}`" /> {{ s.cloud[state.cloud.state] || state.cloud.state }}</dd>
            <dt>URL</dt>
            <dd class="dk-mono">{{ state.cloud.url }}</dd>
          </dl>
          <p v-if="state.cloud.error" class="dk-muted dk-small">{{ state.cloud.error }}</p>
        </section>

        <!-- 设备 -->
        <section class="dk-section">
          <h4>{{ s.device }}</h4>
          <dl class="dk-kv">
            <dt>{{ s.deviceName }}</dt>
            <dd>{{ state.device.name }}</dd>
            <dt>{{ s.deviceId }}</dt>
            <dd class="dk-mono">{{ state.device.id }}</dd>
            <dt>{{ s.folder }}</dt>
            <dd class="dk-mono">{{ state.paths.workspaces }}</dd>
          </dl>
          <button class="dk-btn" @click="openFolder">{{ s.openFolder }}</button>
        </section>

        <!-- Gateway -->
        <section class="dk-section">
          <h4>{{ s.gateway }}</h4>
          <p v-if="!state.gateway.enabled" class="dk-muted dk-small">{{ s.gatewayDisabled }}</p>
          <template v-else>
            <ul v-if="channelNames.length" class="dk-channels">
              <li v-for="name in channelNames" :key="name">
                <span class="dk-dot" :class="state.gateway.channels[name] ? 'is-online' : 'is-offline'" />
                <span>{{ name }}</span>
                <span class="dk-muted dk-small">{{ state.gateway.channels[name] ? s.channelOn : s.channelOff }}</span>
              </li>
            </ul>
            <p v-else class="dk-muted dk-small">{{ s.noChannels }}</p>
            <button v-if="state.gateway.url" class="dk-btn" @click="gatewayOpen = true">{{ s.gatewayOpen }}</button>
          </template>
        </section>

        <p class="dk-muted dk-small dk-version">{{ s.version }} {{ state.version }}</p>
      </div>
    </div>

    <!-- Gateway 管理页（本机另一个端口，用内嵌框架显示） -->
    <div v-if="gatewayOpen" class="dk-overlay dk-gateway-overlay" @mousedown.self="gatewayOpen = false">
      <div class="dk-dialog dk-gateway">
        <div class="dk-dialog-head">
          <h3>{{ s.gateway }}</h3>
          <button class="dk-icon-btn" :title="s.close" @click="gatewayOpen = false">
            <svg width="14" height="14" viewBox="0 0 10 10"><path d="M0.5 0.5l9 9M9.5 0.5l-9 9" stroke="currentColor" stroke-width="1.2" /></svg>
          </button>
        </div>
        <iframe class="dk-gateway-frame" :src="state.gateway.url" referrerpolicy="no-referrer" />
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { getState, openWorkspaceFolder, setPreset } from '../desktopApi.js'
import { useStrings } from '../strings.js'

defineEmits(['close'])
const s = useStrings()
const state = ref(null)
const error = ref('')
const savedHint = ref(false)
const gatewayOpen = ref(false)
let timer = null
let hintTimer = null

const channelNames = computed(() => Object.keys(state.value?.gateway?.channels || {}))

async function refresh() {
  try {
    state.value = await getState()
    error.value = ''
  } catch (err) {
    error.value = `${s.value.loadFailed}：${err.message}`
  }
}

async function choose(preset) {
  if (preset.name === state.value.policy.preset) return
  if (preset.danger && !window.confirm(s.value.dangerConfirm)) {
    await refresh() // 把单选框恢复成原来的选择
    return
  }
  try {
    await setPreset(preset.name)
    await refresh()
    savedHint.value = true
    clearTimeout(hintTimer)
    hintTimer = setTimeout(() => (savedHint.value = false), 1800)
  } catch (err) {
    error.value = err.message
    await refresh()
  }
}

async function openFolder() {
  try {
    await openWorkspaceFolder()
  } catch (err) {
    error.value = err.message
  }
}

onMounted(() => {
  refresh()
  timer = setInterval(refresh, 4000)
})
onBeforeUnmount(() => {
  clearInterval(timer)
  clearTimeout(hintTimer)
})
</script>

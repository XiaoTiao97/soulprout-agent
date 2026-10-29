<template>
  <div class="dk-page">
    <h1>{{ s.settingsTitle }}</h1>
    <p class="dk-page-sub">{{ s.settingsSub }}</p>

    <p v-if="!state" class="dk-note">{{ s.loadFailed }}</p>

    <template v-else>
      <!-- 权限 -->
      <section class="dk-block">
        <h2 class="dk-block-title">{{ s.permission }}</h2>
        <p class="dk-block-desc">{{ s.permissionDesc }}</p>
        <div class="dk-list">
          <label
            v-for="preset in state.policy.presets"
            :key="preset.name"
            class="dk-list-row dk-choice"
            :class="{ 'is-active': preset.name === state.policy.preset, 'is-danger': preset.danger }"
          >
            <input type="radio" name="preset" :checked="preset.name === state.policy.preset" @change="choose(preset)" />
            <span class="dk-check" aria-hidden="true">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12.5l4.5 4.5L19 7.5" /></svg>
            </span>
            <span class="dk-choice-main">
              <span class="dk-choice-label">{{ preset.label }}</span>
              <span class="dk-choice-desc">{{ preset.description }}</span>
            </span>
          </label>
        </div>
        <p class="dk-hint" :class="{ 'is-visible': savedHint }">{{ s.saved }}</p>
      </section>

      <!-- 云端服务 -->
      <section class="dk-block">
        <h2 class="dk-block-title">{{ s.cloudServer }}</h2>
        <p class="dk-block-desc">{{ s.cloudServerDesc }}</p>
        <div class="dk-list">
          <div class="dk-list-row">
            <span class="dk-row-label">{{ s.connection }}</span>
            <span class="dk-row-value">
              <span class="dk-dot" :class="{ 'is-online': state.cloud.state === 'online' }" />
              {{ s.cloud[state.cloud.state] || state.cloud.state }}
            </span>
          </div>
          <div class="dk-list-row">
            <span class="dk-row-label">{{ s.currentService }}</span>
            <span class="dk-row-value">
              <span v-if="!customCloud" class="dk-tag">{{ s.official }}</span>
              <span v-else class="dk-tag is-muted">{{ s.custom }}</span>
            </span>
            <button class="dk-icon-btn is-round" :aria-label="s.serviceSettings" @click="serviceOpen = true">
              <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                <circle cx="12" cy="12" r="3" />
                <path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l.1-.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z" />
              </svg>
            </button>
          </div>
          <div v-if="customCloud" class="dk-list-row">
            <span class="dk-row-label">{{ s.serviceUrl }}</span>
            <span class="dk-row-value dk-mono">{{ state.cloud.url }}</span>
          </div>
        </div>
        <p v-if="state.cloud.error && state.cloud.state !== 'online'" class="dk-note">{{ state.cloud.error }}</p>
      </section>

      <!-- 这台电脑 -->
      <section class="dk-block">
        <h2 class="dk-block-title">{{ s.device }}</h2>
        <p class="dk-block-desc">{{ s.deviceDesc }}</p>
        <div class="dk-list">
          <div class="dk-list-row">
            <span class="dk-row-label">{{ s.deviceName }}</span>
            <span class="dk-row-value">{{ state.device.name }}</span>
          </div>
          <div class="dk-list-row">
            <span class="dk-row-label">{{ s.deviceId }}</span>
            <span class="dk-row-value dk-mono">{{ state.device.id }}</span>
          </div>
          <div class="dk-list-row">
            <span class="dk-row-label">{{ s.folder }}</span>
            <span class="dk-row-value dk-mono">{{ state.paths.workspaces }}</span>
            <button class="dk-link" @click="openFolder">{{ s.openFolder }}</button>
          </div>
        </div>
      </section>

      <p v-if="error" class="dk-error">{{ error }}</p>
      <p class="dk-version">{{ s.version }} {{ state.version }}</p>
    </template>

    <ServiceDialog v-if="serviceOpen && state" :state="state" @close="serviceOpen = false" @changed="$emit('refresh')" />
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, ref } from 'vue'
import { isCustomCloud, openWorkspaceFolder, setPreset } from '../desktopApi.js'
import { useStrings } from '../strings.js'
import ServiceDialog from './ServiceDialog.vue'

const props = defineProps({ state: { type: Object, default: null } })
const emit = defineEmits(['refresh'])

const s = useStrings()
const customCloud = computed(() => isCustomCloud(props.state?.cloud))
const error = ref('')
const savedHint = ref(false)
const serviceOpen = ref(false)
let hintTimer = null

async function choose(preset) {
  if (preset.name === props.state.policy.preset) return
  if (preset.danger && !window.confirm(s.value.dangerConfirm)) {
    emit('refresh') // 把单选框恢复成原来的选择
    return
  }
  try {
    await setPreset(preset.name)
    error.value = ''
    savedHint.value = true
    clearTimeout(hintTimer)
    hintTimer = setTimeout(() => (savedHint.value = false), 1800)
  } catch (err) {
    error.value = err.message
  }
  emit('refresh')
}

async function openFolder() {
  try {
    await openWorkspaceFolder()
  } catch (err) {
    error.value = err.message
  }
}

onBeforeUnmount(() => clearTimeout(hintTimer))
</script>

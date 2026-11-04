<template>
  <button type="button" class="locale-switcher" @click="toggle">
    <svg class="locale-switcher-icon" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
      <circle cx="12" cy="12" r="9.5" />
      <path d="M2.5 12h19" />
      <path d="M12 2.5a14.5 14.5 0 0 1 0 19 14.5 14.5 0 0 1 0-19" />
    </svg>
    <span>{{ t('nav.langSwitch') }}</span>
  </button>
</template>

<script setup>
import { useI18n } from 'vue-i18n'
import { setLocale } from '@/i18n'

const { t, locale } = useI18n()

function toggle() {
  setLocale(locale.value === 'zh-CN' ? 'en' : 'zh-CN')
}
</script>

<style scoped>
.locale-switcher {
  display: inline-flex;
  align-items: center;
  gap: 0.38rem;
  background: transparent;
  border: none;
  border-radius: 999px;
  padding: 0.42rem 0.78rem;
  font-size: 0.82rem;
  color: rgba(15, 15, 15, 0.55);
  cursor: pointer;
  transition: background-color 0.2s ease, color 0.2s ease;
  white-space: nowrap;
}
.locale-switcher-icon {
  flex-shrink: 0;
  opacity: 0.85;
}
.locale-switcher:hover {
  background: rgba(15, 15, 15, 0.06);
  color: #0f0f0f;
}

html[data-theme='dark'] .locale-switcher {
  color: rgba(243, 244, 246, 0.65);
}

html[data-theme='dark'] .locale-switcher:hover {
  background: rgba(255, 255, 255, 0.08);
  color: #f3f4f6;
}
</style>

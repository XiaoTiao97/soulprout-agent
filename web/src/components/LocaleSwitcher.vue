<template>
  <button type="button" class="locale-switcher" @click="toggle">
    {{ t('nav.langSwitch') }}
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
  background: none;
  border: 1px solid rgba(15, 15, 15, 0.12);
  border-radius: 999px;
  padding: 0.35rem 0.75rem;
  font-size: 0.8rem;
  color: rgba(15, 15, 15, 0.55);
  cursor: pointer;
  transition: all 0.25s ease;
  white-space: nowrap;
}
.locale-switcher:hover {
  border-color: rgba(30, 180, 140, 0.45);
  color: #1eb48c;
}
</style>

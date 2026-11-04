<template>
  <div class="theme-switcher" ref="rootRef">
    <button
      type="button"
      class="theme-switcher-btn"
      :aria-expanded="open"
      :aria-label="t('theme.switchLabel')"
      :title=" `${t('theme.switchLabel')}：${currentLabel}` "
      @click.stop="toggleMenu"
    >
      <!-- 跟随系统图标 -->
      <svg
        v-if="themeMode === 'system'"
        class="theme-switcher-icon"
        width="15"
        height="15"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="1.75"
        stroke-linecap="round"
        stroke-linejoin="round"
        aria-hidden="true"
      >
        <rect x="3" y="4" width="18" height="12" rx="2" />
        <path d="M8 20h8M12 16v4" />
      </svg>
      <!-- 白天模式图标 -->
      <svg
        v-else-if="themeMode === 'light'"
        class="theme-switcher-icon"
        width="15"
        height="15"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="1.75"
        stroke-linecap="round"
        stroke-linejoin="round"
        aria-hidden="true"
      >
        <circle cx="12" cy="12" r="4.5" />
        <path d="M12 2.5v2.2M12 19.3v2.2M4.93 4.93l1.56 1.56M17.51 17.51l1.56 1.56M2.5 12h2.2M19.3 12h2.2M4.93 19.07l1.56-1.56M17.51 6.49l1.56-1.56" />
      </svg>
      <!-- 夜晚模式图标 -->
      <svg
        v-else
        class="theme-switcher-icon"
        width="15"
        height="15"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="1.75"
        stroke-linecap="round"
        stroke-linejoin="round"
        aria-hidden="true"
      >
        <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
      </svg>
      <span class="theme-switcher-label">{{ currentLabel }}</span>
    </button>

    <Transition name="theme-pop">
      <div v-if="open" class="theme-switcher-menu" role="menu">
        <button
          v-for="opt in options"
          :key="opt.value"
          type="button"
          role="menuitemradio"
          :aria-checked="themeMode === opt.value"
          class="theme-switcher-option"
          :class="{ 'is-active': themeMode === opt.value }"
          @click.stop="selectMode(opt.value)"
        >
          <svg
            v-if="opt.value === 'system'"
            class="theme-option-icon"
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="1.75"
            stroke-linecap="round"
            stroke-linejoin="round"
            aria-hidden="true"
          >
            <rect x="3" y="4" width="18" height="12" rx="2" />
            <path d="M8 20h8M12 16v4" />
          </svg>
          <svg
            v-else-if="opt.value === 'light'"
            class="theme-option-icon"
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="1.75"
            stroke-linecap="round"
            stroke-linejoin="round"
            aria-hidden="true"
          >
            <circle cx="12" cy="12" r="4.5" />
            <path d="M12 2.5v2.2M12 19.3v2.2M4.93 4.93l1.56 1.56M17.51 17.51l1.56 1.56M2.5 12h2.2M19.3 12h2.2M4.93 19.07l1.56-1.56M17.51 6.49l1.56-1.56" />
          </svg>
          <svg
            v-else
            class="theme-option-icon"
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="1.75"
            stroke-linecap="round"
            stroke-linejoin="round"
            aria-hidden="true"
          >
            <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
          </svg>
          <span class="theme-option-text">{{ opt.label }}</span>
          <span v-if="themeMode === opt.value" class="theme-option-check" aria-hidden="true">
            <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M3.5 8.5l3 3 6-6.5" />
            </svg>
          </span>
        </button>
      </div>
    </Transition>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { themeMode, setThemeMode } from '@/utils/theme.js'

const { t } = useI18n()
const open = ref(false)
const rootRef = ref(null)

const options = computed(() => [
  { value: 'system', label: t('theme.system') },
  { value: 'light', label: t('theme.light') },
  { value: 'dark', label: t('theme.dark') },
])

const currentLabel = computed(() => {
  if (themeMode.value === 'light') return t('theme.lightShort')
  if (themeMode.value === 'dark') return t('theme.darkShort')
  return t('theme.systemShort')
})

function toggleMenu() {
  open.value = !open.value
}

function selectMode(mode) {
  setThemeMode(mode)
  open.value = false
}

function onClickOutside(event) {
  if (!open.value) return
  if (rootRef.value && !rootRef.value.contains(event.target)) {
    open.value = false
  }
}

onMounted(() => {
  document.addEventListener('click', onClickOutside)
})

onUnmounted(() => {
  document.removeEventListener('click', onClickOutside)
})
</script>

<style scoped>
.theme-switcher {
  position: relative;
  display: inline-flex;
  align-items: center;
}

.theme-switcher-btn {
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
  font-family: inherit;
}

.theme-switcher-icon {
  flex-shrink: 0;
  opacity: 0.88;
}

.theme-switcher-btn:hover {
  background: rgba(15, 15, 15, 0.06);
  color: #0f0f0f;
}

.theme-switcher-menu {
  position: absolute;
  top: calc(100% + 8px);
  right: 0;
  min-width: 136px;
  padding: 5px;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.94);
  backdrop-filter: blur(20px) saturate(140%);
  -webkit-backdrop-filter: blur(20px) saturate(140%);
  border: 1px solid rgba(15, 15, 15, 0.08);
  box-shadow:
    0 12px 32px rgba(0, 0, 0, 0.1),
    0 2px 6px rgba(0, 0, 0, 0.04);
  display: flex;
  flex-direction: column;
  gap: 2px;
  z-index: 200;
}

.theme-switcher-option {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 7px 10px;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: rgba(15, 15, 15, 0.72);
  font-size: 0.8rem;
  font-weight: 500;
  font-family: inherit;
  cursor: pointer;
  text-align: left;
  white-space: nowrap;
  transition: background-color 0.16s ease, color 0.16s ease;
}

.theme-switcher-option:hover {
  background: rgba(15, 15, 15, 0.05);
  color: #0f0f0f;
}

.theme-switcher-option.is-active {
  color: #1eb48c;
  background: rgba(30, 180, 140, 0.08);
}

.theme-option-icon {
  flex-shrink: 0;
  opacity: 0.88;
}

.theme-option-text {
  flex: 1;
}

.theme-option-check {
  display: inline-flex;
  align-items: center;
  color: #1eb48c;
  margin-left: 4px;
}

.theme-pop-enter-active,
.theme-pop-leave-active {
  transition: opacity 0.16s ease, transform 0.16s cubic-bezier(0.22, 1, 0.36, 1);
}

.theme-pop-enter-from,
.theme-pop-leave-to {
  opacity: 0;
  transform: translateY(-4px) scale(0.97);
}

html[data-theme='dark'] .theme-switcher-btn {
  color: rgba(243, 244, 246, 0.65);
}

html[data-theme='dark'] .theme-switcher-btn:hover {
  background: rgba(255, 255, 255, 0.08);
  color: #f3f4f6;
}

html[data-theme='dark'] .theme-switcher-menu {
  background: rgba(26, 26, 29, 0.96);
  border-color: rgba(255, 255, 255, 0.1);
  box-shadow:
    0 16px 40px rgba(0, 0, 0, 0.48),
    0 2px 8px rgba(0, 0, 0, 0.28);
}

html[data-theme='dark'] .theme-switcher-option {
  color: rgba(229, 229, 229, 0.78);
}

html[data-theme='dark'] .theme-switcher-option:hover {
  background: rgba(255, 255, 255, 0.07);
  color: #ffffff;
}

html[data-theme='dark'] .theme-switcher-option.is-active {
  color: #8cc4b3;
  background: rgba(46, 108, 90, 0.2);
}

html[data-theme='dark'] .theme-option-check {
  color: #8cc4b3;
}
</style>

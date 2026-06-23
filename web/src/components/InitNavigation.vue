<template>
  <nav class="sp-nav" :class="{ 'sp-nav--scrolled': scrolled }">
    <div class="sp-nav-inner">
      <!-- Logo -->
      <a href="/" class="sp-nav-logo" @click.prevent="scrollToTop">
        <img src="@/assets/images/logo.png" alt="Soulprout" />
      </a>

      <!-- Links -->
      <div class="sp-nav-links">
        <button class="sp-nav-link" @click="scrollTo('capabilities')">{{ t('nav.capabilities') }}</button>
        <button class="sp-nav-link" @click="scrollTo('intelligence')">{{ t('nav.openSource') }}</button>
      </div>

      <div class="sp-nav-actions">
        <LocaleSwitcher class="sp-nav-locale" />
        <button type="button" class="sp-nav-cta" @click="handleStart">
          <span>{{ t('nav.start') }}</span>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
            <path d="M5 12h14M12 5l7 7-7 7" />
          </svg>
        </button>
      </div>
    </div>
  </nav>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { startExperience } from '@/utils/startExperience.js'
import LocaleSwitcher from '@/components/LocaleSwitcher.vue'

const router = useRouter()
const { t } = useI18n()
const scrolled = ref(false)
const onScroll = () => { scrolled.value = window.scrollY > 80 }

onMounted(() => { window.addEventListener('scroll', onScroll, { passive: true }) })
onUnmounted(() => { window.removeEventListener('scroll', onScroll) })

const scrollToTop = () => { window.scrollTo({ top: 0, behavior: 'smooth' }) }
function handleStart() {
  startExperience(router)
}
const scrollTo = (id) => {
  const el = document.getElementById(id)
  if (el) el.scrollIntoView({ behavior: 'smooth' })
}
</script>

<style scoped>
.sp-nav {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  z-index: 50;
  background: rgba(255, 255, 255, 0.6);
  backdrop-filter: blur(24px) saturate(150%);
  -webkit-backdrop-filter: blur(24px) saturate(150%);
  border-bottom: 1px solid rgba(30, 180, 140, 0.06);
  padding: 1.25rem 0;
  transition: padding 0.5s, box-shadow 0.5s;
}
.sp-nav--scrolled {
  padding: 0.75rem 0;
  box-shadow: 0 1px 20px rgba(0, 0, 0, 0.04);
}
.sp-nav-inner {
  max-width: 1200px;
  margin: 0 auto;
  padding: 0 2rem;
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.sp-nav-logo {
  display: inline-flex;
  align-items: center;
  text-decoration: none;
}
.sp-nav-logo img {
  height: 2.25rem;
  width: auto;
}
.sp-nav-links {
  display: flex;
  align-items: center;
  gap: 1.5rem;
}
.sp-nav-link {
  background: none;
  border: none;
  cursor: pointer;
  font-size: 0.85rem;
  letter-spacing: 0.08em;
  color: rgba(15, 15, 15, 0.45);
  transition: color 0.3s;
}
.sp-nav-link:hover { color: #0f0f0f; }
.sp-nav-actions {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}
.sp-nav-cta {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 0.6rem 1.25rem;
  background: #1eb48c;
  color: #ffffff;
  border: none;
  border-radius: 999px;
  font-size: 0.85rem;
  font-weight: 500;
  letter-spacing: 0.04em;
  cursor: pointer;
  transition: all 0.35s cubic-bezier(0.25, 1, 0.5, 1);
  box-shadow: 0 2px 12px rgba(30, 180, 140, 0.2);
}
.sp-nav-cta:hover {
  background: #22c99d;
  transform: translateY(-1px);
  box-shadow: 0 4px 16px rgba(30, 180, 140, 0.28);
}
@media (max-width: 640px) {
  .sp-nav-links { display: none; }
  .sp-nav-inner { padding: 0 1rem; }
}
</style>

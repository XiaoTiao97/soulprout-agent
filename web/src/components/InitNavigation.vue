<template>
  <nav class="sp-nav" :class="{ 'sp-nav--scrolled': scrolled }">
    <div class="sp-nav-inner">
      <!-- Logo -->
      <a href="/" class="sp-nav-logo" @click.prevent="scrollToTop">
        <img src="@/assets/images/logo.png" alt="Soulprout" />
      </a>

      <!-- Links -->
      <div class="sp-nav-links">
        <button class="sp-nav-link" @click="scrollTo('capabilities')">能力</button>
        <button class="sp-nav-link" @click="scrollTo('intelligence')">开源</button>
      </div>

      <!-- CTA -->
      <router-link to="/register" class="sp-nav-cta">
        <span>立即体验</span>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
          <path d="M5 12h14M12 5l7 7-7 7" />
        </svg>
      </router-link>
    </div>
  </nav>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'

const scrolled = ref(false)
const onScroll = () => { scrolled.value = window.scrollY > 80 }

onMounted(() => { window.addEventListener('scroll', onScroll, { passive: true }) })
onUnmounted(() => { window.removeEventListener('scroll', onScroll) })

const scrollToTop = () => { window.scrollTo({ top: 0, behavior: 'smooth' }) }
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
  gap: 2.5rem;
}
.sp-nav-link {
  background: none;
  border: none;
  cursor: pointer;
  font-size: 0.875rem;
  font-family: inherit;
  color: rgba(15, 15, 15, 0.5);
  letter-spacing: 0.05em;
  padding: 0;
  transition: color 0.3s;
}
.sp-nav-link:hover { color: #1eb48c; }
.sp-nav-cta {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 0.625rem 1.5rem;
  background: #1eb48c;
  color: #ffffff;
  border-radius: 60px;
  font-size: 0.875rem;
  font-weight: 500;
  letter-spacing: 0.06em;
  text-decoration: none;
  transition: all 0.4s cubic-bezier(0.25, 1, 0.5, 1);
  box-shadow: 0 4px 20px rgba(30, 180, 140, 0.22);
}
.sp-nav-cta:hover {
  background: #22c99d;
  box-shadow: 0 8px 28px rgba(30, 180, 140, 0.30);
  transform: translateY(-2px);
}

@media (max-width: 640px) {
  .sp-nav-links { display: none; }
  .sp-nav-inner { padding: 0 1rem; }
}
</style>

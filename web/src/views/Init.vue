<template>
  <div class="sp-page">
    <!-- Loading Screen：与桌面端开屏一致，Logo + 三个圆点 -->
    <div v-if="!loaded" class="sp-loading">
      <img class="sp-loading-logo" src="@/assets/images/logo.png" alt="Soulprout" />
      <div class="sp-loading-dots" aria-hidden="true"><i></i><i></i><i></i></div>
    </div>

    <!-- Navigation -->
    <InitNavigation />

    <!-- Content -->
    <div v-show="loaded">

      <!-- ── Hero ── -->
      <section class="sp-hero" ref="heroSectionRef">
        <OrbScene v-if="heroInView" />
        <GrowingParticles v-if="heroInView" />

        <div class="sp-hero-inner">
          <div class="sp-hero-logo">
            <img src="@/assets/images/logo.png" alt="Soulprout" />
          </div>

          <h1 class="sp-hero-title">
            <span class="sp-reveal-wrap" ref="heroTitleRef">
              <span class="sp-reveal-text">{{ t('init.heroTitle') }}</span>
            </span>
          </h1>

          <p class="sp-hero-sub">
            {{ t('init.heroSub') }}
          </p>

          <div class="sp-hero-actions">
            <button class="sp-cta-btn" @click="handleStart">
              <span>{{ t('nav.start') }}</span>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                <path d="M5 12h14M12 5l7 7-7 7" />
              </svg>
            </button>
            <button class="sp-explore-btn" @click="scrollTo('capabilities')">
              {{ t('init.exploreMore') }}
            </button>
          </div>
        </div>
      </section>

      <!-- ── Scenes ── -->
      <section id="scenes" class="sp-scenes-section">
        <div class="sp-scenes-inner">
          <header class="sp-scenes-head">
            <p class="sp-section-eyebrow">{{ t('init.scenesEyebrow') }}</p>
            <h2 class="sp-section-title sp-scenes-title">
              <span class="sp-reveal-wrap" ref="scenesTitleRef">
                <span class="sp-reveal-text">{{ t('init.scenesTitle') }}</span>
              </span>
            </h2>
          </header>

          <div
            class="sp-scenes-stage"
            @mouseenter="pauseScenes"
            @mouseleave="resumeScenes"
          >
            <article
              v-for="(scene, index) in scenes"
              :key="scene.key"
              class="sp-scene-card"
              :class="{ 'is-active': index === activeSceneIndex, 'is-dark': scene.key === 'nearby' }"
              :style="sceneCardStyle(index)"
              :aria-hidden="index !== activeSceneIndex"
              @click="setScene(index)"
            >
              <div class="sp-scene-media">
                <img :src="sceneImages[scene.key]" :alt="scene.title" loading="lazy" draggable="false" />
                <span class="sp-scene-tag">{{ scene.tag }}</span>
                <p v-if="scene.say" class="sp-scene-say">{{ scene.say }}</p>
              </div>
              <div class="sp-scene-body">
                <h3 class="sp-scene-title">{{ scene.title }}</h3>
              </div>
            </article>
          </div>

          <div
            class="sp-scene-timer"
            :class="{ 'is-paused': scenesPaused }"
            :key="sceneBarKey"
          >
            <span class="sp-scene-timer-bar" :style="{ animationDuration: SCENE_AUTOPLAY_MS + 'ms' }" />
          </div>

          <div
            class="sp-scenes-controls"
            @mouseenter="pauseScenes"
            @mouseleave="resumeScenes"
          >
            <button
              type="button"
              class="sp-scenes-nav"
              :aria-label="t('init.scenesPrev')"
              :disabled="!canScenePrev"
              @click="setScene(activeSceneIndex - 1)"
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M15 18l-6-6 6-6" stroke-linecap="round" stroke-linejoin="round" />
              </svg>
            </button>
            <div class="sp-scenes-progress">
              <button
                v-for="(scene, index) in scenes"
                :key="scene.key"
                type="button"
                class="sp-scenes-dot"
                :class="{ 'is-active': activeSceneIndex === index }"
                :aria-label="scene.title"
                @click="setScene(index)"
              />
            </div>
            <button
              type="button"
              class="sp-scenes-nav"
              :aria-label="t('init.scenesNext')"
              :disabled="!canSceneNext"
              @click="setScene(activeSceneIndex + 1)"
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M9 6l6 6-6 6" stroke-linecap="round" stroke-linejoin="round" />
              </svg>
            </button>
          </div>
        </div>
      </section>

      <!-- ── Core Capabilities ── -->
      <section id="capabilities" class="sp-caps-section">
        <div class="sp-caps-bg-radial" />
        <div class="sp-caps-ring sp-caps-ring-lg" />
        <div class="sp-caps-ring sp-caps-ring-sm" />

        <div class="sp-caps-inner">
          <div class="sp-section-header sp-caps-header">
            <p class="sp-section-eyebrow">{{ t('init.capsEyebrow') }}</p>
            <h2 class="sp-section-title">
              <span class="sp-reveal-wrap" ref="capTitleRef">
                <span class="sp-reveal-text">{{ t('init.capsTitle') }}</span>
              </span>
            </h2>
          </div>

          <div class="sp-caps-stage">
            <article
              v-for="(group, gi) in featureGroups"
              :key="group.key"
              class="sp-caps-panel"
              :class="gi === 0 ? 'is-left' : 'is-right'"
            >
              <header class="sp-caps-group-head">
                <span class="sp-caps-group-label">{{ group.label }}</span>
                <h3 class="sp-caps-group-title">{{ group.title }}</h3>
                <span class="sp-caps-group-rule" />
              </header>
              <div
                v-for="(f, ii) in group.items"
                :key="group.key + '-' + ii"
                class="sp-cap-item"
                :style="{ transitionDelay: (ii * 70 + gi * 40) + 'ms' }"
              >
                <h4 class="sp-cap-title">{{ f.title }}</h4>
                <p class="sp-cap-desc" v-html="f.descHtml"></p>
              </div>
            </article>
          </div>
        </div>
      </section>

      <!-- ── Multi-Platform Connectivity ── -->
      <section id="connectivity" class="sp-connect-section">
        <div class="sp-connect-bg-radial" />

        <div class="sp-connect-inner">
          <div class="sp-section-header">
            <p class="sp-section-eyebrow">{{ t('init.connectEyebrow') }}</p>
            <h2 class="sp-section-title">
              <span class="sp-reveal-wrap" ref="connectTitleRef">
                <span class="sp-reveal-text">{{ t('init.connectTitle') }}</span>
              </span>
            </h2>
          </div>

          <div class="sp-connect-split">
            <article class="sp-connect-col">
              <header class="sp-connect-col-head">
                <span class="sp-connect-col-index">01</span>
                <div>
                  <p class="sp-connect-col-label">{{ t('init.connectClientsLabel') }}</p>
                  <h3 class="sp-connect-col-title">{{ t('init.connectClientsTitle') }}</h3>
                </div>
              </header>

              <ul class="sp-connect-clients">
                <li
                  v-for="item in connectClients"
                  :key="item.key"
                  class="sp-connect-client"
                >
                  <div class="sp-connect-client-icon" aria-hidden="true">
                    <svg v-if="item.key === 'web'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7">
                      <path d="M7.2 18h9.6a4 4 0 0 0 .4-8 5.5 5.5 0 0 0-10.5-1.4A3.6 3.6 0 0 0 7.2 18z" stroke-linejoin="round" />
                    </svg>
                    <svg v-else-if="item.key === 'desktop'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7">
                      <rect x="3.5" y="4" width="17" height="11.5" rx="1.6" />
                      <path d="M8 20h8M12 15.5V20" stroke-linecap="round" />
                    </svg>
                    <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7">
                      <rect x="7.5" y="3" width="9" height="18" rx="2" />
                      <path d="M11 18.5h2" stroke-linecap="round" />
                    </svg>
                  </div>
                  <div class="sp-connect-client-body">
                    <div class="sp-connect-client-top">
                      <h4>{{ item.name }}</h4>
                      <span>{{ item.tag }}</span>
                    </div>
                    <p>{{ item.desc }}</p>
                  </div>
                </li>
              </ul>
            </article>

            <article class="sp-connect-col">
              <header class="sp-connect-col-head">
                <span class="sp-connect-col-index">02</span>
                <div>
                  <p class="sp-connect-col-label">{{ t('init.connectChannelsLabel') }}</p>
                  <h3 class="sp-connect-col-title">{{ t('init.connectChannelsTitle') }}</h3>
                </div>
              </header>

              <p class="sp-connect-channels-desc">{{ t('init.connectChannelsDesc') }}</p>

              <div class="sp-connect-chips">
                <span
                  v-for="platform in connectPlatforms"
                  :key="platform"
                  class="sp-connect-chip"
                >{{ connectPlatformNames[platform] }}</span>
              </div>

              <div class="sp-connect-ways">
                <p class="sp-connect-ways-title">{{ t('init.connectWaysTitle') }}</p>
                <div
                  v-for="(way, index) in connectChannelWays"
                  :key="way.key"
                  class="sp-connect-way"
                >
                  <span class="sp-connect-way-num">{{ String(index + 1).padStart(2, '0') }}</span>
                  <div>
                    <strong>{{ way.name }}</strong>
                    <p>{{ way.desc }}</p>
                  </div>
                </div>
              </div>
            </article>
          </div>

          <p class="sp-connect-note">{{ t('init.connectWindowsNote') }}</p>

          <button type="button" class="sp-cta-btn" @click="openDownloadClients">
            <span>{{ t('init.connectDownload') }}</span>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" aria-hidden="true">
              <path d="M12 3v12" stroke-linecap="round" />
              <path d="M8 11l4 4 4-4" stroke-linecap="round" stroke-linejoin="round" />
              <path d="M4 17v2a2 2 0 002 2h12a2 2 0 002-2v-2" stroke-linecap="round" />
            </svg>
          </button>

          <p class="sp-connect-hint">{{ t('init.connectDownloadSub') }}</p>
        </div>
      </section>

      <!-- ── Open Source ── -->
      <section id="intelligence" class="sp-oss-section">
        <div class="sp-oss-bg-radial" />

        <div class="sp-oss-inner">
          <p class="sp-section-eyebrow">{{ t('init.ossEyebrow') }}</p>

          <h2 class="sp-section-title sp-oss-title">
            <span class="sp-reveal-wrap" ref="openTitleRef">
              <span class="sp-reveal-text">{{ t('init.ossTitle') }}</span>
            </span>
          </h2>

          <p class="sp-oss-desc">
            {{ t('init.ossDesc') }}
          </p>

          <a
            href="https://github.com/XiaoTiao97/soulprout-agent"
            target="_blank"
            rel="noopener noreferrer"
            class="sp-github-card"
          >
            <svg class="sp-github-icon" width="32" height="32" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z" />
            </svg>
            <div class="sp-github-info">
              <span class="sp-github-label">{{ t('init.githubLabel') }}</span>
              <span class="sp-github-repo">XiaoTiao97 / soulprout-agent</span>
            </div>
            <svg class="sp-github-arrow" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M7 17L17 7M17 7H7M17 7V17" />
            </svg>
          </a>

          <div class="sp-stats-row">
            <div class="sp-stat">
              <span class="sp-stat-num">0</span>
              <span class="sp-stat-label">{{ t('init.statStars') }}</span>
            </div>
            <div class="sp-stat-divider" />
            <div class="sp-stat">
              <span class="sp-stat-num">MIT</span>
              <span class="sp-stat-label">{{ t('init.statLicense') }}</span>
            </div>
            <div class="sp-stat-divider" />
            <div class="sp-stat">
              <span class="sp-stat-num">Zero</span>
              <span class="sp-stat-label">{{ t('init.statCodeNeeded') }}</span>
            </div>
          </div>
        </div>
      </section>

      <!-- ── Footer ── -->
      <footer class="sp-footer">
        <div class="sp-footer-top-line" />
        <div class="sp-footer-inner">
          <div class="sp-footer-main">
            <img src="@/assets/images/logo.png" alt="Soulprout" class="sp-footer-logo" />
            <p class="sp-footer-tagline">{{ t('init.footerTagline') }}</p>
            <button class="sp-cta-btn" @click="handleStart">
              <span>{{ t('nav.start') }}</span>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                <path d="M5 12h14M12 5l7 7-7 7" />
              </svg>
            </button>
          </div>
          <div class="sp-footer-bottom">
            <p class="sp-footer-copy">&copy; {{ copyrightYear }} Soulprout. All rights reserved.</p>
            <div class="sp-footer-links">
              <a href="https://github.com/XiaoTiao97/soulprout-agent" target="_blank" rel="noopener noreferrer" class="sp-footer-link">GitHub</a>
              <button type="button" class="sp-footer-link" @click="openContact">{{ t('init.footerContact') }}</button>
              <a
                class="sp-footer-beian"
                href="https://beian.miit.gov.cn/"
                target="_blank"
                rel="noopener noreferrer"
              >{{ t('init.footerBeian') }}</a>
            </div>
          </div>
        </div>
      </footer>

    </div>

    <DownloadClientsDialog v-model="showDownloadClients" />

    <Teleport to="body">
      <div v-if="showContact" class="sp-contact-mask" @mousedown.self="closeContact">
        <div class="sp-contact-dialog" role="dialog" aria-modal="true" :aria-label="t('init.footerContact')">
          <header class="sp-contact-head">
            <div class="sp-contact-head-text">
              <strong>{{ t('init.footerContact') }}</strong>
              <span>{{ t('init.contactHint') }}</span>
            </div>
            <button type="button" class="sp-contact-close" :aria-label="t('init.contactClose')" @click="closeContact">×</button>
          </header>
          <div class="sp-contact-body">
            <img class="sp-contact-qr" :src="contactQrUrl" :alt="t('init.contactQrAlt')" />
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { startExperience } from '@/utils/startExperience.js'
import InitNavigation from '@/components/InitNavigation.vue'
import OrbScene from '@/components/OrbScene.vue'
import GrowingParticles from '@/components/GrowingParticles.vue'
import DownloadClientsDialog from '@/components/DownloadClientsDialog.vue'
import contactQrUrl from '@/assets/docs-images/weixinhao.jpg'
import sceneDevices from '@/assets/scenes/scene-devices.svg'
import sceneMemory from '@/assets/scenes/scene-memory.svg'
import sceneWork from '@/assets/scenes/scene-work.svg'
import sceneEarphone from '@/assets/images/earphone.png'
import sceneDiy from '@/assets/images/diy.png'

const sceneImages = {
  'whole-day': sceneDiy,
  'all-devices': sceneDevices,
  remembers: sceneMemory,
  'does-work': sceneWork,
  nearby: sceneEarphone,
}

const router = useRouter()
const { t, tm } = useI18n()

const copyrightYear = new Date().getFullYear()
const showDownloadClients = ref(false)
const showContact = ref(false)
const loaded = ref(false)
const heroInView = ref(true)
const heroSectionRef = ref(null)
const heroTitleRef = ref(null)
const capTitleRef = ref(null)
const connectTitleRef = ref(null)
const scenesTitleRef = ref(null)
const openTitleRef = ref(null)
const featureGroups = computed(() => {
  const groups = tm('init.featureGroups')
  const list = Array.isArray(groups) ? groups : []
  return list.map((g) => ({
    key: g.key,
    label: g.label ?? '',
    title: g.title,
    items: (g.items || []).map((item) => ({
      title: item.title ?? '',
      descHtml: renderBold(item.desc ?? ''),
    })),
  }))
})

function renderBold(text) {
  const escaped = String(text)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
  return escaped.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
}


const connectClients = computed(() => {
  const list = tm('init.connectClients')
  return Array.isArray(list) ? list : []
})

const connectChannelWays = computed(() => {
  const list = tm('init.connectChannelWays')
  return Array.isArray(list) ? list : []
})

const connectPlatforms = ['wechat', 'feishu', 'wework', 'xiaoai', 'rokid']

const connectPlatformNames = computed(() => ({
  wechat: t('chatWindow.channels.wechat'),
  feishu: t('chatWindow.channels.feishu'),
  wework: t('chatWindow.channels.wework'),
  xiaoai: t('chatWindow.channels.xiaoai'),
  rokid: t('chatWindow.channels.rokid'),
}))

const scenes = computed(() => {
  const list = tm('init.scenesList')
  return Array.isArray(list) ? list : []
})

const activeSceneIndex = ref(0)
const canScenePrev = computed(() => activeSceneIndex.value > 0)
const canSceneNext = computed(() => activeSceneIndex.value < scenes.value.length - 1)

const SCENE_AUTOPLAY_MS = 4500
let sceneTimer = null
let sceneStartedAt = 0
let sceneRemaining = SCENE_AUTOPLAY_MS
const scenesPaused = ref(false)
const sceneBarKey = ref(0)

function stopSceneTimer() {
  if (sceneTimer) {
    clearTimeout(sceneTimer)
    sceneTimer = null
  }
}
function armSceneTimer(ms) {
  stopSceneTimer()
  if (scenesPaused.value) return
  sceneStartedAt = Date.now()
  sceneTimer = setTimeout(() => {
    const len = scenes.value.length
    if (!len) return
    activeSceneIndex.value = (activeSceneIndex.value + 1) % len
    sceneRemaining = SCENE_AUTOPLAY_MS
    sceneBarKey.value += 1
    armSceneTimer(SCENE_AUTOPLAY_MS)
  }, ms)
}
function setScene(index) {
  const max = scenes.value.length - 1
  activeSceneIndex.value = Math.min(Math.max(index, 0), max)
  sceneRemaining = SCENE_AUTOPLAY_MS
  sceneBarKey.value += 1
  armSceneTimer(SCENE_AUTOPLAY_MS)
}
function pauseScenes() {
  if (scenesPaused.value) return
  scenesPaused.value = true
  if (sceneTimer) {
    sceneRemaining = Math.max(80, sceneRemaining - (Date.now() - sceneStartedAt))
    stopSceneTimer()
  }
}
function resumeScenes() {
  scenesPaused.value = false
  armSceneTimer(sceneRemaining)
}

// 3D 卡组：当前卡居中放大，两侧卡片后退、缩小、微转，营造前后叠加的纵深感
function sceneCardStyle(index) {
  const offset = index - activeSceneIndex.value
  const abs = Math.abs(offset)
  if (abs > 2) {
    return {
      transform: `translateX(-50%) translateX(${Math.sign(offset) * 140}%) translateZ(-640px) scale(0.58)`,
      opacity: 0,
      zIndex: 0,
      visibility: 'hidden',
      pointerEvents: 'none',
    }
  }
  const presets = {
    0: { x: 0, z: 0, scale: 1, rotate: 0, opacity: 1, zIndex: 30 },
    1: { x: 60, z: -230, scale: 0.85, rotate: 9, opacity: 0.72, zIndex: 20 },
    2: { x: 102, z: -440, scale: 0.72, rotate: 13, opacity: 0.35, zIndex: 10 },
  }
  const cfg = presets[abs]
  const dir = Math.sign(offset)
  return {
    transform:
      `translateX(-50%) translateX(${dir * cfg.x}%) ` +
      `translateZ(${cfg.z}px) rotateY(${dir * -cfg.rotate}deg) scale(${cfg.scale})`,
    opacity: cfg.opacity,
    zIndex: cfg.zIndex,
  }
}

function openDownloadClients() {
  showDownloadClients.value = true
}

function openContact() {
  showContact.value = true
}

function closeContact() {
  showContact.value = false
}

function onContactKeydown(event) {
  if (event.key === 'Escape') closeContact()
}

let heroObserver = null

onMounted(() => {
  window.addEventListener('keydown', onContactKeydown)
  setTimeout(() => { loaded.value = true }, 2000)

  if (heroSectionRef.value) {
    heroObserver = new IntersectionObserver(
      ([entry]) => {
        heroInView.value = entry.isIntersecting
      },
      { rootMargin: '100px 0px' },
    )
    heroObserver.observe(heroSectionRef.value)
  }

  const revealObs = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add('is-inview')
          revealObs.unobserve(entry.target)
        }
      })
    },
    { threshold: 0.2 }
  )
  ;[heroTitleRef.value, capTitleRef.value, connectTitleRef.value, openTitleRef.value, scenesTitleRef.value].forEach(el => {
    if (el) revealObs.observe(el)
  })

  const cardObs = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add('is-visible')
          cardObs.unobserve(entry.target)
        }
      })
    },
    { threshold: 0.05, rootMargin: '0px 0px -60px 0px' }
  )
  document.querySelectorAll('.sp-cap-item').forEach(el => cardObs.observe(el))
  armSceneTimer(SCENE_AUTOPLAY_MS)
})

onUnmounted(() => {
  window.removeEventListener('keydown', onContactKeydown)
  heroObserver?.disconnect()
  stopSceneTimer()
})

function handleStart() {
  startExperience(router)
}

const scrollTo = (id) => {
  const el = document.getElementById(id)
  if (el) el.scrollIntoView({ behavior: 'smooth' })
}
</script>

<style scoped>
/* ─── Base ─────────────────────────────── */
.sp-page {
  font-family: 'Noto Sans SC', 'PingFang SC', -apple-system, BlinkMacSystemFont, sans-serif;
  color: #0f0f0f;
  background: #ffffff;
  overflow-x: hidden;
}

/* ─── Loading（对齐桌面端 splash） ───────── */
.sp-loading {
  position: fixed;
  inset: 0;
  z-index: 9999;
  background: rgb(242, 242, 242);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 28px;
  animation: spLoadFade 0.6s ease 1.8s forwards;
}
@keyframes spLoadFade {
  from { opacity: 1; }
  to   { opacity: 0; pointer-events: none; }
}
.sp-loading-logo {
  width: min(360px, 62vw);
  height: auto;
  display: block;
}
.sp-loading-dots {
  display: flex;
  gap: 8px;
  height: 12px;
  align-items: center;
}
.sp-loading-dots i {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #16a34a;
  opacity: 0.25;
  animation: spLoadPulse 1.2s infinite ease-in-out;
}
.sp-loading-dots i:nth-child(2) { animation-delay: 0.2s; }
.sp-loading-dots i:nth-child(3) { animation-delay: 0.4s; }
@keyframes spLoadPulse {
  0%, 100% { opacity: 0.25; transform: scale(0.85); }
  50% { opacity: 1; transform: scale(1.15); }
}

/* ─── Reveal text ──────────────────────── */
.sp-reveal-wrap {
  position: relative;
  display: inline-block;
  overflow: hidden;
}
.sp-reveal-text {
  display: block;
  white-space: nowrap;
  opacity: 0;
  transform: translateY(24px);
  transition: opacity 1s cubic-bezier(0.25, 1, 0.5, 1),
              transform 1s cubic-bezier(0.25, 1, 0.5, 1);
}
.sp-reveal-wrap.is-inview .sp-reveal-text {
  opacity: 1;
  transform: translateY(0);
}

/* ─── CTA Button ───────────────────────── */
.sp-cta-btn {
  display: inline-flex;
  align-items: center;
  gap: 12px;
  padding: 16px 40px;
  background: #1eb48c;
  color: #ffffff;
  border: none;
  border-radius: 60px;
  font-size: 16px;
  font-weight: 500;
  letter-spacing: 0.06em;
  text-decoration: none;
  cursor: pointer;
  transition: all 0.4s cubic-bezier(0.25, 1, 0.5, 1);
  box-shadow: 0 4px 20px rgba(30, 180, 140, 0.22);
}
.sp-cta-btn:hover {
  background: #22c99d;
  box-shadow: 0 8px 28px rgba(30, 180, 140, 0.30);
  transform: translateY(-2px);
}

/* ─── Hero ─────────────────────────────── */
.sp-hero {
  position: relative;
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  background: #ffffff;
}
.sp-hero-inner {
  position: relative;
  z-index: 20;
  text-align: center;
  padding: 0 1rem;
}
.sp-hero-logo {
  margin-bottom: 1.5rem;
}
.sp-hero-logo img {
  height: 72px;
  width: auto;
  display: inline-block;
}
.sp-hero-title {
  font-size: clamp(48px, 8vw, 78px);
  font-weight: 700;
  letter-spacing: -0.025em;
  line-height: 1;
  color: #0f0f0f;
  margin: 0 0 2rem;
}
.sp-hero-sub {
  font-size: clamp(1rem, 2vw, 1.375rem);
  font-weight: 300;
  color: rgba(15, 15, 15, 0.5);
  max-width: 680px;
  margin: 0 auto 3rem;
  line-height: 1.7;
  letter-spacing: 0.02em;
}
.sp-hero-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: center;
  gap: 1.5rem;
}
.sp-explore-btn {
  background: none;
  border: none;
  cursor: pointer;
  font-size: 0.8rem;
  letter-spacing: 0.2em;
  color: rgba(15, 15, 15, 0.3);
  transition: color 0.3s;
  padding: 0;
}
.sp-explore-btn:hover { color: #1eb48c; }

/* ─── Section common ───────────────────── */
.sp-section-header {
  text-align: center;
  margin-bottom: 4rem;
}
.sp-section-eyebrow {
  font-size: 11px;
  letter-spacing: 0.4em;
  text-transform: uppercase;
  color: rgba(30, 180, 140, 0.5);
  font-weight: 300;
  margin: 0 0 1.25rem;
}
.sp-section-title {
  font-size: clamp(40px, 7vw, 72px);
  font-weight: 700;
  color: #0f0f0f;
  letter-spacing: -0.025em;
  margin: 0;
  line-height: 1;
}

/* ─── Scenes ───────────────────────────── */
.sp-scenes-section {
  --scene-card: min(740px, 82vw);
  position: relative;
  padding: 9rem 1.5rem 7.5rem;
  overflow: hidden;
  background: #fbfbfb;
}
.sp-scenes-inner {
  position: relative;
  z-index: 10;
  max-width: 1180px;
  margin: 0 auto;
}
.sp-scenes-head {
  text-align: center;
  margin-bottom: 3.5rem;
}
.sp-scenes-head .sp-section-eyebrow {
  margin: 0 0 1rem;
}
.sp-scenes-title {
  font-size: clamp(40px, 6vw, 68px);
}
/* 3D 卡组舞台 */
.sp-scenes-stage {
  position: relative;
  height: calc(var(--scene-card) * 0.75 + 92px);
  perspective: 1700px;
  transform-style: preserve-3d;
}
.sp-scene-card {
  position: absolute;
  top: 0;
  left: 50%;
  width: var(--scene-card);
  display: flex;
  flex-direction: column;
  background: transparent;
  border: none;
  overflow: visible;
  box-shadow: none;
  cursor: pointer;
  user-select: none;
  transform-style: preserve-3d;
  transition: transform 0.7s cubic-bezier(0.25, 1, 0.5, 1),
              opacity 0.7s cubic-bezier(0.25, 1, 0.5, 1),
              visibility 0.7s,
              box-shadow 0.4s;
  will-change: transform, opacity;
  height: 100%;
}
.sp-scene-card.is-active {
  cursor: default;
}
.sp-scene-media {
  position: relative;
  flex: 1;
  min-height: 0;
  background: #f4f3f1;
  overflow: hidden;
  border: 1px solid rgba(15, 15, 15, 0.07);
  border-radius: 1.75rem;
  box-shadow: 0 24px 70px rgba(15, 15, 15, 0.1);
}
.sp-scene-card.is-active .sp-scene-media {
  box-shadow: 0 30px 80px rgba(15, 15, 15, 0.13);
}
.sp-scene-media img {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.sp-scene-tag {
  position: absolute;
  top: 18px;
  left: 18px;
  font-size: 12px;
  font-weight: 500;
  letter-spacing: 0.1em;
  color: #0f7a5e;
  background: rgba(255, 255, 255, 0.82);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  border-radius: 999px;
  padding: 0.35rem 0.85rem;
  box-shadow: 0 2px 10px rgba(15, 15, 15, 0.06);
}
.sp-scene-say {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 1.35rem;
  margin: 0;
  text-align: center;
  font-size: 1.15rem;
  font-weight: 400;
  letter-spacing: 0.18em;
  color: #fff;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.85), 0 0 12px rgba(0, 0, 0, 0.35);
}
.sp-scene-card.is-dark .sp-scene-media img {
  object-position: 38% center;
}
.sp-scene-body {
  flex: none;
  padding: 1.15rem 0.5rem 0;
  text-align: center;
  background: transparent;
}
.sp-scene-title {
  margin: 0;
  font-size: 1.35rem;
  font-weight: 400;
  line-height: 1.45;
  color: #0f0f0f;
  letter-spacing: -0.02em;
}
.sp-scene-timer {
  width: 120px;
  height: 2px;
  margin: 1.35rem auto 0;
  background: rgba(15, 15, 15, 0.08);
  border-radius: 2px;
  overflow: hidden;
}
.sp-scene-timer-bar {
  display: block;
  height: 100%;
  width: 0;
  background: #1eb48c;
  animation-name: spSceneTimer;
  animation-timing-function: linear;
  animation-fill-mode: forwards;
}
.sp-scene-timer.is-paused .sp-scene-timer-bar {
  animation-play-state: paused;
}
@keyframes spSceneTimer {
  from { width: 0; }
  to { width: 100%; }
}

/* 控制条：箭头 + 小圆点 */
.sp-scenes-controls {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 1.5rem;
  margin-top: 2.5rem;
}
.sp-scenes-nav {
  width: 44px;
  height: 44px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  border: 1px solid rgba(15, 15, 15, 0.12);
  background: #ffffff;
  color: rgba(15, 15, 15, 0.6);
  cursor: pointer;
  transition: all 0.25s;
}
.sp-scenes-nav:hover:not(:disabled) {
  background: #1eb48c;
  border-color: #1eb48c;
  color: #ffffff;
}
.sp-scenes-nav:disabled {
  opacity: 0.3;
  cursor: default;
}
.sp-scenes-progress {
  display: flex;
  justify-content: center;
  gap: 0.55rem;
}
.sp-scenes-dot {
  width: 7px;
  height: 7px;
  padding: 0;
  border: none;
  border-radius: 50%;
  background: rgba(15, 15, 15, 0.12);
  cursor: pointer;
  transition: all 0.25s;
}
.sp-scenes-dot:hover { background: rgba(30, 180, 140, 0.45); }
.sp-scenes-dot.is-active {
  background: #1eb48c;
  transform: scale(1.25);
}

/* ─── Capabilities ─────────────────────── */
.sp-caps-section {
  position: relative;
  padding: 9rem 1.5rem;
  overflow: hidden;
  background: #ffffff;
}
.sp-caps-bg-radial {
  position: absolute;
  inset: 0;
  pointer-events: none;
  background: radial-gradient(ellipse 80% 60% at 50% 50%, #f0f7f7 0%, #ffffff 70%);
}
.sp-caps-ring {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  border-radius: 50%;
  pointer-events: none;
}
.sp-caps-ring-lg {
  width: 800px;
  height: 800px;
  border: 1px solid rgba(30, 180, 140, 0.04);
}
.sp-caps-ring-sm {
  width: 500px;
  height: 500px;
  border: 1px solid rgba(30, 180, 140, 0.06);
}
.sp-caps-inner {
  position: relative;
  z-index: 10;
  max-width: 1080px;
  margin: 0 auto;
}

.sp-caps-header {
  margin-bottom: 5.5rem;
}
.sp-caps-stage {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 2.25rem;
}
.sp-caps-panel {
  position: relative;
  isolation: isolate;
  padding: 2.4rem 2.2rem 1.6rem;
  border-radius: 1.75rem;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.96) 0%, rgba(248, 250, 249, 0.94) 100%);
  border: 1px solid rgba(15, 15, 15, 0.06);
  box-shadow:
    0 28px 60px rgba(15, 15, 15, 0.1),
    0 2px 0 rgba(255, 255, 255, 0.8) inset;
  transition: transform 0.6s cubic-bezier(0.25, 1, 0.5, 1),
              box-shadow 0.6s cubic-bezier(0.25, 1, 0.5, 1);
}
.sp-caps-panel::before {
  content: '';
  position: absolute;
  z-index: -1;
  inset: 0;
  border-radius: inherit;
  pointer-events: none;
  background: linear-gradient(
    135deg,
    rgba(255, 255, 255, 0.55) 0%,
    rgba(255, 255, 255, 0) 42%
  );
}
.sp-caps-panel:hover {
  transform: translateY(-8px);
  box-shadow:
    0 38px 80px rgba(15, 15, 15, 0.14),
    0 2px 0 rgba(255, 255, 255, 0.85) inset;
}
.sp-caps-group-head {
  padding-bottom: 1.5rem;
}
.sp-caps-group-label {
  display: block;
  margin-bottom: 0.9rem;
  font-size: 11px;
  font-weight: 500;
  letter-spacing: 0.32em;
  text-transform: uppercase;
  color: #1eb48c;
}
.sp-caps-group-title {
  margin: 0;
  font-size: clamp(2.25rem, 4vw, 3.25rem);
  font-weight: 700;
  letter-spacing: -0.02em;
  color: #0f0f0f;
  line-height: 1.05;
}
.sp-caps-group-rule {
  display: block;
  width: 2rem;
  height: 2px;
  margin-top: 1.5rem;
  background: #1eb48c;
  border-radius: 2px;
}
.sp-cap-item {
  box-sizing: border-box;
  padding-top: 1.6rem;
  padding-bottom: 1.6rem;
  border-top: 1px solid rgba(15, 15, 15, 0.08);
  opacity: 0;
  transform: translateY(14px);
  transition: opacity 0.7s cubic-bezier(0.25, 1, 0.5, 1),
              transform 0.7s cubic-bezier(0.25, 1, 0.5, 1);
}
.sp-cap-item.is-visible {
  opacity: 1;
  transform: translateY(0);
}
.sp-cap-title {
  margin: 0 0 0.55rem;
  font-size: 1.15rem;
  font-weight: 600;
  letter-spacing: 0;
  color: #0f0f0f;
  line-height: 1.35;
  transition: color 0.3s;
}
.sp-cap-item:hover .sp-cap-title { color: #1eb48c; }
.sp-cap-desc {
  margin: 0;
  font-size: 0.975rem;
  font-weight: 400;
  line-height: 1.75;
  color: rgba(15, 15, 15, 0.66);
}
.sp-cap-desc :deep(strong) {
  font-weight: 600;
  color: #17a27d;
}

/* ─── Connectivity ─────────────────────── */
.sp-connect-section {
  position: relative;
  padding: 9rem 1.5rem;
  overflow: hidden;
  background: #f8f8f8;
  content-visibility: auto;
  contain-intrinsic-size: auto 980px;
}
.sp-connect-bg-radial {
  position: absolute;
  inset: 0;
  pointer-events: none;
  background: radial-gradient(ellipse 60% 50% at 50% 50%, rgba(30,180,140,0.03) 0%, transparent 70%);
}
.sp-connect-inner {
  position: relative;
  z-index: 10;
  max-width: 1080px;
  margin: 0 auto;
  text-align: center;
}
.sp-connect-inner .sp-section-header {
  margin-bottom: 0;
}
.sp-connect-split {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1.25rem;
  margin: 4.5rem 0 2.75rem;
  text-align: left;
  align-items: stretch;
}
.sp-connect-col {
  display: flex;
  flex-direction: column;
  min-width: 0;
  background: #ffffff;
  border: 1px solid rgba(15, 15, 15, 0.06);
  border-radius: 1.25rem;
  padding: 2rem 1.85rem 1.85rem;
  box-shadow: 0 10px 40px rgba(15, 15, 15, 0.03);
}
.sp-connect-col-head {
  display: flex;
  align-items: flex-start;
  gap: 1rem;
  margin-bottom: 1.75rem;
}
.sp-connect-col-index {
  font-size: 0.75rem;
  font-weight: 600;
  letter-spacing: 0.16em;
  color: #1eb48c;
  padding-top: 0.35rem;
}
.sp-connect-col-label {
  margin: 0 0 0.4rem;
  font-size: 11px;
  font-weight: 500;
  letter-spacing: 0.28em;
  text-transform: uppercase;
  color: rgba(30, 180, 140, 0.7);
}
.sp-connect-col-title {
  margin: 0;
  font-size: 1.55rem;
  font-weight: 700;
  letter-spacing: -0.03em;
  line-height: 1.2;
  color: #0f0f0f;
}
.sp-connect-clients {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  flex: 1;
}
.sp-connect-client {
  display: grid;
  grid-template-columns: 44px 1fr;
  gap: 1rem;
  align-items: flex-start;
  padding: 1.2rem 0;
  border-top: 1px solid rgba(15, 15, 15, 0.07);
}
.sp-connect-client:first-child {
  padding-top: 0;
  border-top: none;
}
.sp-connect-client-icon {
  width: 44px;
  height: 44px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 12px;
  background: rgba(30, 180, 140, 0.08);
  color: #17a27d;
  flex-shrink: 0;
}
.sp-connect-client-icon svg {
  width: 20px;
  height: 20px;
}
.sp-connect-client-body {
  min-width: 0;
}
.sp-connect-client-top {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.55rem;
  margin-bottom: 0.45rem;
}
.sp-connect-client-top h4 {
  margin: 0;
  font-size: 1.05rem;
  font-weight: 600;
  color: #0f0f0f;
}
.sp-connect-client-top span {
  font-size: 11px;
  letter-spacing: 0.04em;
  color: #148f72;
  background: rgba(30, 180, 140, 0.08);
  border-radius: 999px;
  padding: 0.18rem 0.55rem;
}
.sp-connect-client-body p {
  margin: 0;
  font-size: 0.925rem;
  line-height: 1.75;
  color: rgba(15, 15, 15, 0.62);
  overflow-wrap: break-word;
}
.sp-connect-channels-desc {
  margin: 0 0 1.25rem;
  font-size: 0.95rem;
  line-height: 1.8;
  color: rgba(15, 15, 15, 0.62);
  overflow-wrap: break-word;
}
.sp-connect-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}
.sp-connect-chip {
  font-size: 0.8rem;
  line-height: 1;
  padding: 0.55rem 0.85rem;
  border-radius: 999px;
  border: 1px solid rgba(30, 180, 140, 0.16);
  background: rgba(30, 180, 140, 0.05);
  color: #148f72;
  transition: background 0.25s, border-color 0.25s;
}
.sp-connect-chip:hover {
  background: rgba(30, 180, 140, 0.12);
  border-color: rgba(30, 180, 140, 0.3);
}
.sp-connect-ways {
  margin-top: auto;
  padding-top: 1.5rem;
}
.sp-connect-ways-title {
  margin: 0 0 0.85rem;
  font-size: 11px;
  font-weight: 500;
  letter-spacing: 0.22em;
  text-transform: uppercase;
  color: rgba(15, 15, 15, 0.35);
}
.sp-connect-way {
  display: grid;
  grid-template-columns: 2rem 1fr;
  gap: 0.75rem;
  padding: 0.95rem 1rem;
  border-radius: 0.9rem;
  background: #f7faf9;
}
.sp-connect-way + .sp-connect-way {
  margin-top: 0.65rem;
}
.sp-connect-way-num {
  font-size: 0.72rem;
  font-weight: 600;
  letter-spacing: 0.12em;
  color: #1eb48c;
  padding-top: 0.15rem;
}
.sp-connect-way strong {
  display: block;
  margin-bottom: 0.3rem;
  font-size: 0.95rem;
  font-weight: 600;
  color: #0f0f0f;
}
.sp-connect-way p {
  margin: 0;
  font-size: 0.875rem;
  line-height: 1.7;
  color: rgba(15, 15, 15, 0.58);
}
.sp-connect-note {
  margin: 0 0 1.75rem;
  font-size: 0.75rem;
  letter-spacing: 0.08em;
  color: rgba(15, 15, 15, 0.35);
}
.sp-connect-hint {
  margin: 1.25rem 0 0;
  font-size: 0.8rem;
  font-weight: 300;
  line-height: 1.6;
  color: rgba(15, 15, 15, 0.35);
}

/* ─── Open Source ──────────────────────── */
.sp-oss-section {
  position: relative;
  padding: 9rem 2rem;
  background: #f8f8f8;
  overflow: hidden;
}
.sp-oss-bg-radial {
  position: absolute;
  inset: 0;
  pointer-events: none;
  background: radial-gradient(ellipse 60% 50% at 50% 50%, rgba(30,180,140,0.03) 0%, transparent 70%);
}
.sp-oss-inner {
  position: relative;
  z-index: 10;
  max-width: 720px;
  margin: 0 auto;
  text-align: center;
}
.sp-oss-title {
  margin: 0 0 2.5rem;
}
.sp-oss-desc {
  font-size: 1.05rem;
  color: rgba(15, 15, 15, 0.4);
  font-weight: 300;
  line-height: 1.8;
  max-width: 600px;
  margin: 0 auto 3.5rem;
}

/* GitHub card */
.sp-github-card {
  display: inline-flex;
  align-items: center;
  gap: 1.25rem;
  padding: 1.5rem 2.5rem;
  background: #ffffff;
  border: 1px solid rgba(15, 15, 15, 0.06);
  border-radius: 1rem;
  text-decoration: none;
  transition: border-color 0.5s, box-shadow 0.5s;
}
.sp-github-card:hover {
  border-color: rgba(30, 180, 140, 0.3);
  box-shadow: 0 8px 40px rgba(30, 180, 140, 0.08);
}
.sp-github-icon {
  color: rgba(15, 15, 15, 0.6);
  flex-shrink: 0;
  transition: color 0.5s;
}
.sp-github-card:hover .sp-github-icon { color: #1eb48c; }
.sp-github-info {
  text-align: left;
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}
.sp-github-label {
  font-size: 11px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: rgba(15, 15, 15, 0.25);
  display: block;
}
.sp-github-repo {
  font-size: 0.95rem;
  font-weight: 500;
  color: rgba(15, 15, 15, 0.7);
  transition: color 0.5s;
}
.sp-github-card:hover .sp-github-repo { color: #1eb48c; }
.sp-github-arrow {
  color: rgba(15, 15, 15, 0.2);
  margin-left: 0.5rem;
  flex-shrink: 0;
  transition: color 0.5s, transform 0.5s;
}
.sp-github-card:hover .sp-github-arrow {
  color: #1eb48c;
  transform: translateX(4px);
}

/* Stats */
.sp-stats-row {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4rem;
  margin-top: 4rem;
}
.sp-stat {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.25rem;
}
.sp-stat-num {
  font-size: 1.75rem;
  font-weight: 600;
  color: rgba(15, 15, 15, 0.8);
  line-height: 1;
}
.sp-stat-label {
  font-size: 10px;
  letter-spacing: 0.2em;
  text-transform: uppercase;
  color: rgba(15, 15, 15, 0.25);
}
.sp-stat-divider {
  width: 1px;
  height: 2rem;
  background: rgba(15, 15, 15, 0.08);
}

/* ─── Footer ───────────────────────────── */
.sp-footer {
  position: relative;
  padding: 5rem 2rem 3rem;
  background: #f0f0f0;
}
.sp-footer-top-line {
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 1px;
  background: linear-gradient(to right, transparent, rgba(30,180,140,0.3), transparent);
}
.sp-footer-inner {
  max-width: 1100px;
  margin: 0 auto;
}
.sp-footer-main {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 2rem;
  margin-bottom: 4rem;
}
.sp-footer-logo {
  height: 2.5rem;
  width: auto;
}
.sp-footer-tagline {
  font-size: 0.875rem;
  color: rgba(15, 15, 15, 0.4);
  font-weight: 300;
  letter-spacing: 0.05em;
  margin: 0;
}
.sp-footer-bottom {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 1rem;
  padding-top: 2rem;
  border-top: 1px solid rgba(15, 15, 15, 0.08);
}
.sp-footer-copy {
  font-size: 0.75rem;
  color: rgba(15, 15, 15, 0.3);
  letter-spacing: 0.05em;
  margin: 0;
}
.sp-footer-links {
  display: flex;
  align-items: center;
  gap: 2rem;
}
.sp-footer-link {
  font-size: 0.75rem;
  letter-spacing: 0.05em;
  color: rgba(15, 15, 15, 0.3);
  text-decoration: none;
  transition: color 0.3s;
  background: none;
  border: none;
  padding: 0;
  cursor: pointer;
  font-family: inherit;
}
.sp-footer-link:hover { color: #1eb48c; }
.sp-footer-beian {
  font-size: 0.75rem;
  color: rgba(15, 15, 15, 0.2);
  text-decoration: none;
  letter-spacing: 0.02em;
  transition: color 0.3s;
}
.sp-footer-beian:hover { color: #1eb48c; }

.sp-contact-mask {
  position: fixed;
  inset: 0;
  z-index: 5000;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.35);
  padding: 20px;
}
.sp-contact-dialog {
  width: min(420px, calc(100vw - 32px));
  max-height: calc(100vh - 40px);
  display: flex;
  flex-direction: column;
  background: #fff;
  border-radius: 14px;
  box-shadow: 0 20px 50px rgba(0, 0, 0, 0.2);
  color: #111827;
  overflow: hidden;
}
.sp-contact-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 16px 18px 14px;
  border-bottom: 1px solid #eef0f2;
  text-align: left;
}
.sp-contact-head-text {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}
.sp-contact-head-text strong {
  font-size: 15px;
  font-weight: 600;
}
.sp-contact-head-text span {
  font-size: 12px;
  color: #6b7280;
  line-height: 1.5;
}
.sp-contact-close {
  width: 28px;
  height: 28px;
  border: none;
  border-radius: 6px;
  background: transparent;
  font-size: 20px;
  line-height: 1;
  color: #6b7280;
  cursor: pointer;
  flex-shrink: 0;
}
.sp-contact-close:hover { background: #f3f4f6; }
.sp-contact-body {
  display: flex;
  justify-content: center;
  min-height: 0;
  overflow: auto;
  padding: 22px 18px 26px;
}
.sp-contact-qr {
  width: min(280px, 100%);
  max-height: min(520px, calc(100vh - 180px));
  height: auto;
  object-fit: contain;
  border-radius: 8px;
}

/* ─── Responsive ───────────────────────── */
@media (max-width: 1440px) {
  .sp-scenes-section {
    --scene-card: min(620px, 74vw);
    padding: 6rem 1.5rem 5rem;
  }
  .sp-scenes-head {
    margin-bottom: 2.25rem;
  }
  .sp-scene-title {
    font-size: 1.2rem;
  }
  .sp-caps-section,
  .sp-connect-section,
  .sp-oss-section {
    padding-top: 6rem;
    padding-bottom: 6rem;
  }
  .sp-section-header {
    margin-bottom: 2.75rem;
  }
  .sp-caps-header {
    margin-bottom: 3.5rem;
  }
  .sp-caps-stage {
    gap: 1.5rem;
  }
  .sp-caps-panel {
    padding: 1.8rem 1.6rem 1.2rem;
  }
  .sp-caps-group-title {
    font-size: clamp(1.85rem, 3vw, 2.6rem);
  }
  .sp-connect-split {
    gap: 1rem;
  }
  .sp-connect-col {
    padding: 1.6rem 1.45rem 1.35rem;
  }
  .sp-connect-col-title {
    font-size: 1.35rem;
  }
}
@media (max-width: 1080px) {
  .sp-connect-split {
    grid-template-columns: 1fr;
  }
}
@media (max-width: 900px) {
  .sp-caps-stage {
    grid-template-columns: 1fr;
  }
}
@media (max-width: 768px) {
  .sp-cap-item {
    padding: 1.35rem 0;
  }
  .sp-connect-col {
    padding: 1.5rem 1.2rem 1.35rem;
  }
  .sp-connect-col-title {
    font-size: 1.3rem;
  }
  .sp-connect-client {
    grid-template-columns: 40px 1fr;
  }
  .sp-stats-row {
    gap: 2rem;
  }
  .sp-footer-main {
    flex-direction: column;
    align-items: center;
    text-align: center;
  }
  .sp-footer-bottom {
    flex-direction: column;
    align-items: center;
    text-align: center;
  }
  .sp-github-card {
    padding: 1.25rem 1.5rem;
    gap: 1rem;
  }
  .sp-scenes-section {
    --scene-card: min(620px, 88vw);
  }
  .sp-scenes-title {
    font-size: clamp(34px, 8vw, 48px);
  }
  .sp-scenes-lead {
    font-size: 0.95rem;
  }
  .sp-scenes-controls {
    margin-top: 1.75rem;
    gap: 1rem;
  }
  .sp-scene-body {
    padding: 0.95rem 1.15rem 1.05rem;
  }
  .sp-scene-say {
    bottom: 1rem;
    font-size: 1rem;
    letter-spacing: 0.14em;
  }
  .sp-scene-title {
    font-size: 1.15rem;
  }
}
</style>

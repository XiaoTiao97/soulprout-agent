<template>
  <div class="sp-page">
    <!-- Loading Screen：与桌面端开屏一致，Logo + 三个圆点 -->
    <div v-if="!loaded" class="sp-loading">
      <img class="sp-loading-logo" :src="isDark ? logoDark : logoLight" alt="Soulprout" />
      <div class="sp-loading-dots" aria-hidden="true"><i></i><i></i><i></i></div>
    </div>

    <!-- Navigation -->
    <InitNavigation />

    <!-- Content -->
    <div v-show="loaded">

      <!-- ── Hero ── -->
      <section class="sp-hero" ref="heroSectionRef">
        <OrbScene v-if="heroInView && !isDark" />
        <GrowingParticles v-if="heroInView && !isDark" />
        <div v-if="isDark" class="sp-hero-frosted" aria-hidden="true" />

        <div class="sp-hero-inner">
          <div class="sp-hero-logo">
            <img :src="isDark ? logoDark : logoLight" alt="Soulprout" />
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
                <p v-if="scene.say" class="sp-scene-say" :class="{ 'is-long': scene.say.length > 12 }">{{ scene.say }}</p>
              </div>
              <h3 class="sp-scene-title">{{ scene.title }}</h3>
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
        <div class="sp-connect-inner">
          <div class="sp-section-header sp-connect-header">
            <p class="sp-section-eyebrow">{{ t('init.connectEyebrow') }}</p>
            <h2 class="sp-section-title">
              <span class="sp-reveal-wrap" ref="connectTitleRef">
                <span class="sp-reveal-text">{{ t('init.connectTitle') }}</span>
              </span>
            </h2>
            <div class="sp-connect-lead-wrap sp-connect-reveal">
              <span class="sp-connect-lead-line" aria-hidden="true" />
              <span class="sp-connect-lead-badge">{{ t('init.connectClientsLabel') }}</span>
              <p class="sp-connect-lead">{{ t('init.connectClientsTitle') }}</p>
              <span class="sp-connect-lead-line" aria-hidden="true" />
            </div>
          </div>

          <!-- 三大运行端：发布会级独立硬件展台卡片 -->
          <ul class="sp-connect-clients">
            <li
              v-for="(item, idx) in connectClients"
              :key="item.key"
              class="sp-connect-client sp-connect-reveal"
              :class="[`is-${item.key}`, { 'is-featured': item.key === 'desktop' }]"
              :style="{ transitionDelay: (idx * 90) + 'ms' }"
            >
              <div class="sp-connect-client-glow" aria-hidden="true" />

              <!-- 顶部微缩设备舞台视觉 -->
              <div class="sp-connect-stage-visual" aria-hidden="true">
                <!-- Web 云端沙盒视觉 -->
                <div v-if="item.key === 'web'" class="sp-device-art sp-device-web">
                  <div class="sp-art-window">
                    <div class="sp-art-dots"><i /><i /><i /></div>
                    <div class="sp-art-cloud-core">
                      <span class="sp-art-ring sp-art-ring-1" />
                      <span class="sp-art-ring sp-art-ring-2" />
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6">
                        <path d="M7.2 18h9.6a4 4 0 0 0 .4-8 5.5 5.5 0 0 0-10.5-1.4A3.6 3.6 0 0 0 7.2 18z" stroke-linejoin="round" />
                      </svg>
                    </div>
                  </div>
                </div>

                <!-- Desktop 本地电脑中枢视觉 -->
                <div v-else-if="item.key === 'desktop'" class="sp-device-art sp-device-desktop">
                  <div class="sp-art-screen">
                    <div class="sp-art-screen-bar" />
                    <div class="sp-art-hub-nodes">
                      <span class="sp-art-node is-left" />
                      <span class="sp-art-beam" />
                      <div class="sp-art-hub-center">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6">
                          <rect x="3.5" y="4" width="17" height="11.5" rx="1.8" />
                          <path d="M8 20h8M12 15.5V20" stroke-linecap="round" />
                        </svg>
                      </div>
                      <span class="sp-art-beam" />
                      <span class="sp-art-node is-right" />
                    </div>
                  </div>
                  <div class="sp-art-laptop-base" />
                </div>

                <!-- Mobile 随身待命视觉 -->
                <div v-else class="sp-device-art sp-device-mobile">
                  <div class="sp-art-phone">
                    <div class="sp-art-notch" />
                    <div class="sp-art-voice-orb">
                      <span class="sp-art-wave w1" />
                      <span class="sp-art-wave w2" />
                      <span class="sp-art-wave w3" />
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6">
                        <path d="M12 3a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3z" />
                        <path d="M19 10v2a7 7 0 0 1-14 0v-2M12 19v3" stroke-linecap="round" />
                      </svg>
                    </div>
                  </div>
                </div>
              </div>

              <div class="sp-connect-client-body">
                <div class="sp-connect-client-meta">
                  <span class="sp-connect-client-tag">
                    <i class="sp-connect-tag-dot" aria-hidden="true" />
                    {{ item.tag }}
                  </span>
                  <span class="sp-connect-client-index">0{{ idx + 1 }}</span>
                </div>
                <h4 class="sp-connect-client-name">{{ item.name }}</h4>
                <p class="sp-connect-client-desc">{{ item.desc }}</p>
              </div>
            </li>
          </ul>

          <!-- 全场景生态渠道与接入架构 Bento 展板 -->
          <div class="sp-connect-bento sp-connect-reveal">
            <div class="sp-connect-channels-main">
              <div class="sp-connect-panel-head">
                <span class="sp-connect-label">{{ t('init.connectChannelsLabel') }}</span>
                <h3 class="sp-connect-channels-title">{{ t('init.connectChannelsTitle') }}</h3>
                <p class="sp-connect-channels-desc">{{ t('init.connectChannelsDesc') }}</p>
              </div>

              <!-- 生态设备磁贴矩阵 -->
              <div class="sp-connect-matrix">
                <div
                  v-for="(platform, pIdx) in connectPlatforms"
                  :key="platform"
                  class="sp-connect-tile"
                  :style="{ animationDelay: (pIdx * 0.4) + 's' }"
                >
                  <div class="sp-connect-tile-icon" aria-hidden="true">
                    <!-- 微信 -->
                    <svg v-if="platform === 'wechat'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6">
                      <path d="M9.5 4C5.36 4 2 6.91 2 10.5c0 1.98 1.03 3.75 2.66 4.95L4 18l2.74-1.37c.87.24 1.8.37 2.76.37.34 0 .68-.02 1.01-.06A5.95 5.95 0 0 1 10 14.5c0-3.04 2.91-5.5 6.5-5.5.33 0 .65.02.96.06C16.82 6.16 13.5 4 9.5 4z" stroke-linejoin="round" />
                      <path d="M16.5 9c-3.59 0-6.5 2.46-6.5 5.5s2.91 5.5 6.5 5.5c.78 0 1.53-.12 2.22-.34L21 21l-.55-2.16C21.99 17.84 23 16.27 23 14.5 23 11.46 20.09 9 16.5 9z" stroke-linejoin="round" />
                    </svg>
                    <!-- 飞书 -->
                    <svg v-else-if="platform === 'feishu'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6">
                      <path d="M21 4L3 10.5l6.5 2.8L19 6.5l-6.2 8.8 2.9 5.7L21 4z" stroke-linejoin="round" />
                    </svg>
                    <!-- 企业微信 -->
                    <svg v-else-if="platform === 'wework'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6">
                      <rect x="3" y="6" width="18" height="14" rx="2.5" />
                      <path d="M8 6V4.5A1.5 1.5 0 0 1 9.5 3h5A1.5 1.5 0 0 1 16 4.5V6" />
                      <path d="M3 11.5h18" />
                    </svg>
                    <!-- 小爱音箱 -->
                    <svg v-else-if="platform === 'xiaoai'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6">
                      <rect x="6" y="2.5" width="12" height="19" rx="3.5" />
                      <circle cx="12" cy="14" r="3.2" />
                      <path d="M10.5 6.5h3" stroke-linecap="round" />
                    </svg>
                    <!-- Rokid AI 眼镜 -->
                    <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6">
                      <rect x="2.5" y="9" width="7.5" height="6" rx="2" />
                      <rect x="14" y="9" width="7.5" height="6" rx="2" />
                      <path d="M10 11.5h4M2.5 11L1 9.5M21.5 11L23 9.5" stroke-linecap="round" />
                    </svg>
                  </div>
                  <div class="sp-connect-tile-info">
                    <span class="sp-connect-tile-name">{{ connectPlatformNames[platform] }}</span>
                    <span class="sp-connect-tile-status">
                      <i aria-hidden="true" />SYNC
                    </span>
                  </div>
                </div>
              </div>
            </div>

            <!-- 右侧：如何接通 -->
            <div class="sp-connect-ways">
              <div class="sp-connect-ways-head">
                <span class="sp-connect-label">{{ t('init.connectWaysTitle') }}</span>
              </div>
              <div class="sp-connect-ways-list">
                <div
                  v-for="(way, index) in connectChannelWays"
                  :key="way.key"
                  class="sp-connect-way-card"
                >
                  <div class="sp-connect-way-badge">
                    <span class="sp-connect-way-num">{{ String(index + 1).padStart(2, '0') }}</span>
                    <div class="sp-connect-way-icon" aria-hidden="true">
                      <svg v-if="way.key === 'desktop'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6">
                        <rect x="3" y="4" width="18" height="12" rx="2" />
                        <path d="M8 20h8M12 16v4" stroke-linecap="round" />
                      </svg>
                      <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6">
                        <rect x="3" y="4" width="18" height="6.5" rx="1.5" />
                        <rect x="3" y="13.5" width="18" height="6.5" rx="1.5" />
                        <circle cx="7" cy="7.25" r="0.8" fill="currentColor" />
                        <circle cx="7" cy="16.75" r="0.8" fill="currentColor" />
                      </svg>
                    </div>
                  </div>
                  <div class="sp-connect-way-body">
                    <strong>{{ way.name }}</strong>
                    <p>{{ way.desc }}</p>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- 底部发布会级下载召唤坞 -->
          <div class="sp-connect-dock sp-connect-reveal">
            <div class="sp-connect-dock-platforms">
              <i class="sp-connect-dock-dot" aria-hidden="true" />
              <span class="sp-connect-note">{{ t('init.connectWindowsNote') }}</span>
            </div>
            <button type="button" class="sp-cta-btn sp-connect-cta" @click="openDownloadClients">
              <span>{{ t('init.connectDownload') }}</span>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" aria-hidden="true">
                <path d="M12 3v12" stroke-linecap="round" />
                <path d="M8 11l4 4 4-4" stroke-linecap="round" stroke-linejoin="round" />
                <path d="M4 17v2a2 2 0 002 2h12a2 2 0 002-2v-2" stroke-linecap="round" />
              </svg>
            </button>
            <p v-if="t('init.connectDownloadSub')" class="sp-connect-hint">{{ t('init.connectDownloadSub') }}</p>
          </div>
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
            <img :src="isDark ? logoDark : logoLight" alt="Soulprout" class="sp-footer-logo" />
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
import { ref, computed, onMounted, onUpdated, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { startExperience } from '@/utils/startExperience.js'
import { isDark } from '@/utils/theme.js'
import logoLight from '@/assets/images/logo.png'
import logoDark from '@/assets/images/logo_dark.png'
import InitNavigation from '@/components/InitNavigation.vue'
import OrbScene from '@/components/OrbScene.vue'
import GrowingParticles from '@/components/GrowingParticles.vue'
import DownloadClientsDialog from '@/components/DownloadClientsDialog.vue'
import contactQrUrl from '@/assets/docs-images/weixinhao.jpg'
import sceneDevices from '@/assets/images/whereever.jpeg'
import sceneMemory from '@/assets/scenes/scene-memory.svg'
import sceneEarphone from '@/assets/images/earphone.png'
import sceneDiy from '@/assets/images/diy.jpeg'
import sceneLaptop from '@/assets/images/laptop.jpeg'

const sceneImages = {
  'whole-day': sceneDiy,
  'all-devices': sceneDevices,
  remembers: sceneMemory,
  'does-work': sceneLaptop,
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
  return Array.isArray(list) ? list.filter((scene) => scene.key !== 'remembers') : []
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
let revealObs = null
let cardObs = null

function observeReveals() {
  if (revealObs) {
    ;[heroTitleRef.value, capTitleRef.value, connectTitleRef.value, openTitleRef.value, scenesTitleRef.value].forEach(el => {
      if (el && !el.classList.contains('is-inview')) revealObs.observe(el)
    })
  }
  if (cardObs) {
    document.querySelectorAll('.sp-cap-item:not(.is-visible), .sp-connect-reveal:not(.is-visible)').forEach(el => cardObs.observe(el))
  }
}

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

  revealObs = new IntersectionObserver(
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

  cardObs = new IntersectionObserver(
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

  observeReveals()
  armSceneTimer(SCENE_AUTOPLAY_MS)
})

onUpdated(() => {
  observeReveals()
})

onUnmounted(() => {
  window.removeEventListener('keydown', onContactKeydown)
  heroObserver?.disconnect()
  revealObs?.disconnect()
  cardObs?.disconnect()
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
  height: calc(var(--scene-card) * 0.75);
  perspective: 1700px;
  transform-style: preserve-3d;
}
.sp-scene-card {
  position: absolute;
  top: 0;
  left: 50%;
  width: var(--scene-card);
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
  height: 100%;
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
  left: 0;
  right: 0;
  bottom: 1.35rem;
  text-align: center;
  font-size: 14px;
  font-weight: 500;
  letter-spacing: 0.42em;
  text-indent: 0.42em;
  line-height: 1;
  color: #ffffff;
  text-shadow: 0 1px 3px rgba(0, 0, 0, 0.6), 0 0 12px rgba(0, 0, 0, 0.35);
}
.sp-scene-tag::before {
  display: none;
}
.sp-scene-say {
  position: absolute;
  left: 0;
  right: 0;
  top: 1.5rem;
  margin: 0;
  text-align: center;
  font-size: 1.15rem;
  font-weight: 400;
  letter-spacing: 0.18em;
  color: #fff;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.85), 0 0 12px rgba(0, 0, 0, 0.35);
}
.sp-scene-say.is-long {
  left: 1.4rem;
  right: 1.4rem;
  line-height: 1.65;
}
.sp-scene-card.is-dark .sp-scene-media img {
  object-position: 38% center;
}
.sp-scene-title {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
  clip-path: inset(50%);
  white-space: nowrap;
  border: 0;
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

/* ─── Connectivity（发布会级硬件与生态互联展台） ─── */
.sp-connect-section {
  position: relative;
  padding: 9.5rem 1.5rem 8.5rem;
  overflow: hidden;
  background: #f8f8f8;
}

.sp-connect-inner {
  position: relative;
  z-index: 10;
  max-width: 1120px;
  margin: 0 auto;
  text-align: center;
}
.sp-connect-header {
  margin-bottom: 4.25rem;
}
.sp-connect-lead-wrap {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.9rem;
  margin-top: 2rem;
  padding: 0.45rem 1.15rem 0.45rem 0.55rem;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.85);
  border: 1px solid rgba(30, 180, 140, 0.16);
  box-shadow: 0 10px 30px rgba(15, 15, 15, 0.04);
  backdrop-filter: blur(12px);
}
.sp-connect-lead-line {
  display: none;
}
.sp-connect-lead-badge {
  display: inline-flex;
  align-items: center;
  padding: 0.28rem 0.75rem;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: #ffffff;
  background: linear-gradient(135deg, #1eb48c 0%, #159674 100%);
  box-shadow: 0 4px 12px rgba(30, 180, 140, 0.25);
}
.sp-connect-lead {
  margin: 0;
  font-size: 0.98rem;
  font-weight: 500;
  letter-spacing: 0.08em;
  color: rgba(15, 15, 15, 0.78);
}

.sp-connect-reveal {
  opacity: 1;
  transform: translateY(0);
  transition: opacity 0.85s cubic-bezier(0.25, 1, 0.5, 1),
              transform 0.85s cubic-bezier(0.25, 1, 0.5, 1);
}

/* ─── 三大运行端：发布会 Bento 硬件展台卡片 ─── */
.sp-connect-clients {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 1.5rem;
  text-align: left;
}
.sp-connect-client {
  position: relative;
  isolation: isolate;
  display: flex;
  flex-direction: column;
  min-width: 0;
  border-radius: 1.75rem;
  padding: 0.65rem 0.65rem 2.1rem;
  background: #ffffff;
  border: 1px solid rgba(15, 15, 15, 0.06);
  box-shadow:
    0 24px 56px rgba(15, 15, 15, 0.06),
    0 2px 0 rgba(255, 255, 255, 0.9) inset;
  overflow: hidden;
  transition: transform 0.55s cubic-bezier(0.25, 1, 0.5, 1),
              box-shadow 0.55s cubic-bezier(0.25, 1, 0.5, 1),
              border-color 0.45s ease;
}
.sp-connect-client.is-featured {
  border-color: rgba(15, 15, 15, 0.1);
  box-shadow:
    0 28px 64px rgba(15, 15, 15, 0.08),
    0 2px 0 rgba(255, 255, 255, 0.95) inset;
}
.sp-connect-client:hover {
  transform: translateY(-8px);
  border-color: rgba(15, 15, 15, 0.14);
  box-shadow:
    0 36px 80px rgba(15, 15, 15, 0.11),
    0 2px 0 rgba(255, 255, 255, 0.95) inset;
}
.sp-connect-client-glow {
  display: none;
}

/* 顶部微缩硬件舞台 */
.sp-connect-stage-visual {
  position: relative;
  height: 168px;
  border-radius: 1.3rem;
  background: linear-gradient(180deg, #f5f5f7 0%, #efeff2 100%);
  border: 1px solid rgba(15, 15, 15, 0.05);
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}
.sp-connect-client.is-featured .sp-connect-stage-visual {
  background: linear-gradient(180deg, #f3f4f6 0%, #eceef1 100%);
  border-color: rgba(15, 15, 15, 0.07);
}

/* 硬件艺术示意图通用 */
.sp-device-art {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  transition: transform 0.55s cubic-bezier(0.25, 1, 0.5, 1);
}
.sp-connect-client:hover .sp-device-art {
  transform: scale(1.05) translateY(-2px);
}

/* 1. Web 云端沙盒微缩窗 */
.sp-art-window {
  width: 168px;
  height: 108px;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.92);
  border: 1px solid rgba(15, 15, 15, 0.08);
  box-shadow: 0 14px 32px rgba(15, 15, 15, 0.07);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.sp-art-dots {
  display: flex;
  gap: 5px;
  padding: 8px 11px;
  border-bottom: 1px solid rgba(15, 15, 15, 0.05);
}
.sp-art-dots i {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: rgba(15, 15, 15, 0.14);
}
.sp-art-dots i:first-child {
  background: #1eb48c;
}
.sp-art-cloud-core {
  position: relative;
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #17a27d;
}
.sp-art-cloud-core svg {
  position: relative;
  z-index: 2;
  width: 34px;
  height: 34px;
}
.sp-art-ring {
  position: absolute;
  border-radius: 50%;
  border: 1px solid rgba(30, 180, 140, 0.22);
}
.sp-art-ring-1 {
  width: 54px;
  height: 54px;
}
.sp-art-ring-2 {
  width: 78px;
  height: 78px;
  border-style: dashed;
  border-color: rgba(30, 180, 140, 0.15);
}

/* 2. Desktop 本地电脑中枢微缩窗 */
.sp-art-screen {
  width: 176px;
  height: 104px;
  border-radius: 12px 12px 4px 4px;
  background: rgba(255, 255, 255, 0.96);
  border: 1.5px solid rgba(30, 180, 140, 0.28);
  box-shadow: 0 16px 36px rgba(30, 180, 140, 0.14);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  position: relative;
}
.sp-art-screen-bar {
  position: absolute;
  top: 7px;
  width: 36px;
  height: 3px;
  border-radius: 99px;
  background: rgba(30, 180, 140, 0.25);
}
.sp-art-hub-nodes {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 4px;
}
.sp-art-hub-center {
  width: 44px;
  height: 44px;
  border-radius: 12px;
  background: linear-gradient(135deg, #1eb48c 0%, #159674 100%);
  color: #ffffff;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 8px 20px rgba(30, 180, 140, 0.32);
}
.sp-art-hub-center svg {
  width: 22px;
  height: 22px;
}
.sp-art-beam {
  width: 22px;
  height: 2px;
  background: linear-gradient(90deg, rgba(30, 180, 140, 0.2), #1eb48c, rgba(30, 180, 140, 0.2));
  border-radius: 2px;
}
.sp-art-node {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #ffffff;
  border: 2px solid #1eb48c;
  box-shadow: 0 0 0 4px rgba(30, 180, 140, 0.12);
}
.sp-art-laptop-base {
  width: 198px;
  height: 7px;
  margin-top: -1px;
  border-radius: 2px 2px 8px 8px;
  background: linear-gradient(90deg, #dce5e1 0%, #eef3f1 50%, #dce5e1 100%);
  border: 1px solid rgba(15, 15, 15, 0.08);
}

/* 3. Mobile 手机待命微缩窗 */
.sp-art-phone {
  width: 82px;
  height: 124px;
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.94);
  border: 1.5px solid rgba(15, 15, 15, 0.1);
  box-shadow: 0 14px 32px rgba(15, 15, 15, 0.08);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  position: relative;
}
.sp-art-notch {
  position: absolute;
  top: 7px;
  width: 22px;
  height: 4px;
  border-radius: 99px;
  background: rgba(15, 15, 15, 0.14);
}
.sp-art-voice-orb {
  position: relative;
  width: 44px;
  height: 44px;
  border-radius: 50%;
  background: rgba(30, 180, 140, 0.12);
  color: #17a27d;
  display: flex;
  align-items: center;
  justify-content: center;
}
.sp-art-voice-orb svg {
  position: relative;
  z-index: 2;
  width: 20px;
  height: 20px;
}
.sp-art-wave {
  position: absolute;
  inset: 0;
  border-radius: 50%;
  border: 1px solid rgba(30, 180, 140, 0.35);
  animation: spVoicePulse 2.8s infinite ease-out;
}
.sp-art-wave.w2 { animation-delay: 0.9s; }
.sp-art-wave.w3 { animation-delay: 1.8s; }
@keyframes spVoicePulse {
  0% { transform: scale(0.95); opacity: 0.8; }
  100% { transform: scale(1.65); opacity: 0; }
}

/* 卡片正文区 */
.sp-connect-client-body {
  padding: 1.65rem 1.5rem 0;
  display: flex;
  flex-direction: column;
  flex: 1;
}
.sp-connect-client-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 0.9rem;
}
.sp-connect-client-tag {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.28rem 0.7rem;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.08em;
  color: #148f72;
  background: rgba(30, 180, 140, 0.09);
  border: 1px solid rgba(30, 180, 140, 0.16);
}
.sp-connect-tag-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: #1eb48c;
}
.sp-connect-client-index {
  font-size: 0.75rem;
  font-weight: 600;
  letter-spacing: 0.16em;
  font-variant-numeric: tabular-nums;
  color: rgba(15, 15, 15, 0.24);
}
.sp-connect-client-name {
  margin: 0 0 0.75rem;
  font-size: clamp(1.5rem, 2.2vw, 1.85rem);
  font-weight: 700;
  letter-spacing: -0.02em;
  line-height: 1.15;
  color: #0f0f0f;
  transition: color 0.3s;
}
.sp-connect-client:hover .sp-connect-client-name {
  color: #17a27d;
}
.sp-connect-client-desc {
  margin: 0;
  font-size: 0.94rem;
  line-height: 1.78;
  color: rgba(15, 15, 15, 0.62);
  overflow-wrap: break-word;
}

/* ─── 全场景生态渠道与接入架构 Bento 大展板 ─── */
.sp-connect-bento {
  position: relative;
  margin-top: 1.75rem;
  border-radius: 1.85rem;
  padding: 2.8rem 2.8rem;
  background: #ffffff;
  border: 1px solid rgba(15, 15, 15, 0.06);
  box-shadow:
    0 28px 64px rgba(15, 15, 15, 0.06),
    0 2px 0 rgba(255, 255, 255, 0.9) inset;
  display: grid;
  grid-template-columns: 1.25fr 1fr;
  gap: 3rem;
  text-align: left;
  align-items: center;
}
.sp-connect-label {
  display: inline-block;
  margin-bottom: 0.75rem;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.3em;
  text-transform: uppercase;
  color: #1eb48c;
}
.sp-connect-channels-title {
  margin: 0 0 0.75rem;
  font-size: clamp(1.65rem, 2.6vw, 2.15rem);
  font-weight: 700;
  letter-spacing: -0.02em;
  line-height: 1.15;
  color: #0f0f0f;
}
.sp-connect-channels-desc {
  margin: 0 0 1.85rem;
  font-size: 0.95rem;
  line-height: 1.75;
  color: rgba(15, 15, 15, 0.6);
  max-width: 520px;
}

/* 生态渠道硬件磁贴矩阵 */
.sp-connect-matrix {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(152px, 1fr));
  gap: 0.85rem;
}
.sp-connect-tile {
  display: flex;
  align-items: center;
  gap: 0.8rem;
  padding: 0.85rem 1rem;
  border-radius: 1.1rem;
  background: #f5f5f7;
  border: 1px solid rgba(15, 15, 15, 0.06);
  transition: all 0.35s cubic-bezier(0.25, 1, 0.5, 1);
}
.sp-connect-tile:hover {
  transform: translateY(-3px);
  background: #ffffff;
  border-color: rgba(30, 180, 140, 0.32);
  box-shadow: 0 12px 28px rgba(15, 15, 15, 0.07);
}
.sp-connect-tile-icon {
  width: 38px;
  height: 38px;
  border-radius: 10px;
  background: #ffffff;
  border: 1px solid rgba(15, 15, 15, 0.06);
  color: #17a27d;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: background 0.3s, color 0.3s, border-color 0.3s;
}
.sp-connect-tile:hover .sp-connect-tile-icon {
  background: #1eb48c;
  border-color: #1eb48c;
  color: #ffffff;
}
.sp-connect-tile-icon svg {
  width: 20px;
  height: 20px;
}
.sp-connect-tile-info {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
  min-width: 0;
}
.sp-connect-tile-name {
  font-size: 0.88rem;
  font-weight: 600;
  color: #0f0f0f;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.sp-connect-tile-status {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.12em;
  color: rgba(15, 15, 15, 0.45);
}
.sp-connect-tile-status i {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: #1eb48c;
}

/* 右侧：如何接通 */
.sp-connect-ways {
  padding-left: 2.8rem;
  border-left: 1px solid rgba(15, 15, 15, 0.07);
  display: flex;
  flex-direction: column;
  justify-content: center;
}
.sp-connect-ways-head {
  margin-bottom: 0.5rem;
}
.sp-connect-ways-list {
  display: flex;
  flex-direction: column;
  gap: 0.9rem;
}
.sp-connect-way-card {
  display: flex;
  align-items: flex-start;
  gap: 1rem;
  padding: 1.2rem 1.25rem;
  border-radius: 1.2rem;
  background: #f5f5f7;
  border: 1px solid rgba(15, 15, 15, 0.05);
  transition: all 0.35s cubic-bezier(0.25, 1, 0.5, 1);
}
.sp-connect-way-card:hover {
  background: #ffffff;
  border-color: rgba(30, 180, 140, 0.25);
  box-shadow: 0 12px 28px rgba(15, 15, 15, 0.05);
  transform: translateX(4px);
}
.sp-connect-way-badge {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.35rem;
  flex-shrink: 0;
}
.sp-connect-way-num {
  font-size: 0.7rem;
  font-weight: 700;
  letter-spacing: 0.14em;
  font-variant-numeric: tabular-nums;
  color: #1eb48c;
}
.sp-connect-way-icon {
  width: 36px;
  height: 36px;
  border-radius: 10px;
  background: #ffffff;
  border: 1px solid rgba(30, 180, 140, 0.18);
  color: #17a27d;
  display: flex;
  align-items: center;
  justify-content: center;
}
.sp-connect-way-icon svg {
  width: 18px;
  height: 18px;
}
.sp-connect-way-body {
  min-width: 0;
  padding-top: 0.1rem;
}
.sp-connect-way-body strong {
  display: block;
  margin-bottom: 0.3rem;
  font-size: 1rem;
  font-weight: 600;
  line-height: 1.35;
  color: #0f0f0f;
}
.sp-connect-way-body p {
  margin: 0;
  font-size: 0.875rem;
  line-height: 1.65;
  color: rgba(15, 15, 15, 0.58);
}

/* ─── 底部发布会下载召唤坞 ─── */
.sp-connect-dock {
  margin-top: 3.25rem;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1.15rem;
}
.sp-connect-dock-platforms {
  display: inline-flex;
  align-items: center;
  gap: 0.55rem;
  padding: 0.4rem 1rem;
  border-radius: 999px;
  background: rgba(15, 15, 15, 0.035);
  border: 1px solid rgba(15, 15, 15, 0.06);
}
.sp-connect-dock-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #1eb48c;
}
.sp-connect-note {
  margin: 0;
  font-size: 0.78rem;
  font-weight: 500;
  letter-spacing: 0.1em;
  color: rgba(15, 15, 15, 0.52);
}
.sp-connect-cta {
  padding: 17px 44px;
  box-shadow:
    0 10px 30px rgba(30, 180, 140, 0.28),
    0 0 0 4px rgba(30, 180, 140, 0.1);
}
.sp-connect-cta:hover {
  box-shadow:
    0 14px 36px rgba(30, 180, 140, 0.36),
    0 0 0 6px rgba(30, 180, 140, 0.14);
}
.sp-connect-hint {
  margin: 0.2rem 0 0;
  font-size: 0.8rem;
  font-weight: 300;
  line-height: 1.6;
  color: rgba(15, 15, 15, 0.4);
}

@media (prefers-reduced-motion: reduce) {
  .sp-connect-reveal { transition: none; }
  .sp-art-wave { animation: none; }
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
  .sp-connect-clients {
    gap: 1.2rem;
  }
  .sp-connect-bento {
    gap: 2.2rem;
    padding: 2.2rem 2rem;
  }
  .sp-connect-ways {
    padding-left: 2.2rem;
  }
}
@media (max-width: 980px) {
  .sp-connect-clients {
    grid-template-columns: 1fr;
  }
  .sp-connect-bento {
    grid-template-columns: 1fr;
    gap: 2.25rem;
  }
  .sp-connect-ways {
    padding-left: 0;
    padding-top: 2rem;
    border-left: none;
    border-top: 1px solid rgba(15, 15, 15, 0.07);
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
  .sp-connect-bento {
    padding: 1.85rem 1.35rem;
  }
  .sp-connect-header {
    margin-bottom: 3rem;
  }
  .sp-connect-matrix {
    grid-template-columns: repeat(2, 1fr);
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
  .sp-scene-say {
    top: 1.1rem;
    font-size: 1rem;
    letter-spacing: 0.14em;
  }
  .sp-scene-tag {
    bottom: 1rem;
  }
}

/* ─── Dark Mode (Pure Matte Black + Subtle Localized Frosted Sage) ───────────────────────── */
html[data-theme='dark'] .sp-page {
  color: #f2f2f2;
  background-color: #0b0b0c;
  background-image: none;
}
html[data-theme='dark'] .sp-loading {
  background: #0b0b0c;
}
html[data-theme='dark'] .sp-hero {
  background: #0b0b0c;
}
/* 仅在 Hero 局部保留一处克制、低饱和的暗磨砂绿质感，不铺满全屏 */
.sp-hero-frosted {
  position: absolute;
  inset: 0;
  z-index: 1;
  pointer-events: none;
  background:
    radial-gradient(ellipse 38% 32% at 50% 42%, rgba(46, 102, 86, 0.16) 0%, rgba(28, 64, 54, 0.06) 55%, transparent 100%),
    #0b0b0c;
}
.sp-hero-frosted::after {
  content: '';
  position: absolute;
  inset: 0;
  background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 240 240' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noise)' opacity='0.04'/%3E%3C/svg%3E");
  backdrop-filter: blur(40px);
  -webkit-backdrop-filter: blur(40px);
}
html[data-theme='dark'] .sp-cta-btn {
  background: rgba(34, 122, 98, 0.82);
  border: 1px solid rgba(110, 185, 162, 0.25);
  color: #f5f5f5;
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.45), inset 0 1px 0 rgba(255, 255, 255, 0.1);
}
html[data-theme='dark'] .sp-cta-btn:hover {
  background: rgba(40, 138, 112, 0.92);
  border-color: rgba(130, 200, 178, 0.35);
  box-shadow: 0 12px 30px rgba(0, 0, 0, 0.55), inset 0 1px 0 rgba(255, 255, 255, 0.14);
}
html[data-theme='dark'] .sp-hero-title,
html[data-theme='dark'] .sp-hero-title .sp-reveal-text,
html[data-theme='dark'] .sp-section-title,
html[data-theme='dark'] .sp-section-title .sp-reveal-text,
html[data-theme='dark'] .sp-scenes-title,
html[data-theme='dark'] .sp-oss-title,
html[data-theme='dark'] .sp-caps-group-title,
html[data-theme='dark'] .sp-cap-title,
html[data-theme='dark'] .sp-connect-client-name,
html[data-theme='dark'] .sp-connect-channels-title,
html[data-theme='dark'] .sp-connect-tile-name,
html[data-theme='dark'] .sp-connect-way-body strong {
  color: #f2f2f2;
}
html[data-theme='dark'] .sp-hero-sub {
  color: rgba(229, 229, 229, 0.68);
}
html[data-theme='dark'] .sp-explore-btn {
  color: rgba(229, 229, 229, 0.55);
}
html[data-theme='dark'] .sp-explore-btn:hover {
  color: #6ab09c;
}
html[data-theme='dark'] .sp-section-eyebrow,
html[data-theme='dark'] .sp-caps-group-label,
html[data-theme='dark'] .sp-connect-label,
html[data-theme='dark'] .sp-connect-way-num {
  color: #6ab09c;
}
html[data-theme='dark'] .sp-caps-group-rule {
  background: #4d8f7c;
}

/* Scenes Dark */
html[data-theme='dark'] .sp-scenes-section {
  background: #0e0e10;
}
html[data-theme='dark'] .sp-scene-media {
  background: #161618;
  border-color: rgba(255, 255, 255, 0.08);
  box-shadow: 0 28px 80px rgba(0, 0, 0, 0.6);
}
html[data-theme='dark'] .sp-scene-card.is-active .sp-scene-media {
  box-shadow: 0 34px 90px rgba(0, 0, 0, 0.75);
}
html[data-theme='dark'] .sp-scene-timer {
  background: rgba(255, 255, 255, 0.12);
}
html[data-theme='dark'] .sp-scene-timer-bar {
  background: #589e8b;
}
html[data-theme='dark'] .sp-scenes-nav {
  background: #18181b;
  border-color: rgba(255, 255, 255, 0.1);
  color: rgba(242, 242, 242, 0.78);
}
html[data-theme='dark'] .sp-scenes-nav:hover:not(:disabled) {
  background: #266b58;
  border-color: rgba(110, 185, 162, 0.3);
  color: #ffffff;
}
html[data-theme='dark'] .sp-scenes-dot {
  background: rgba(255, 255, 255, 0.18);
}
html[data-theme='dark'] .sp-scenes-dot:hover {
  background: rgba(106, 176, 156, 0.5);
}
html[data-theme='dark'] .sp-scenes-dot.is-active {
  background: #589e8b;
}

/* Capabilities Dark */
html[data-theme='dark'] .sp-caps-section {
  background: #0b0b0c;
}
html[data-theme='dark'] .sp-caps-bg-radial {
  background: none;
}
html[data-theme='dark'] .sp-caps-ring-lg,
html[data-theme='dark'] .sp-caps-ring-sm {
  display: none;
}
html[data-theme='dark'] .sp-caps-panel {
  background: linear-gradient(180deg, rgba(24, 24, 27, 0.92) 0%, rgba(19, 19, 22, 0.95) 100%);
  border-color: rgba(255, 255, 255, 0.08);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  box-shadow:
    0 28px 60px rgba(0, 0, 0, 0.52),
    0 1px 0 rgba(255, 255, 255, 0.05) inset;
}
html[data-theme='dark'] .sp-caps-panel::before {
  background: radial-gradient(ellipse 60% 40% at 15% 0%, rgba(56, 118, 100, 0.08) 0%, transparent 70%);
}
html[data-theme='dark'] .sp-caps-panel:hover {
  border-color: rgba(255, 255, 255, 0.14);
  box-shadow:
    0 38px 80px rgba(0, 0, 0, 0.65),
    0 1px 0 rgba(255, 255, 255, 0.08) inset;
}
html[data-theme='dark'] .sp-cap-item {
  border-top-color: rgba(255, 255, 255, 0.07);
}
html[data-theme='dark'] .sp-cap-item:hover .sp-cap-title {
  color: #72b8a4;
}
html[data-theme='dark'] .sp-cap-desc {
  color: rgba(212, 212, 216, 0.68);
}
html[data-theme='dark'] .sp-cap-desc :deep(strong) {
  color: #72b8a4;
}

/* Connectivity Dark */
html[data-theme='dark'] .sp-connect-section {
  background: #0e0e10;
}
html[data-theme='dark'] .sp-connect-lead-wrap {
  background: rgba(24, 24, 27, 0.88);
  border-color: rgba(255, 255, 255, 0.09);
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.4);
}
html[data-theme='dark'] .sp-connect-lead-badge {
  background: rgba(42, 115, 94, 0.45);
  border: 1px solid rgba(106, 176, 156, 0.25);
  color: #d5ece5;
  box-shadow: none;
}
html[data-theme='dark'] .sp-connect-lead {
  color: rgba(242, 242, 242, 0.85);
}
html[data-theme='dark'] .sp-connect-client {
  background: #151518;
  border-color: rgba(255, 255, 255, 0.07);
  box-shadow:
    0 24px 56px rgba(0, 0, 0, 0.45),
    0 1px 0 rgba(255, 255, 255, 0.04) inset;
}
html[data-theme='dark'] .sp-connect-client.is-featured {
  border-color: rgba(255, 255, 255, 0.12);
  box-shadow:
    0 28px 64px rgba(0, 0, 0, 0.52),
    0 1px 0 rgba(255, 255, 255, 0.07) inset;
}
html[data-theme='dark'] .sp-connect-client:hover {
  border-color: rgba(255, 255, 255, 0.16);
  box-shadow:
    0 36px 80px rgba(0, 0, 0, 0.62),
    0 1px 0 rgba(255, 255, 255, 0.09) inset;
}
/* 框内舞台背景：深黑灰底 + 局部微弱的暗磨砂绿质感，无荧光感 */
html[data-theme='dark'] .sp-connect-stage-visual,
html[data-theme='dark'] .sp-connect-client.is-featured .sp-connect-stage-visual {
  background:
    radial-gradient(circle at 50% 50%, rgba(46, 102, 86, 0.1) 0%, transparent 70%),
    #1b1b1f;
  border-color: rgba(255, 255, 255, 0.06);
}
html[data-theme='dark'] .sp-art-window,
html[data-theme='dark'] .sp-art-screen,
html[data-theme='dark'] .sp-art-phone {
  background: rgba(32, 32, 36, 0.95);
  border-color: rgba(255, 255, 255, 0.12);
  box-shadow: 0 14px 32px rgba(0, 0, 0, 0.45);
}
html[data-theme='dark'] .sp-art-screen {
  border-color: rgba(106, 176, 156, 0.25);
  box-shadow: 0 16px 36px rgba(0, 0, 0, 0.45);
}
html[data-theme='dark'] .sp-art-hub-center {
  background: linear-gradient(135deg, #267862 0%, #1d5e4d 100%);
  box-shadow: 0 6px 16px rgba(0, 0, 0, 0.4);
}
html[data-theme='dark'] .sp-art-cloud-core,
html[data-theme='dark'] .sp-art-voice-orb {
  color: #6ab09c;
}
html[data-theme='dark'] .sp-art-dots {
  border-bottom-color: rgba(255, 255, 255, 0.07);
}
html[data-theme='dark'] .sp-art-dots i:first-child {
  background: #589e8b;
}
html[data-theme='dark'] .sp-art-dots i:not(:first-child),
html[data-theme='dark'] .sp-art-notch {
  background: rgba(255, 255, 255, 0.22);
}
html[data-theme='dark'] .sp-art-node {
  background: #1b1b1f;
  border-color: #589e8b;
  box-shadow: 0 0 0 4px rgba(88, 158, 139, 0.12);
}
html[data-theme='dark'] .sp-art-laptop-base {
  background: linear-gradient(90deg, #27272c 0%, #34343b 50%, #27272c 100%);
  border-color: rgba(255, 255, 255, 0.1);
}
/* 局部胶囊标签：磨砂暗绿质感，去除刺眼荧光 */
html[data-theme='dark'] .sp-connect-client-tag {
  color: #8cc4b3;
  background: rgba(46, 108, 90, 0.18);
  border-color: rgba(106, 176, 156, 0.2);
  backdrop-filter: blur(8px);
}
html[data-theme='dark'] .sp-connect-tag-dot,
html[data-theme='dark'] .sp-connect-tile-status i,
html[data-theme='dark'] .sp-connect-dock-dot {
  background: #589e8b;
}
html[data-theme='dark'] .sp-connect-client-index {
  color: rgba(255, 255, 255, 0.25);
}
html[data-theme='dark'] .sp-connect-client:hover .sp-connect-client-name {
  color: #72b8a4;
}
html[data-theme='dark'] .sp-connect-client-desc,
html[data-theme='dark'] .sp-connect-channels-desc,
html[data-theme='dark'] .sp-connect-way-body p {
  color: rgba(212, 212, 216, 0.65);
}
html[data-theme='dark'] .sp-connect-bento {
  background: #151518;
  border-color: rgba(255, 255, 255, 0.07);
  box-shadow:
    0 28px 64px rgba(0, 0, 0, 0.48),
    0 1px 0 rgba(255, 255, 255, 0.04) inset;
}
html[data-theme='dark'] .sp-connect-tile,
html[data-theme='dark'] .sp-connect-way-card {
  background: #1c1c20;
  border-color: rgba(255, 255, 255, 0.06);
}
html[data-theme='dark'] .sp-connect-tile:hover,
html[data-theme='dark'] .sp-connect-way-card:hover {
  background: #232328;
  border-color: rgba(255, 255, 255, 0.14);
  box-shadow: 0 12px 28px rgba(0, 0, 0, 0.4);
}
html[data-theme='dark'] .sp-connect-tile-icon,
html[data-theme='dark'] .sp-connect-way-icon {
  background: rgba(46, 108, 90, 0.16);
  border-color: rgba(106, 176, 156, 0.18);
  color: #7ab8a6;
}
html[data-theme='dark'] .sp-connect-tile:hover .sp-connect-tile-icon {
  background: #266b58;
  border-color: rgba(110, 185, 162, 0.3);
  color: #ffffff;
}
html[data-theme='dark'] .sp-connect-tile-status {
  color: rgba(212, 212, 216, 0.48);
}
html[data-theme='dark'] .sp-connect-ways {
  border-left-color: rgba(255, 255, 255, 0.07);
  border-top-color: rgba(255, 255, 255, 0.07);
}
html[data-theme='dark'] .sp-connect-dock-platforms {
  background: rgba(255, 255, 255, 0.04);
  border-color: rgba(255, 255, 255, 0.08);
}
html[data-theme='dark'] .sp-connect-note {
  color: rgba(212, 212, 216, 0.62);
}
html[data-theme='dark'] .sp-connect-hint {
  color: rgba(212, 212, 216, 0.46);
}

/* Open Source & Footer Dark */
html[data-theme='dark'] .sp-oss-section {
  background: #0b0b0c;
}
html[data-theme='dark'] .sp-oss-bg-radial {
  background: radial-gradient(ellipse 45% 35% at 50% 50%, rgba(46, 102, 86, 0.08) 0%, transparent 70%);
}
html[data-theme='dark'] .sp-oss-desc {
  color: rgba(212, 212, 216, 0.68);
}
html[data-theme='dark'] .sp-github-card {
  background: #161619;
  border-color: rgba(255, 255, 255, 0.09);
}
html[data-theme='dark'] .sp-github-card:hover {
  border-color: rgba(106, 176, 156, 0.32);
  box-shadow: 0 12px 36px rgba(0, 0, 0, 0.45);
}
html[data-theme='dark'] .sp-github-card:hover .sp-github-icon,
html[data-theme='dark'] .sp-github-card:hover .sp-github-repo,
html[data-theme='dark'] .sp-github-card:hover .sp-github-arrow {
  color: #72b8a4;
}
html[data-theme='dark'] .sp-github-icon {
  color: rgba(242, 242, 242, 0.85);
}
html[data-theme='dark'] .sp-github-label {
  color: rgba(212, 212, 216, 0.55);
}
html[data-theme='dark'] .sp-github-repo {
  color: #f2f2f2;
}
html[data-theme='dark'] .sp-github-arrow {
  color: rgba(242, 242, 242, 0.55);
}
html[data-theme='dark'] .sp-stat-num {
  color: #f2f2f2;
}
html[data-theme='dark'] .sp-stat-label {
  color: rgba(212, 212, 216, 0.55);
}
html[data-theme='dark'] .sp-stat-divider {
  background: rgba(255, 255, 255, 0.12);
}
html[data-theme='dark'] .sp-footer {
  background: #080809;
}
html[data-theme='dark'] .sp-footer-top-line {
  background: linear-gradient(to right, transparent, rgba(255, 255, 255, 0.1), transparent);
}
html[data-theme='dark'] .sp-footer-tagline {
  color: rgba(212, 212, 216, 0.62);
}
html[data-theme='dark'] .sp-footer-bottom {
  border-top-color: rgba(255, 255, 255, 0.08);
}
html[data-theme='dark'] .sp-footer-copy,
html[data-theme='dark'] .sp-footer-link {
  color: rgba(212, 212, 216, 0.6);
}
html[data-theme='dark'] .sp-footer-link:hover,
html[data-theme='dark'] .sp-footer-beian:hover {
  color: #72b8a4;
}
html[data-theme='dark'] .sp-footer-beian {
  color: rgba(212, 212, 216, 0.48);
}
html[data-theme='dark'] .sp-contact-mask {
  background: rgba(0, 0, 0, 0.65);
}
html[data-theme='dark'] .sp-contact-dialog {
  background: #18181b;
  border: 1px solid rgba(255, 255, 255, 0.09);
  color: #f2f2f2;
  box-shadow: 0 24px 60px rgba(0, 0, 0, 0.55);
}
html[data-theme='dark'] .sp-contact-head {
  border-bottom-color: rgba(255, 255, 255, 0.08);
}
html[data-theme='dark'] .sp-contact-head-text span {
  color: #a1a1aa;
}
html[data-theme='dark'] .sp-contact-close {
  color: #a1a1aa;
}
html[data-theme='dark'] .sp-contact-close:hover {
  background: rgba(255, 255, 255, 0.08);
  color: #f2f2f2;
}
</style>

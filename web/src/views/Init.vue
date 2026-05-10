<template>
  <div class="sp-page">
    <!-- Loading Screen -->
    <div v-if="!loaded" class="sp-loading">
      <div class="sp-loading-text">
        <span
          v-for="(char, i) in loadingChars"
          :key="i"
          class="sp-loading-char"
          :style="{ animationDelay: `${i * 0.08}s` }"
        >{{ char }}</span>
      </div>
    </div>

    <!-- Navigation -->
    <InitNavigation />

    <!-- Content -->
    <div v-show="loaded">

      <!-- ── Hero ── -->
      <section class="sp-hero">
        <OrbScene />
        <GrowingParticles />

        <div class="sp-hero-inner">
          <div class="sp-hero-logo">
            <img src="@/assets/images/logo.png" alt="Soulprout" />
          </div>

          <h1 class="sp-hero-title">
            <span class="sp-reveal-wrap" ref="heroTitleRef">
              <span class="sp-reveal-text">思想种下，自有森林</span>
            </span>
          </h1>

          <p class="sp-hero-sub">
            Soulprout —— 打造想你所想，真正做事的 AI 智能体平台
          </p>

          <div class="sp-hero-actions">
            <router-link to="/register" class="sp-cta-btn">
              <span>立即体验</span>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                <path d="M5 12h14M12 5l7 7-7 7" />
              </svg>
            </router-link>
            <button class="sp-explore-btn" @click="scrollTo('capabilities')">
              探索更多 ↓
            </button>
          </div>
        </div>
      </section>

      <!-- ── Core Capabilities ── -->
      <section id="capabilities" class="sp-caps-section">
        <!-- soft radial bg -->
        <div class="sp-caps-bg-radial" />
        <div class="sp-caps-ring sp-caps-ring-lg" />
        <div class="sp-caps-ring sp-caps-ring-sm" />

        <div class="sp-caps-inner">
          <!-- header -->
          <div class="sp-section-header">
            <p class="sp-section-eyebrow">Core Capabilities</p>
            <h2 class="sp-section-title">
              <span class="sp-reveal-wrap" ref="capTitleRef">
                <span class="sp-reveal-text">能力矩阵</span>
              </span>
            </h2>
          </div>

          <!-- panel -->
          <div class="sp-caps-panel">
            <div class="sp-caps-panel-border" />
            <div class="sp-caps-panel-inner">
              <div class="sp-caps-top-line" />
              <div class="sp-caps-grid">
                <div
                  v-for="(f, i) in features"
                  :key="i"
                  class="sp-cap-card"
                  :class="[
                    i % 3 === 1 ? 'sp-cap-card--mid' : '',
                    i < 3 ? 'sp-cap-card--top' : ''
                  ]"
                >
                  <div class="sp-cap-card-hover-bg" />
                  <div class="sp-cap-num-row">
                    <span class="sp-cap-num">{{ f.num }}</span>
                    <span class="sp-cap-num-line" />
                  </div>
                  <h3 class="sp-cap-title">{{ f.title }}</h3>
                  <p class="sp-cap-desc">{{ f.desc }}</p>
                  <div class="sp-cap-foot">
                    <span class="sp-cap-dot" />
                    <span class="sp-cap-foot-line" />
                  </div>
                </div>
              </div>
              <div class="sp-caps-bottom-line" />
            </div>
          </div>

          <div class="sp-caps-label-row">
            <span class="sp-caps-label-dash" />
            <span class="sp-caps-label-text">Six Pillars</span>
            <span class="sp-caps-label-dash" />
          </div>
        </div>
      </section>

      <!-- ── Open Source ── -->
      <section id="intelligence" class="sp-oss-section">
        <div class="sp-oss-bg-radial" />

        <div class="sp-oss-inner">
          <p class="sp-section-eyebrow">Open Source</p>

          <h2 class="sp-section-title sp-oss-title">
            <span class="sp-reveal-wrap" ref="openTitleRef">
              <span class="sp-reveal-text">全面开源</span>
            </span>
          </h2>

          <p class="sp-oss-desc">
            Soulprout 的核心代码开源，相信透明与协作是推动 AI 智能体生态进化的最佳方式。
            欢迎开发者参与共建，一起打造更强大的智能体平台。
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
              <span class="sp-github-label">GitHub Repository</span>
              <span class="sp-github-repo">XiaoTiao97 / soulprout-agent</span>
            </div>
            <svg class="sp-github-arrow" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M7 17L17 7M17 7H7M17 7V17" />
            </svg>
          </a>

          <div class="sp-stats-row">
            <div class="sp-stat">
              <span class="sp-stat-num">0</span>
              <span class="sp-stat-label">Stars</span>
            </div>
            <div class="sp-stat-divider" />
            <div class="sp-stat">
              <span class="sp-stat-num">MIT</span>
              <span class="sp-stat-label">License</span>
            </div>
            <div class="sp-stat-divider" />
            <div class="sp-stat">
              <span class="sp-stat-num">Zero</span>
              <span class="sp-stat-label">Code Needed</span>
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
            <p class="sp-footer-tagline">想你所想，真正做事</p>
            <router-link to="/register" class="sp-cta-btn">
              <span>立即体验</span>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                <path d="M5 12h14M12 5l7 7-7 7" />
              </svg>
            </router-link>
          </div>
          <div class="sp-footer-bottom">
            <p class="sp-footer-copy">&copy; 2025 Soulprout. All rights reserved.</p>
            <div class="sp-footer-links">
              <a href="https://github.com/XiaoTiao97/soulprout-agent" target="_blank" rel="noopener noreferrer" class="sp-footer-link">GitHub</a>
              <a href="#" class="sp-footer-link">联系我们</a>
              <span class="sp-footer-beian">苏ICP备2025216370号-1</span>
            </div>
          </div>
        </div>
      </footer>

    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import InitNavigation from '@/components/InitNavigation.vue'
import OrbScene from '@/components/OrbScene.vue'
import GrowingParticles from '@/components/GrowingParticles.vue'

const loaded = ref(false)
const heroTitleRef = ref(null)
const capTitleRef = ref(null)
const openTitleRef = ref(null)
const loadingChars = 'LOADING_SOULPROUT...'.split('')

const features = [
  { num: '01', title: '交互式规划', desc: '设身处地为你着想，智能拆解复杂任务为清晰步骤，动态调整策略。' },
  { num: '02', title: '人机协作办公', desc: '人与 AI 高度协同，随时手动微调，告别低效重复操作。' },
  { num: '03', title: '专家模式', desc: '零代码将工作流转换成 Agent 专家团队，自动并行执行任务。' },
  { num: '04', title: 'AI 知识库检索', desc: 'RAG 与生成式 AI 双保险，快速召回信息，遇阻自动升级深度检索。' },
  { num: '05', title: '灵活部署', desc: '一键云端体验或本地私有化部署，零配置开箱即用，数据隔离安全。' },
  { num: '06', title: '流程全透明', desc: '每一步操作清晰可见，工具使用全程留痕，避免模型幻觉误判。' },
]

onMounted(() => {
  setTimeout(() => { loaded.value = true }, 2000)

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
  ;[heroTitleRef.value, capTitleRef.value, openTitleRef.value].forEach(el => {
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
  document.querySelectorAll('.sp-cap-card').forEach(el => cardObs.observe(el))
})

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

/* ─── Loading ──────────────────────────── */
.sp-loading {
  position: fixed;
  inset: 0;
  z-index: 9999;
  background: #ffffff;
  display: flex;
  align-items: center;
  justify-content: center;
  animation: spLoadFade 0.6s ease 1.8s forwards;
}
@keyframes spLoadFade {
  from { opacity: 1; }
  to   { opacity: 0; pointer-events: none; }
}
.sp-loading-text {
  font-family: 'Source Code Pro', 'Courier New', monospace;
  font-size: 14px;
  letter-spacing: 0.3em;
  color: #1eb48c;
}
.sp-loading-char {
  display: inline-block;
  animation: spCharBlink 1.5s ease-in-out infinite;
}
@keyframes spCharBlink {
  0%, 100% { opacity: 1; }
  50%       { opacity: 0.3; }
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
  max-width: 1000px;
  margin: 0 auto;
}

/* Panel */
.sp-caps-panel {
  position: relative;
}
.sp-caps-panel-border {
  position: absolute;
  inset: -1px;
  border-radius: 1.5rem;
  pointer-events: none;
  background: linear-gradient(135deg,
    rgba(30,180,140,0.08) 0%,
    rgba(30,180,140,0.02) 50%,
    rgba(30,180,140,0.06) 100%);
}
.sp-caps-panel-inner {
  position: relative;
  background: rgba(255, 255, 255, 0.7);
  backdrop-filter: blur(24px);
  border: 1px solid rgba(15, 15, 15, 0.06);
  border-radius: 1.5rem;
  overflow: hidden;
  box-shadow: 0 0 80px rgba(30, 180, 140, 0.04);
}
.sp-caps-top-line,
.sp-caps-bottom-line {
  height: 1px;
  width: 100%;
  background: linear-gradient(to right, transparent, rgba(30,180,140,0.2), transparent);
}

/* 3-col grid */
.sp-caps-grid {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
}

/* Card */
.sp-cap-card {
  position: relative;
  padding: 2.5rem;
  transition: background 0.5s;
  opacity: 0;
  transform: translateY(24px);
  transition: opacity 0.7s cubic-bezier(0.25, 1, 0.5, 1),
              transform 0.7s cubic-bezier(0.25, 1, 0.5, 1),
              background 0.5s;
}
.sp-cap-card.is-visible {
  opacity: 1;
  transform: translateY(0);
}
.sp-cap-card:nth-child(1) { transition-delay: 0ms; }
.sp-cap-card:nth-child(2) { transition-delay: 80ms; }
.sp-cap-card:nth-child(3) { transition-delay: 160ms; }
.sp-cap-card:nth-child(4) { transition-delay: 240ms; }
.sp-cap-card:nth-child(5) { transition-delay: 320ms; }
.sp-cap-card:nth-child(6) { transition-delay: 400ms; }
.sp-cap-card:hover { background: rgba(248, 250, 250, 0.8); }

/* Top row gets bottom border, middle column gets left/right borders */
.sp-cap-card--top {
  border-bottom: 1px solid rgba(15, 15, 15, 0.05);
}
.sp-cap-card--mid {
  border-left: 1px solid rgba(15, 15, 15, 0.05);
  border-right: 1px solid rgba(15, 15, 15, 0.05);
}

.sp-cap-card-hover-bg {
  position: absolute;
  top: 0; right: 0;
  width: 8rem; height: 8rem;
  background: linear-gradient(to bottom left, rgba(30,180,140,0.03), transparent);
  opacity: 0;
  transition: opacity 0.7s;
  pointer-events: none;
}
.sp-cap-card:hover .sp-cap-card-hover-bg { opacity: 1; }

.sp-cap-num-row {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin-bottom: 1.5rem;
}
.sp-cap-num {
  font-size: 10px;
  font-family: 'Courier New', monospace;
  color: rgba(30, 180, 140, 0.4);
  letter-spacing: 0.2em;
  flex-shrink: 0;
}
.sp-cap-num-line {
  flex: 1;
  height: 1px;
  background: rgba(15, 15, 15, 0.04);
  transition: background 0.5s;
}
.sp-cap-card:hover .sp-cap-num-line { background: rgba(30, 180, 140, 0.1); }

.sp-cap-title {
  font-size: 1.05rem;
  font-weight: 600;
  color: #0f0f0f;
  letter-spacing: -0.01em;
  margin: 0 0 0.75rem;
  transition: color 0.5s;
}
.sp-cap-card:hover .sp-cap-title { color: #1eb48c; }

.sp-cap-desc {
  font-size: 0.875rem;
  color: rgba(15, 15, 15, 0.35);
  font-weight: 300;
  line-height: 1.7;
  margin: 0;
  transition: color 0.5s;
}
.sp-cap-card:hover .sp-cap-desc { color: rgba(15, 15, 15, 0.5); }

.sp-cap-foot {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-top: 1.5rem;
}
.sp-cap-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: transparent;
  transition: background 0.5s;
  flex-shrink: 0;
}
.sp-cap-card:hover .sp-cap-dot { background: rgba(30, 180, 140, 0.4); }
.sp-cap-foot-line {
  flex: 1;
  height: 1px;
  background: rgba(15, 15, 15, 0.03);
  transition: background 0.5s;
}
.sp-cap-card:hover .sp-cap-foot-line { background: rgba(30, 180, 140, 0.1); }

/* label row */
.sp-caps-label-row {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 1rem;
  margin-top: 3rem;
}
.sp-caps-label-dash {
  width: 2rem;
  height: 1px;
  background: rgba(15, 15, 15, 0.08);
}
.sp-caps-label-text {
  font-size: 10px;
  letter-spacing: 0.3em;
  text-transform: uppercase;
  color: rgba(15, 15, 15, 0.2);
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
}
.sp-footer-link:hover { color: #1eb48c; }
.sp-footer-beian {
  font-size: 0.75rem;
  color: rgba(15, 15, 15, 0.2);
}

/* ─── Responsive ───────────────────────── */
@media (max-width: 768px) {
  .sp-caps-grid {
    grid-template-columns: 1fr;
  }
  .sp-cap-card--top {
    border-bottom: 1px solid rgba(15, 15, 15, 0.05);
  }
  .sp-cap-card--mid {
    border-left: none;
    border-right: none;
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
}
</style>

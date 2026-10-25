<template>
  <div class="orb" :class="'orb--' + phase" :style="{ '--amp': amp }" aria-hidden="true">
    <div ref="flashEl" class="orb-flash">
      <div class="orb-field">
        <!-- 常驻：几团柔和的绿色光晕 -->
        <div class="blobs">
          <i class="blob blob-1"></i>
          <i class="blob blob-2"></i>
          <i class="blob blob-3"></i>
        </div>
        <i class="core"></i>

        <!-- 待命：一圈极细的呼吸光环 -->
        <i class="halo"></i>
        <!-- 聆听：随麦克风音量伸缩的光环 -->
        <i class="mic"></i>
        <!-- 思考：绕着光球转动的亮弧 -->
        <i class="swirl"></i>
        <!-- 回答：一圈圈向外扩散的声波 -->
        <i class="wave wave-1"></i>
        <i class="wave wave-2"></i>
        <i class="wave wave-3"></i>
      </div>
    </div>
    <i ref="ringEl" class="ring"></i>
  </div>
</template>

<script setup>
/**
 * 「灵魂」光感，主色取应用主题绿（#1eb48c）。四个阶段各有不同的形态，一眼能看出后台在做什么：
 *  standby   缩小、很淡，慢速呼吸，外围一圈极细光环
 *  listening 放大提亮，光环随麦克风音量伸缩
 *  thinking  收紧成一团，亮弧绕着转，整体像心跳
 *  speaking  随播放音量起伏，一圈圈声波向外扩散
 * 被唤醒时（pulse 自增）瞬间提亮并向外扩一圈光环。
 */
import { computed, ref, watch } from 'vue'

const props = defineProps({
  /** starting | standby | listening | thinking | speaking */
  phase: { type: String, default: 'standby' },
  /** 麦克风音量 0-100 */
  level: { type: Number, default: 0 },
  /** 播放输出音量 0-100 */
  outLevel: { type: Number, default: 0 },
  /** 每次唤醒自增 */
  pulse: { type: Number, default: 0 },
})

const flashEl = ref(null)
const ringEl = ref(null)

const amp = computed(() => {
  let v = 0
  if (props.phase === 'listening') v = props.level / 100
  else if (props.phase === 'speaking') v = (props.outLevel / 100) * 1.25
  return Math.max(0, Math.min(1, v)).toFixed(3)
})

watch(
  () => props.pulse,
  (n, o) => {
    if (n === o || !n) return
    flashEl.value?.animate(
      [
        { transform: 'scale(1)', filter: 'brightness(1) saturate(1)' },
        { transform: 'scale(1.25)', filter: 'brightness(1.1) saturate(1.5)', offset: 0.28 },
        { transform: 'scale(1)', filter: 'brightness(1) saturate(1)' },
      ],
      { duration: 1000, easing: 'cubic-bezier(0.22, 1, 0.36, 1)' },
    )
    ringEl.value?.animate(
      [
        { transform: 'translate(-50%, -50%) scale(0.5)', opacity: 0.8 },
        { transform: 'translate(-50%, -50%) scale(1.9)', opacity: 0 },
      ],
      { duration: 1100, easing: 'cubic-bezier(0.16, 1, 0.3, 1)' },
    )
  },
)
</script>

<style scoped>
.orb {
  --base: 0.8;
  --c-brand: 30, 180, 140; /* #1eb48c */
  position: relative;
  width: min(88vw, 380px);
  aspect-ratio: 1;
  pointer-events: none;
}

.orb--starting {
  --base: 0.68;
}

.orb--listening {
  --base: 0.98;
}

.orb--thinking {
  --base: 0.76;
}

.orb--speaking {
  --base: 0.9;
}

.orb-flash {
  position: absolute;
  inset: 0;
  will-change: transform, filter;
}

.orb-field {
  position: absolute;
  inset: 0;
  transform: scale(calc(var(--base) + var(--amp) * 0.34));
  transition: transform 0.14s ease-out;
  will-change: transform;
}

/* ---------- 光晕 ---------- */
.blobs {
  position: absolute;
  inset: 0;
}

.blob {
  position: absolute;
  width: 64%;
  height: 64%;
  border-radius: 50%;
  filter: blur(34px);
  opacity: 0.5;
  transition: opacity 0.7s ease;
}

.blob-1 {
  top: 5%;
  left: 3%;
  background: radial-gradient(circle at 45% 45%, #6fe0bd 0%, rgba(111, 224, 189, 0) 72%);
  animation: drift-1 11s ease-in-out infinite;
}

.blob-2 {
  top: 12%;
  right: 2%;
  background: radial-gradient(circle at 55% 45%, #1eb48c 0%, rgba(30, 180, 140, 0) 72%);
  animation: drift-2 13s ease-in-out infinite;
}

.blob-3 {
  bottom: 2%;
  left: 20%;
  background: radial-gradient(circle at 50% 50%, #b9f1cf 0%, rgba(185, 241, 207, 0) 72%);
  animation: drift-3 15s ease-in-out infinite;
}

.core {
  position: absolute;
  top: 50%;
  left: 50%;
  width: 46%;
  height: 46%;
  transform: translate(-50%, -50%);
  border-radius: 50%;
  background: radial-gradient(circle, rgba(255, 255, 255, 0.95) 0%, rgba(255, 255, 255, 0.5) 38%, rgba(255, 255, 255, 0) 72%);
  filter: blur(6px);
  opacity: 0.7;
  animation: core-glow 5.5s ease-in-out infinite;
  transition: opacity 0.6s ease;
}

/* ---------- 各阶段专属图层（默认隐藏） ---------- */
.halo,
.mic,
.swirl,
.wave {
  position: absolute;
  border-radius: 50%;
  opacity: 0;
  transition: opacity 0.6s ease;
}

.halo {
  inset: 16%;
  border: 1px solid rgba(var(--c-brand), 0.4);
  box-shadow: 0 0 22px rgba(var(--c-brand), 0.16);
}

.mic {
  inset: 18%;
  border: 2px solid rgba(var(--c-brand), 0.55);
  box-shadow: 0 0 30px rgba(var(--c-brand), 0.3), inset 0 0 26px rgba(var(--c-brand), 0.14);
  transform: scale(calc(0.86 + var(--amp) * 0.34));
  transition: opacity 0.6s ease, transform 0.1s ease-out;
}

.swirl {
  inset: 14%;
  background: conic-gradient(
    from 0deg,
    rgba(var(--c-brand), 0) 0%,
    rgba(var(--c-brand), 0) 52%,
    rgba(var(--c-brand), 0.85) 88%,
    #d9fbec 100%
  );
  -webkit-mask: radial-gradient(farthest-side, transparent calc(100% - 7px), #000 calc(100% - 6px));
  mask: radial-gradient(farthest-side, transparent calc(100% - 7px), #000 calc(100% - 6px));
  filter: blur(1px) drop-shadow(0 0 8px rgba(var(--c-brand), 0.7));
}

.wave {
  inset: 24%;
  border: 1.5px solid rgba(var(--c-brand), 0.6);
}

/* ---------- 待命 ---------- */
.orb--standby .orb-field,
.orb--starting .orb-field {
  animation: orb-breathe 6.5s ease-in-out infinite;
  transition: transform 1.2s ease;
}

.orb--standby .halo,
.orb--starting .halo {
  opacity: 1;
  animation: halo-breathe 6.5s ease-in-out infinite;
}

/* ---------- 聆听 ---------- */
.orb--listening .blob {
  opacity: 0.88;
}

.orb--listening .core {
  opacity: 1;
}

.orb--listening .mic {
  opacity: 1;
}

/* ---------- 思考 ---------- */
.orb--thinking .orb-field {
  animation: think-beat 1.9s ease-in-out infinite;
}

.orb--thinking .blobs {
  animation: orb-spin 5s linear infinite;
}

.orb--thinking .blob {
  opacity: 0.75;
}

.orb--thinking .swirl {
  opacity: 1;
  animation: orb-spin 1.7s linear infinite;
}

/* ---------- 回答 ---------- */
.orb--speaking .blob {
  opacity: 0.85;
}

.orb--speaking .core {
  opacity: 1;
}

.orb--speaking .wave {
  animation: wave-out 2.4s cubic-bezier(0.2, 0.6, 0.3, 1) infinite;
}

.orb--speaking .wave-2 {
  animation-delay: 0.8s;
}

.orb--speaking .wave-3 {
  animation-delay: 1.6s;
}

.ring {
  position: absolute;
  top: 50%;
  left: 50%;
  width: 52%;
  height: 52%;
  border-radius: 50%;
  border: 1.5px solid rgba(var(--c-brand), 0.6);
  box-shadow: 0 0 28px rgba(var(--c-brand), 0.4);
  transform: translate(-50%, -50%) scale(0.5);
  opacity: 0;
}

/* ---------- 动画 ---------- */
@keyframes orb-breathe {
  0%,
  100% {
    transform: scale(0.76);
  }
  50% {
    transform: scale(0.88);
  }
}

@keyframes halo-breathe {
  0%,
  100% {
    opacity: 0.35;
    transform: scale(0.96);
  }
  50% {
    opacity: 1;
    transform: scale(1.06);
  }
}

@keyframes think-beat {
  0%,
  100% {
    transform: scale(0.74);
  }
  18% {
    transform: scale(0.84);
  }
  36% {
    transform: scale(0.76);
  }
  54% {
    transform: scale(0.8);
  }
}

@keyframes orb-spin {
  to {
    transform: rotate(360deg);
  }
}

@keyframes wave-out {
  0% {
    transform: scale(0.7);
    opacity: calc(0.35 + var(--amp) * 0.55);
  }
  100% {
    transform: scale(1.75);
    opacity: 0;
  }
}

@keyframes drift-1 {
  0%,
  100% {
    transform: translate(0, 0) scale(1);
  }
  50% {
    transform: translate(16%, 10%) scale(1.12);
  }
}

@keyframes drift-2 {
  0%,
  100% {
    transform: translate(0, 0) scale(1);
  }
  50% {
    transform: translate(-14%, 14%) scale(0.92);
  }
}

@keyframes drift-3 {
  0%,
  100% {
    transform: translate(0, 0) scale(1);
  }
  50% {
    transform: translate(10%, -14%) scale(1.1);
  }
}

@keyframes core-glow {
  0%,
  100% {
    filter: blur(6px) brightness(0.95);
  }
  50% {
    filter: blur(6px) brightness(1.1);
  }
}

@media (prefers-reduced-motion: reduce) {
  .orb-field,
  .blobs,
  .blob,
  .core,
  .swirl,
  .wave,
  .halo {
    animation: none !important;
  }
}
</style>

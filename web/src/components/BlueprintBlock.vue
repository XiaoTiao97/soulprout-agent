<template>
  <div v-if="content" class="bp-block">
    <div class="bp-summaries-row">
      <button
        type="button"
        class="bp-summary-pill bp-summary-pill--active bp-summary-pill--pending"
        :aria-expanded="expanded"
        aria-label="正在生成蓝图，点击展开或折叠"
        @click="expanded = !expanded"
      >
        <span class="bp-pill-icon" aria-hidden="true">
          <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
            <path d="M14 2v6h6" />
            <path d="M8 13h8" />
            <path d="M8 17h5" />
          </svg>
        </span>
        <span class="bp-pill-text">正在生成蓝图</span>
        <span class="bp-pill-chevron">{{ expanded ? '▴' : '▾' }}</span>
      </button>
    </div>

    <div v-if="expanded" class="bp-detail-panel">
      <section class="bp-detail-section">
        <div class="bp-detail-block">
          <div class="bp-detail-block-title">蓝图内容</div>
          <div class="bp-result-wrap">
            <div class="bp-result-content">{{ content }}</div>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<script lang="ts" setup>
import { ref, watch } from 'vue'

const props = withDefaults(
  defineProps<{
    content?: string
    pending?: boolean
  }>(),
  {
    content: '',
    pending: true,
  },
)

const expanded = ref(true)

watch(
  () => props.content,
  (v, old) => {
    const wasEmpty = !old || old === ''
    if (wasEmpty && v) expanded.value = true
  },
)
</script>

<style scoped>
.bp-block {
  display: flex;
  flex-direction: column;
  gap: 0;
  width: 100%;
  max-width: 100%;
  margin: 0 0 8px;
  cursor: default;
}

.bp-summaries-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  column-gap: 8px;
  row-gap: 4px;
}

.bp-summary-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 11px 5px 9px;
  border: 1px solid rgba(0, 0, 0, 0.08);
  border-radius: 999px;
  background: #fafafa;
  color: #525252;
  font-size: 12.5px;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.18s ease, border-color 0.18s ease, box-shadow 0.18s ease;
  font-family: inherit;
  line-height: 1.3;
  max-width: 100%;
}

.bp-summary-pill:hover {
  background: #f4f4f5;
  border-color: rgba(0, 0, 0, 0.12);
}

.bp-summary-pill--active {
  background: #f0f0f0;
  border-color: rgba(0, 0, 0, 0.14);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06);
}

.bp-summary-pill--pending {
  position: relative;
  overflow: hidden;
}

.bp-summary-pill--pending::after {
  content: '';
  position: absolute;
  inset: -1px;
  left: -100%;
  width: calc(100% + 2px);
  background: linear-gradient(
    90deg,
    transparent 0%,
    rgba(255, 255, 255, 0.65) 45%,
    rgba(255, 255, 255, 0.85) 50%,
    rgba(255, 255, 255, 0.65) 55%,
    transparent 100%
  );
  animation: bp-pill-shine 2s ease-in-out infinite;
  pointer-events: none;
  border-radius: inherit;
}

@keyframes bp-pill-shine {
  0%, 55% { left: -100%; }
  100% { left: 100%; }
}

.bp-pill-icon {
  display: inline-flex;
  color: #737373;
  flex-shrink: 0;
}

.bp-pill-text {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 280px;
}

.bp-pill-chevron {
  flex-shrink: 0;
  font-size: 8px;
  color: #a3a3a3;
  margin-left: 1px;
}

.bp-detail-panel {
  margin-top: 8px;
  padding: 0;
  border: 1px solid rgba(0, 0, 0, 0.06);
  border-radius: 12px;
  background: #f8f9fa;
  overflow: hidden;
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.04);
  width: fit-content;
  min-width: 300px;
  max-width: 100%;
  cursor: default;
}

.bp-detail-section {
  padding: 8px 10px 10px;
}

.bp-detail-block-title {
  font-size: 10px;
  font-weight: 600;
  color: #a3a3a3;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  margin-bottom: 5px;
  padding-left: 1px;
}

.bp-result-wrap {
  position: relative;
  width: 100%;
}

.bp-result-content {
  margin: 0;
  padding: 7px 9px;
  font-size: 12px;
  line-height: 1.5;
  color: #3f3f46;
  font-family: inherit;
  font-weight: 400;
  background: #fff;
  border: 1px solid rgba(0, 0, 0, 0.05);
  border-radius: 8px;
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.03);
  white-space: pre-wrap;
  word-break: break-word;
  overflow-wrap: anywhere;
  max-height: 480px;
  overflow-y: auto;
  box-sizing: border-box;
  scrollbar-width: thin;
  scrollbar-color: rgba(0, 0, 0, 0.12) transparent;
}

.bp-result-content::-webkit-scrollbar {
  width: 4px;
}

.bp-result-content::-webkit-scrollbar-thumb {
  background: rgba(0, 0, 0, 0.12);
  border-radius: 999px;
}

@media (max-width: 520px) {
  .bp-pill-text {
    max-width: 200px;
  }

  .bp-detail-panel {
    min-width: 0;
    width: 100%;
  }
}
</style>

<template>
  <div v-if="calls.length" class="ws-block">
    <!-- 并行搜索：摘要行集中展示 -->
    <div class="ws-summaries-row">
      <button
        v-for="(item, idx) in calls"
        :key="item.toolCallId"
        type="button"
        class="ws-summary-pill"
        :class="{
          'ws-summary-pill--active': expanded.has(item.toolCallId),
          'ws-summary-pill--pending': pending && getCount(item.toolCallId) === 0,
        }"
        @click="toggle(item.toolCallId)"
      >
        <span class="ws-pill-icon" aria-hidden="true">
          <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round">
            <circle cx="10.5" cy="10.5" r="6.5" />
            <path d="M16 16l5 5" />
          </svg>
        </span>
        <span class="ws-pill-text">
          <template v-if="getCount(item.toolCallId) > 0">
            已阅读 {{ getCount(item.toolCallId) }} 个网页
          </template>
          <template v-else>正在搜索网页…</template>
        </span>
        <span v-if="calls.length > 1" class="ws-pill-index">{{ idx + 1 }}</span>
        <span class="ws-pill-chevron">{{ expanded.has(item.toolCallId) ? '▴' : '▾' }}</span>
      </button>
    </div>

    <!-- 结果统一在下方独立区域展示 -->
    <div v-if="hasExpanded" class="ws-detail-panel">
      <template v-for="(item, idx) in calls" :key="'panel-' + item.toolCallId">
        <section v-if="expanded.has(item.toolCallId)" class="ws-detail-section">
          <header v-if="calls.length > 1" class="ws-detail-head">
            <span class="ws-detail-head-label">检索 {{ idx + 1 }}</span>
            <span v-if="item.query" class="ws-detail-head-query">{{ item.query }}</span>
            <span class="ws-detail-head-count">{{ getCount(item.toolCallId) }} 条</span>
          </header>
          <ul v-if="getResults(item.toolCallId).length" class="ws-source-list">
            <li v-for="(row, ri) in getResults(item.toolCallId)" :key="ri" class="ws-source-item-wrap">
              <a
                :href="row.link || '#'"
                class="ws-source-item"
                target="_blank"
                rel="noopener noreferrer"
                @click="!row.link && $event.preventDefault()"
              >
                <span class="ws-source-meta">
                  <span v-if="row.media" class="ws-source-media">{{ row.media }}</span>
                  <span v-if="row.publish_date" class="ws-source-date">{{ row.publish_date }}</span>
                </span>
                <span class="ws-source-title">{{ row.title || row.link || '无标题' }}</span>
              </a>
            </li>
          </ul>
          <p v-else class="ws-detail-empty">暂无检索结果</p>
        </section>
      </template>
    </div>
  </div>
</template>

<script lang="ts" setup>
import { computed, ref } from 'vue'
import type { AgentMessage } from '../types/interface'
import { parseWebSearchResultContent } from '../utils/parseWebSearchResult'

export type WebSearchCallItem = {
  toolCallId: string
  query?: string
}

const props = defineProps<{
  calls: WebSearchCallItem[]
  toolMessages?: AgentMessage[]
  agentMessageList?: AgentMessage[]
  /** 流式进行中且尚无结果时显示扫光 */
  pending?: boolean
}>()

const expanded = ref(new Set<string>())

function toggle(id: string) {
  const next = new Set(expanded.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  expanded.value = next
}

const hasExpanded = computed(() =>
  props.calls.some((c) => expanded.value.has(c.toolCallId))
)

function getRawResult(toolCallId: string): string {
  if (!toolCallId) return ''
  const id = String(toolCallId)
  const sources = [...(props.toolMessages || []), ...(props.agentMessageList || [])]
  for (const m of sources) {
    if (m.role === 'tool' && String(m.tool_call_id || '') === id && m.content) {
      return m.content
    }
  }
  return ''
}

function getResults(toolCallId: string) {
  return parseWebSearchResultContent(getRawResult(toolCallId))
}

function getCount(toolCallId: string) {
  return getResults(toolCallId).length
}
</script>

<style scoped>
.ws-block {
  display: flex;
  flex-direction: column;
  gap: 0;
  width: 100%;
  max-width: 100%;
  margin: 4px 0 8px;
}

.ws-summaries-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.ws-summary-pill {
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

.ws-summary-pill:hover {
  background: #f4f4f5;
  border-color: rgba(0, 0, 0, 0.12);
}

.ws-summary-pill--active {
  background: #f0f0f0;
  border-color: rgba(0, 0, 0, 0.14);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06);
}

.ws-summary-pill--pending {
  position: relative;
  overflow: hidden;
}

.ws-summary-pill--pending::after {
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
  animation: ws-pill-shine 2s ease-in-out infinite;
  pointer-events: none;
  border-radius: inherit;
}

@keyframes ws-pill-shine {
  0%, 55% { left: -100%; }
  100% { left: 100%; }
}

.ws-pill-icon {
  display: inline-flex;
  color: #737373;
  flex-shrink: 0;
}

.ws-pill-text {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 200px;
}

.ws-pill-index {
  flex-shrink: 0;
  font-size: 10px;
  font-weight: 600;
  color: #a3a3a3;
  background: rgba(0, 0, 0, 0.05);
  padding: 1px 5px;
  border-radius: 4px;
  line-height: 1.4;
}

.ws-pill-chevron {
  flex-shrink: 0;
  font-size: 8px;
  color: #a3a3a3;
  margin-left: 1px;
}

/* 独立结果区 */
.ws-detail-panel {
  margin-top: 10px;
  padding: 0;
  border: 1px solid rgba(0, 0, 0, 0.07);
  border-radius: 10px;
  background: #fcfcfc;
  overflow: hidden;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
}

.ws-detail-section + .ws-detail-section {
  border-top: 1px solid rgba(0, 0, 0, 0.06);
}

.ws-detail-head {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px 8px;
  background: #f5f5f5;
  border-bottom: 1px solid rgba(0, 0, 0, 0.05);
  font-size: 11px;
  color: #737373;
  letter-spacing: 0.02em;
}

.ws-detail-head-label {
  font-weight: 600;
  color: #525252;
  flex-shrink: 0;
}

.ws-detail-head-query {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ws-detail-head-count {
  flex-shrink: 0;
  color: #a3a3a3;
}

.ws-source-list {
  list-style: none;
  margin: 0;
  padding: 4px 0;
}

.ws-source-item-wrap {
  margin: 0;
  padding: 0;
}

.ws-source-item {
  display: grid;
  grid-template-columns: minmax(100px, 28%) minmax(0, 1fr);
  gap: 12px 16px;
  align-items: baseline;
  padding: 10px 14px;
  text-decoration: none;
  color: inherit;
  border-bottom: 1px solid rgba(0, 0, 0, 0.04);
  transition: background 0.15s ease;
}

.ws-source-item-wrap:last-child .ws-source-item {
  border-bottom: none;
}

.ws-source-item:hover {
  background: #f5f5f5;
}

.ws-source-meta {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
  font-size: 11.5px;
  color: #a3a3a3;
  line-height: 1.4;
}

.ws-source-media,
.ws-source-date {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ws-source-title {
  font-size: 13.5px;
  font-weight: 500;
  color: #404040;
  line-height: 1.45;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  white-space: normal;
}

.ws-source-item:hover .ws-source-title {
  color: #171717;
}

.ws-detail-empty {
  margin: 0;
  padding: 16px 14px;
  font-size: 12px;
  color: #a3a3a3;
  text-align: center;
}

@media (max-width: 520px) {
  .ws-source-item {
    grid-template-columns: 1fr;
    gap: 4px;
  }
}
</style>

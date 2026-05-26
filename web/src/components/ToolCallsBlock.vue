<template>
  <div v-if="calls.length" class="tc-block">
    <div class="tc-summaries-row">
      <button
        v-for="(item, idx) in calls"
        :key="item.toolCallId"
        type="button"
        class="tc-summary-pill"
        :class="{
          'tc-summary-pill--active': expanded.has(item.toolCallId),
          'tc-summary-pill--pending': isPending(item),
        }"
        @click="onPillClick(item)"
        @mouseenter="emit('highlight', item.toolCallId)"
        @mouseleave="emit('unhighlight')"
      >
        <span class="tc-pill-icon" aria-hidden="true">
          <svg v-if="getToolIconKind(item.toolName, item.messageType) === 'search'" viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round">
            <circle cx="10.5" cy="10.5" r="6.5" />
            <path d="M16 16l5 5" />
          </svg>
          <svg v-else-if="getToolIconKind(item.toolName, item.messageType) === 'agent'" viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="8" r="3.5" />
            <path d="M5 20c0-3.3 3.1-5 7-5s7 1.7 7 5" />
          </svg>
          <svg v-else-if="getToolIconKind(item.toolName, item.messageType) === 'file'" viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
            <path d="M14 2v6h6" />
          </svg>
          <svg v-else-if="getToolIconKind(item.toolName, item.messageType) === 'shell'" viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="4 17 10 11 4 5" />
            <line x1="12" y1="19" x2="20" y2="19" />
          </svg>
          <svg v-else-if="getToolIconKind(item.toolName, item.messageType) === 'memory'" viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <ellipse cx="12" cy="5" rx="8" ry="3" />
            <path d="M4 5v6c0 1.7 3.6 3 8 3s8-1.3 8-3V5" />
            <path d="M4 11v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6" />
          </svg>
          <svg v-else-if="getToolIconKind(item.toolName, item.messageType) === 'kb'" viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
            <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
          </svg>
          <svg v-else viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z" />
          </svg>
        </span>
        <span class="tc-pill-text">{{ getLabel(item) }}</span>
        <span v-if="calls.length > 1" class="tc-pill-index">{{ idx + 1 }}</span>
        <span class="tc-pill-chevron">{{ expanded.has(item.toolCallId) ? '▴' : '▾' }}</span>
      </button>
    </div>

    <div v-if="hasExpanded" class="tc-detail-panel">
      <template v-for="(item, idx) in calls" :key="'panel-' + item.toolCallId">
        <section v-if="expanded.has(item.toolCallId)" class="tc-detail-section">
          <header v-if="calls.length > 1" class="tc-detail-head">
            <span class="tc-detail-head-label">调用 {{ idx + 1 }}</span>
            <span class="tc-detail-head-query">{{ getLabel(item) }}</span>
          </header>

          <div v-if="hasArguments(item)" class="tc-detail-block">
            <div class="tc-detail-block-title">参数</div>
            <div class="tc-args-list">
              <div v-for="(value, key) in item.arguments" :key="String(key)" class="tc-arg-row">
                <span class="tc-arg-key">{{ key }}</span>
                <div class="tc-arg-value">{{ formatToolArgumentValue(value) }}</div>
              </div>
            </div>
          </div>

          <div class="tc-detail-block">
            <div class="tc-detail-block-title">返回结果</div>
            <div v-if="getRawResult(item.toolCallId)" class="tc-result-wrap">
              <div
                class="tc-result-content"
                :style="{ height: `${getResultHeight(item.toolCallId)}px` }"
              >{{ formatToolResultContent(getRawResult(item.toolCallId)) }}</div>
              <div
                class="tc-result-resize-handle"
                role="separator"
                aria-orientation="vertical"
                aria-label="拖拽调整结果区域高度"
                @mousedown.prevent="startResultResize($event, item.toolCallId)"
              >
                <span class="tc-result-resize-grip" aria-hidden="true" />
              </div>
            </div>
            <p v-else class="tc-detail-empty">等待工具返回…</p>
          </div>
        </section>
      </template>
    </div>
  </div>
</template>

<script lang="ts" setup>
import { computed, onUnmounted, ref } from 'vue'
import type { AgentMessage } from '../types/interface'
import {
  type ToolCallItem,
  formatToolArgumentValue,
  formatToolResultContent,
  getToolFilePath,
  getToolIconKind,
  getToolSummaryLabel,
} from '../utils/toolCallDisplay'

const props = defineProps<{
  calls: ToolCallItem[]
  toolMessages?: AgentMessage[]
  agentMessageList?: AgentMessage[]
  /** 流式进行中且当前块尚无结果时显示扫光 */
  pending?: boolean
}>()

const emit = defineEmits<{
  highlight: [id: string]
  unhighlight: []
  scrollTo: [id: string]
  openFilePreview: [filePath: string]
}>()

const expanded = ref(new Set<string>())

const DEFAULT_RESULT_HEIGHT = 168
const MIN_RESULT_HEIGHT = 72
const MAX_RESULT_HEIGHT = 480
const resultHeights = ref<Record<string, number>>({})

let activeResize: {
  onMove: (ev: MouseEvent) => void
  onUp: () => void
} | null = null

function getResultHeight(toolCallId: string): number {
  return resultHeights.value[toolCallId] ?? DEFAULT_RESULT_HEIGHT
}

function stopResultResize() {
  if (!activeResize) return
  window.removeEventListener('mousemove', activeResize.onMove)
  window.removeEventListener('mouseup', activeResize.onUp)
  document.body.style.cursor = ''
  document.body.style.userSelect = ''
  activeResize = null
}

function startResultResize(event: MouseEvent, toolCallId: string) {
  stopResultResize()
  const startY = event.clientY
  const startHeight = getResultHeight(toolCallId)

  const onMove = (ev: MouseEvent) => {
    const next = Math.min(
      MAX_RESULT_HEIGHT,
      Math.max(MIN_RESULT_HEIGHT, startHeight + (ev.clientY - startY)),
    )
    resultHeights.value = { ...resultHeights.value, [toolCallId]: next }
  }

  const onUp = () => stopResultResize()

  activeResize = { onMove, onUp }
  document.body.style.cursor = 'ns-resize'
  document.body.style.userSelect = 'none'
  window.addEventListener('mousemove', onMove)
  window.addEventListener('mouseup', onUp)
}

onUnmounted(() => stopResultResize())

function onPillClick(item: ToolCallItem) {
  toggle(item.toolCallId)
  if (getToolIconKind(item.toolName, item.messageType) === 'agent') {
    emit('scrollTo', item.toolCallId)
  }
  const filePath = getToolFilePath(item.toolName, item.arguments)
  if (filePath) {
    emit('openFilePreview', filePath)
  }
}

function toggle(id: string) {
  const next = new Set(expanded.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  expanded.value = next
}

const hasExpanded = computed(() =>
  props.calls.some((c) => expanded.value.has(c.toolCallId)),
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

function hasArguments(item: ToolCallItem): boolean {
  return Object.keys(item.arguments).length > 0
}

function getLabel(item: ToolCallItem): string {
  const result = getRawResult(item.toolCallId)
  return getToolSummaryLabel(item.toolName, item.arguments, !!result, result)
}

function isPending(item: ToolCallItem): boolean {
  return !!props.pending && !getRawResult(item.toolCallId)
}
</script>

<style scoped>
.tc-block {
  display: flex;
  flex-direction: column;
  gap: 0;
  width: 100%;
  max-width: 100%;
  margin: 0;
  cursor: default;
}

.tc-summaries-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  column-gap: 8px;
  row-gap: 4px;
}

.tc-summary-pill {
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

.tc-summary-pill:hover {
  background: #f4f4f5;
  border-color: rgba(0, 0, 0, 0.12);
}

.tc-summary-pill--active {
  background: #f0f0f0;
  border-color: rgba(0, 0, 0, 0.14);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06);
}

.tc-summary-pill--pending {
  position: relative;
  overflow: hidden;
}

.tc-summary-pill--pending::after {
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
  animation: tc-pill-shine 2s ease-in-out infinite;
  pointer-events: none;
  border-radius: inherit;
}

@keyframes tc-pill-shine {
  0%, 55% { left: -100%; }
  100% { left: 100%; }
}

.tc-pill-icon {
  display: inline-flex;
  color: #737373;
  flex-shrink: 0;
}

.tc-pill-text {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 280px;
}

.tc-pill-index {
  flex-shrink: 0;
  font-size: 10px;
  font-weight: 600;
  color: #a3a3a3;
  background: rgba(0, 0, 0, 0.05);
  padding: 1px 5px;
  border-radius: 4px;
  line-height: 1.4;
}

.tc-pill-chevron {
  flex-shrink: 0;
  font-size: 8px;
  color: #a3a3a3;
  margin-left: 1px;
}

.tc-detail-panel {
  margin-top: 8px;
  padding: 0;
  border: 1px solid rgba(0, 0, 0, 0.06);
  border-radius: 12px;
  background: #f8f9fa;
  overflow: hidden;
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.04);
  width: fit-content;
  min-width: 300px;
  cursor: default;
}

.tc-detail-section + .tc-detail-section {
  border-top: 1px solid rgba(0, 0, 0, 0.05);
}

.tc-detail-section {
  padding: 8px 10px 10px;
}

.tc-detail-head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 8px;
  margin-bottom: 8px;
  background: rgba(255, 255, 255, 0.72);
  border: 1px solid rgba(0, 0, 0, 0.05);
  border-radius: 8px;
  font-size: 10.5px;
  color: #8b8b8b;
  letter-spacing: 0.01em;
}

.tc-detail-head-label {
  font-weight: 600;
  color: #5c5c5c;
  flex-shrink: 0;
}

.tc-detail-head-query {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: #737373;
}

.tc-detail-block {
  padding: 0;
  border-bottom: none;
}

.tc-detail-block + .tc-detail-block {
  margin-top: 8px;
}

.tc-detail-block-title {
  font-size: 10px;
  font-weight: 600;
  color: #a3a3a3;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  margin-bottom: 5px;
  padding-left: 1px;
}

.tc-args-list {
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.tc-arg-row {
  display: grid;
  grid-template-columns: minmax(56px, 24%) minmax(0, 1fr);
  gap: 6px 10px;
  align-items: start;
  padding: 6px 9px;
  background: #fff;
  border: 1px solid rgba(0, 0, 0, 0.05);
  border-radius: 8px;
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.03);
}

.tc-arg-key {
  font-size: 11px;
  font-weight: 500;
  color: #9ca3af;
  line-height: 1.4;
  word-break: break-word;
  padding-top: 1px;
}

.tc-arg-value {
  margin: 0;
  font-size: 12px;
  line-height: 1.45;
  color: #3f3f46;
  font-family: inherit;
  font-weight: 400;
  white-space: pre-wrap;
  word-break: break-word;
  overflow-wrap: anywhere;
  max-height: 64px;
  overflow-y: auto;
  scrollbar-width: thin;
  scrollbar-color: rgba(0, 0, 0, 0.12) transparent;
}

.tc-arg-value::-webkit-scrollbar {
  width: 4px;
}

.tc-arg-value::-webkit-scrollbar-thumb {
  background: rgba(0, 0, 0, 0.12);
  border-radius: 999px;
}

.tc-result-wrap {
  position: relative;
  width: 100%;
}

.tc-result-content {
  margin: 0;
  padding: 7px 9px 14px;
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
  overflow-y: auto;
  box-sizing: border-box;
  scrollbar-width: thin;
  scrollbar-color: rgba(0, 0, 0, 0.12) transparent;
}

.tc-result-content::-webkit-scrollbar {
  width: 4px;
}

.tc-result-content::-webkit-scrollbar-thumb {
  background: rgba(0, 0, 0, 0.12);
  border-radius: 999px;
}

.tc-result-resize-handle {
  position: absolute;
  right: 0;
  bottom: 0;
  width: 18px;
  height: 18px;
  display: flex;
  align-items: flex-end;
  justify-content: flex-end;
  padding: 0 3px 3px 0;
  cursor: ns-resize;
  touch-action: none;
  z-index: 1;
}

.tc-result-resize-grip {
  width: 8px;
  height: 8px;
  border-right: 2px solid rgba(0, 0, 0, 0.18);
  border-bottom: 2px solid rgba(0, 0, 0, 0.18);
  border-bottom-right-radius: 2px;
  opacity: 0.75;
  transition: opacity 0.15s ease, border-color 0.15s ease;
}

.tc-result-resize-handle:hover .tc-result-resize-grip,
.tc-result-resize-handle:active .tc-result-resize-grip {
  opacity: 1;
  border-color: rgba(0, 0, 0, 0.32);
}

.tc-detail-empty {
  margin: 0;
  padding: 10px 8px;
  font-size: 11.5px;
  color: #b4b4b4;
  text-align: center;
  background: rgba(255, 255, 255, 0.65);
  border: 1px dashed rgba(0, 0, 0, 0.07);
  border-radius: 8px;
}

@media (max-width: 520px) {
  .tc-arg-row {
    grid-template-columns: 1fr;
    gap: 3px;
  }

  .tc-pill-text {
    max-width: 200px;
  }
}
</style>

<!-- ToolsOption.vue -->
<template>
  <div class="tools-option-overlay" @click="handleOverlayClick">
    <div class="tools-option-container" @click.stop>
      <div class="tools-option-header">
        <div class="header-title-group">
          <p class="header-eyebrow">TOOLS</p>
          <h2>工具库</h2>
        </div>

        <button class="close-btn" @click="$emit('close')" aria-label="关闭">
          <svg width="11" height="11" viewBox="0 0 10 10" fill="none">
            <path d="M9 1L1 9M1 1L9 9" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/>
          </svg>
        </button>
      </div>

      <!-- 分页标签 -->
      <div class="tabs-container">
        <div class="tabs-track">
          <span
            class="tab-indicator"
            :style="{
              transform: `translateX(${activeTabIndex * 100}%)`,
              width: `${100 / tabs.length}%`
            }"
          ></span>
          <button
            v-for="tab in tabs"
            :key="tab.type"
            :class="['tab-btn', { active: activeTab === tab.type }]"
            @click="activeTab = tab.type"
          >
            <span class="tab-label">{{ tab.label }}</span>
            <span class="tab-count">{{ getToolsCountByType(tab.type) }}</span>
          </button>
        </div>
      </div>

      <!-- 工具列表内容 -->
      <div class="tools-content">
        <div v-if="loading" class="loading-state">
          <div class="loading-spinner"></div>
          <p>Loading tools...</p>
        </div>

        <div v-else-if="error" class="error-state">
          <p>{{ error }}</p>
          <button @click="fetchToolsInfo" class="retry-btn">Retry</button>
        </div>

        <div v-else class="tools-list">
          <div 
            v-for="(tools, classZh) in groupedTools" 
            :key="classZh"
            class="class-zh-group"
          >
            <!-- class_zh 分组头部 -->
            <div class="class-zh-header" @click="toggleClassZh(classZh)">
              <div class="class-zh-header-text">
                <h3 class="class-zh-name">{{ classZh }}</h3>
                <span class="class-zh-count">{{ tools.length }} 个工具</span>
              </div>
              <div class="class-zh-toggle">
                <svg 
                  :class="['toggle-icon', { expanded: expandedClassZh.includes(classZh) }]"
                  width="16" 
                  height="16" 
                  viewBox="0 0 16 16" 
                  fill="none"
                >
                  <path d="M4 6L8 10L12 6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                </svg>
              </div>
            </div>

            <!-- class_zh 分组下的工具列表 -->
            <div v-if="expandedClassZh.includes(classZh)" class="class-zh-tools">
              <div 
                v-for="tool in tools" 
                :key="tool.name"
                class="tool-item"
              >
                <div class="tool-shell">
                  <div 
                    class="tool-header"
                    @click="toggleTool(tool.name)"
                  >
                    <div class="tool-header-text">
                      <h3 class="tool-name">{{ tool.name }}</h3>
                      <p class="tool-description">{{ tool.description }}</p>
                    </div>
                    <div class="tool-toggle">
                      <svg 
                        :class="['toggle-icon', { expanded: expandedTools.includes(tool.name) }]"
                        width="16" 
                        height="16" 
                        viewBox="0 0 16 16" 
                        fill="none"
                      >
                        <path d="M4 6L8 10L12 6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                      </svg>
                    </div>
                  </div>

                  <!-- 展开的详细信息 -->
                  <div v-if="expandedTools.includes(tool.name)" class="tool-details">
                    <div v-if="tool.inputSchema?.properties" class="tool-properties">
                      <div class="properties-title-row">
                        <h4 class="properties-title">Parameters</h4>
                        <span class="properties-count">{{ Object.keys(tool.inputSchema.properties).length }}</span>
                      </div>
                      <div class="properties-list">
                        <div 
                          v-for="(property, key) in tool.inputSchema.properties" 
                          :key="key"
                          class="property-item"
                        >
                          <div class="property-header">
                            <span class="property-name">{{ key }}</span>
                            <span class="property-type">{{ property.type }}</span>
                            <span 
                              v-if="tool.inputSchema.required?.includes(key)" 
                              class="property-required"
                            >
                              required
                            </span>
                          </div>
                          <p v-if="property.description" class="property-description">
                            {{ property.description }}
                          </p>
                        </div>
                      </div>
                    </div>

                    <div v-else class="empty-parameters">暂无参数</div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- 空状态 -->
          <div v-if="Object.keys(groupedTools).length === 0" class="empty-state">
            <p>暂未找到{{ activeTab }}工具</p>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import axios from 'axios'

// 定义接口类型
interface PropertyInfo {
  type: string
  description?: string
}

interface InputSchema {
  type: string
  required?: string[]
  properties?: Record<string, PropertyInfo>
}

interface ToolsInfo {
  /** 旧版 Mongo 分渠道；新版合并后多为 local */
  type: 'sse' | 'http' | 'local' | 'project' | string
  sse_url?: string
  name: string
  description: string
  class_zh?: string
  inputSchema?: InputSchema
  code?: any
}

// 定义 emits
defineEmits<{
  close: []
}>()

// 响应式数据
const tools_info_list = ref<ToolsInfo[]>([])
const loading = ref<boolean>(false)
const error = ref<string>('')
// 新版后端工具统一为 type=local，默认选本地避免首屏空白（旧版仍可按渠道切换）
const activeTab = ref<'sse' | 'http' | 'local' | 'project'>('local')
const expandedTools = ref<string[]>([])
const expandedClassZh = ref<string[]>([])

// 标签配置
const tabs = [
  { type: 'local' as const, label: '系统工具' },
  { type: 'project' as const, label: '定制工具' },
  // { type: 'sse' as const, label: 'SSE工具' },
  // { type: 'http' as const, label: 'HTTP工具' },
]

// 计算属性：根据当前标签过滤工具并按 class_zh 分组
const groupedTools = computed(() => {
  const filtered = tools_info_list.value.filter(tool => tool.type === activeTab.value)
  const groups: Record<string, ToolsInfo[]> = {}
  
  filtered.forEach(tool => {
    const classZh = tool.class_zh || '未分类'
    if (!groups[classZh]) {
      groups[classZh] = []
    }
    groups[classZh].push(tool)
  })
  
  return groups
})

// 获取指定类型的工具数量
function getToolsCountByType(type: string): number {
  return tools_info_list.value.filter(tool => tool.type === type).length
}

// 当前 tab 的索引，用于驱动 segmented control 的滑动指示器
const activeTabIndex = computed(() =>
  Math.max(0, tabs.findIndex(t => t.type === activeTab.value))
)

// 切换工具详情展开/收起
const toggleTool = (toolName: string) => {
  const index = expandedTools.value.indexOf(toolName)
  if (index > -1) {
    expandedTools.value.splice(index, 1)
  } else {
    expandedTools.value.push(toolName)
  }
}

// 切换 class_zh 分组展开/收起
const toggleClassZh = (classZh: string) => {
  const index = expandedClassZh.value.indexOf(classZh)
  if (index > -1) {
    expandedClassZh.value.splice(index, 1)
  } else {
    expandedClassZh.value.push(classZh)
  }
}

// 获取工具信息
async function fetchToolsInfo(): Promise<void> {
  loading.value = true
  error.value = ''
  
  try {
    const response = await axios.get<ToolsInfo[]>('/api/tools_info')
    tools_info_list.value = response.data
  } catch (err) {
    console.error('获取工具信息失败:', err)
    error.value = 'Failed to load tools information'
  } finally {
    loading.value = false
  }
}

// 处理遮罩层点击
function handleOverlayClick() {
  // 点击遮罩层关闭弹窗
  // 这里可以添加确认逻辑
}

// 组件挂载时获取数据
onMounted(() => {
  fetchToolsInfo()
})
</script>

<style scoped>
.tools-option-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.tools-option-container {
  background: #ffffff;
  border-radius: 20px;
  width: 90%;
  max-width: 820px;
  max-height: 82vh;
  overflow: hidden;
  box-shadow:
    0 0 0 0.5px rgba(0, 0, 0, 0.06),
    0 24px 60px -12px rgba(0, 0, 0, 0.18),
    0 12px 24px -8px rgba(0, 0, 0, 0.08);
  display: flex;
  flex-direction: column;
}

/* ── Header (Apple-style light) ── */
.tools-option-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  padding: 26px 32px 18px;
  background: #ffffff;
}

.header-title-group {
  display: flex;
  flex-direction: column;
  gap: 7px;
  min-width: 0;
}

.header-eyebrow {
  margin: 0;
  font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Helvetica Neue', 'PingFang SC', sans-serif;
  font-size: 0.6875rem;
  font-weight: 600;
  color: #86868b;
  letter-spacing: 0.12em;
  line-height: 1;
  text-transform: uppercase;
}

.tools-option-header h2 {
  margin: 0;
  font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Display', 'Helvetica Neue', 'PingFang SC', sans-serif;
  font-size: 1.5rem;
  font-weight: 500;
  color: #1d1d1f;
  letter-spacing: -0.022em;
  line-height: 1.18;
}

.header-subtitle {
  margin: 0;
  font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Helvetica Neue', 'PingFang SC', sans-serif;
  font-size: 0.8125rem;
  font-weight: 400;
  color: #86868b;
  letter-spacing: -0.005em;
  line-height: 1.3;
}

.close-btn {
  width: 30px;
  height: 30px;
  background: rgba(0, 0, 0, 0.04);
  border: none;
  cursor: pointer;
  color: #86868b;
  border-radius: 50%;
  display: grid;
  place-items: center;
  transition: background 0.2s ease, color 0.2s ease, transform 0.2s ease;
  flex-shrink: 0;
  margin-top: 4px;
}

.close-btn:hover {
  background: rgba(0, 0, 0, 0.08);
  color: #1d1d1f;
}

.close-btn:active {
  transform: scale(0.94);
}

/* ── Tabs (Apple Segmented Control) ── */
.tabs-container {
  padding: 4px 32px 22px;
  background: #ffffff;
  box-shadow: 0 1px 0 rgba(0, 0, 0, 0.05);
  position: relative;
  z-index: 1;
}

.tabs-track {
  position: relative;
  display: inline-flex;
  background: #f5f5f7;
  border-radius: 9px;
  padding: 0;
  isolation: isolate;
}

.tab-indicator {
  position: absolute;
  top: 0;
  left: 0;
  bottom: 0;
  background: #ffffff;
  border-radius: 9px;
  box-shadow:
    0 3px 8px rgba(0, 0, 0, 0.06),
    0 1px 2px rgba(0, 0, 0, 0.04),
    0 0 0 0.5px rgba(0, 0, 0, 0.04);
  transition: transform 0.35s cubic-bezier(0.32, 0.72, 0, 1);
  pointer-events: none;
  z-index: 0;
}

.tab-btn {
  background: transparent;
  border: none;
  padding: 8px 22px;
  margin: 0;
  cursor: pointer;
  color: #6e6e73;
  font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Helvetica Neue', 'PingFang SC', sans-serif;
  font-size: 0.8125rem;
  font-weight: 500;
  letter-spacing: -0.01em;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  white-space: nowrap;
  position: relative;
  z-index: 1;
  transition: color 0.25s ease;
  min-width: 124px;
}

.tab-btn:hover:not(.active) {
  color: #1d1d1f;
}

.tab-btn.active {
  color: #1d1d1f;
  font-weight: 600;
}

.tab-count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 18px;
  height: 16px;
  padding: 0 5px;
  background: rgba(0, 0, 0, 0.05);
  color: #86868b;
  border-radius: 4px;
  font-size: 0.6875rem;
  font-weight: 500;
  letter-spacing: 0;
  transition: background 0.25s ease, color 0.25s ease;
}

.tab-btn.active .tab-count {
  background: rgba(0, 0, 0, 0.08);
  color: #1d1d1f;
}

.tools-content {
  flex: 1;
  overflow-y: auto;
  padding: 24px 32px 28px;
  background: #f5f5f7;
  font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Helvetica Neue', 'PingFang SC', sans-serif;
}

.loading-state,
.error-state,
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 56px 40px;
  text-align: center;
  color: #86868b;
  font-size: 0.875rem;
  letter-spacing: -0.005em;
}

.loading-spinner {
  width: 28px;
  height: 28px;
  border: 2px solid rgba(0, 0, 0, 0.06);
  border-top-color: #1d1d1f;
  border-radius: 50%;
  animation: spin 0.9s linear infinite;
  margin-bottom: 14px;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.retry-btn {
  margin-top: 14px;
  padding: 7px 18px;
  background: #1d1d1f;
  color: #ffffff;
  border: none;
  border-radius: 980px;
  cursor: pointer;
  font-family: inherit;
  font-size: 0.8125rem;
  font-weight: 500;
  letter-spacing: -0.005em;
  transition: background-color 0.2s ease, transform 0.2s ease;
}

.retry-btn:hover {
  background: #000;
}

.retry-btn:active {
  transform: scale(0.97);
}

.tools-list {
  display: flex;
  flex-direction: column;
  gap: 26px;
}

.class-zh-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.class-zh-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 4px 6px 10px;
  cursor: pointer;
  background: transparent;
  border: none;
  border-radius: 0;
  transition: opacity 0.2s ease;
}

.class-zh-header:hover {
  opacity: 0.7;
}

.class-zh-header-text {
  display: flex;
  align-items: baseline;
  gap: 10px;
  flex: 1;
  min-width: 0;
}

.class-zh-name {
  margin: 0;
  font-size: 0.8125rem;
  font-weight: 600;
  color: #6e6e73;
  letter-spacing: 0.06em;
  line-height: 1.3;
  text-transform: uppercase;
}

.class-zh-count {
  background: transparent;
  color: #a1a1a6;
  padding: 0;
  border-radius: 0;
  font-size: 0.75rem;
  font-weight: 500;
  letter-spacing: 0.02em;
}

.class-zh-toggle {
  flex-shrink: 0;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  background: transparent;
  color: #a1a1a6;
  transition: color 0.2s ease;
}

.class-zh-header:hover .class-zh-toggle {
  color: #1d1d1f;
}

.class-zh-tools {
  display: flex;
  flex-direction: column;
  gap: 0;
  padding: 0;
  background: #ffffff;
  border-radius: 14px;
  border: 1px solid rgba(0, 0, 0, 0.05);
  box-shadow:
    0 1px 2px rgba(0, 0, 0, 0.03),
    0 0 0 0.5px rgba(0, 0, 0, 0.02);
  overflow: hidden;
}

.tool-item {
  position: relative;
}

.tool-item + .tool-item {
  border-top: 1px solid rgba(0, 0, 0, 0.05);
}

.tool-shell {
  border: none;
  border-radius: 0;
  background: transparent;
  box-shadow: none;
  overflow: hidden;
  transition: background 0.18s ease;
}

.tool-shell:hover {
  background: rgba(0, 0, 0, 0.02);
}

.tool-header {
  display: flex;
  justify-content: space-between;
  gap: 14px;
  align-items: center;
  padding: 14px 18px;
  cursor: pointer;
  background: transparent;
  transition: background 0.2s ease;
}

.tool-header-text {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.tool-name {
  margin: 0;
  font-size: 0.9375rem;
  font-weight: 500;
  color: #1d1d1f;
  letter-spacing: -0.012em;
  line-height: 1.35;
}

.tool-description {
  margin: 0;
  color: #86868b;
  font-size: 0.8125rem;
  font-weight: 400;
  line-height: 1.45;
  letter-spacing: -0.005em;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
}

.tool-toggle {
  flex-shrink: 0;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  background: transparent;
  color: #86868b;
  transition: background 0.2s ease, color 0.2s ease;
}

.tool-header:hover .tool-toggle {
  background: rgba(0, 0, 0, 0.05);
  color: #1d1d1f;
}

.toggle-icon {
  transition: transform 0.25s cubic-bezier(0.32, 0.72, 0, 1);
}

.toggle-icon.expanded {
  transform: rotate(180deg);
}

.tool-details {
  padding: 16px 18px 18px;
  background: #f5f5f7;
  border-top: 1px solid rgba(0, 0, 0, 0.05);
}

.properties-title-row {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin-bottom: 10px;
}

.properties-title {
  margin: 0;
  font-size: 0.6875rem;
  font-weight: 600;
  color: #86868b;
  letter-spacing: 0.1em;
  text-transform: uppercase;
}

.properties-count {
  min-width: 0;
  padding: 0;
  border-radius: 0;
  background: transparent;
  color: #86868b;
  font-size: 0.6875rem;
  font-weight: 400;
  letter-spacing: 0.04em;
  text-align: left;
}

.properties-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.property-item {
  padding: 11px 14px;
  background: #ffffff;
  border-radius: 10px;
  border: 1px solid rgba(0, 0, 0, 0.04);
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.02);
  transition: border-color 0.2s ease, box-shadow 0.2s ease;
}

.property-item:hover {
  border-color: rgba(0, 0, 0, 0.08);
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.04);
}

.property-header {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-bottom: 2px;
}

.property-name {
  font-family: 'SF Mono', ui-monospace, 'Menlo', 'Consolas', monospace;
  font-weight: 500;
  color: #1d1d1f;
  font-size: 0.8125rem;
  letter-spacing: -0.005em;
}

.property-type {
  background: rgba(0, 0, 0, 0.05);
  color: #6e6e73;
  padding: 1px 7px;
  border-radius: 4px;
  font-family: 'SF Mono', ui-monospace, 'Menlo', 'Consolas', monospace;
  font-size: 0.6875rem;
  font-weight: 500;
  letter-spacing: 0;
}

.property-required {
  background: transparent;
  color: #ff453a;
  padding: 0;
  border-radius: 0;
  font-size: 0.6875rem;
  font-weight: 500;
  letter-spacing: 0.02em;
  text-transform: lowercase;
}

.property-description {
  margin: 4px 0 0 0;
  color: #6e6e73;
  font-size: 0.8125rem;
  font-weight: 400;
  line-height: 1.5;
  letter-spacing: -0.005em;
}

.empty-parameters {
  padding: 12px 0 4px;
  color: #86868b;
  font-size: 0.8125rem;
  font-weight: 400;
  letter-spacing: -0.005em;
}

/* 响应式设计 */
@media (max-width: 640px) {
  .tools-option-container {
    width: 95%;
    max-height: 90vh;
    border-radius: 16px;
  }

  .tools-option-header {
    padding: 22px 20px 16px;
  }

  .tools-option-header h2 {
    font-size: 1.375rem;
  }

  .header-eyebrow {
    font-size: 0.625rem;
  }

  .tabs-container {
    padding: 4px 20px 18px;
  }

  .tabs-track {
    width: 100%;
  }

  .tab-btn {
    padding: 7px 14px;
    font-size: 0.78125rem;
    min-width: 0;
    flex: 1;
  }

  .tools-content {
    padding: 20px 20px 24px;
  }

  .property-header {
    flex-wrap: wrap;
  }
}
</style>
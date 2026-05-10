<template>
  <div class="extra-info">
    <!-- Tab 切换栏 -->
    <div class="tab-container">
      <div 
        class="tab-item" 
        :class="{ active: activeTab === 'tools' }"
        @click="activeTab = 'tools'"
      >
        <span class="tab-icon">🛠️</span>
        <span class="tab-text">工具信息</span>
      </div>
      <div 
        class="tab-item" 
        :class="{ active: activeTab === 'files' }"
        @click="activeTab = 'files'"
      >
        <span class="tab-icon">📁</span>
        <span class="tab-text">文件库</span>
      </div>
    </div>

    <!-- 工具信息内容 -->
    <div v-if="activeTab === 'tools'" class="tool-messages" ref="toolMessagesContainer" @scroll="handleScroll">
      <div v-for="(group, index) in groupedToolMessages" :key="group.tool_call_id" class="tool-message">
        <div class="tool-frame" :class="{ highlighted: props.highlightedId === group.tool_call_id }" :ref="el => toolRefs[index] = el as HTMLElement">
          <div class="content-container" :class="{ expanded: isExpanded(group.tool_call_id), 'needs-expand': needsExpand[index] }" :ref="el => contentRefs[index] = el">
            <template v-for="(msg, msgIndex) in group.messages" :key="msgIndex">
              <!-- Handle different types for each message -->
              <div v-if="msg.type === 'event'" class="answer-robot-event">
                {{ msg.content }}
              </div>
              
              <div v-else-if="(msg.type === 'get_tools' || (msg.type === 'tool' && msg.role !== 'agent')) && msg.tool_calls" class="answer-robot-tool-wrapper">
                <!-- 先显示 content（如果存在） -->
                <div v-if="msg.content && msg.content.trim()" class="text-message-wrapper">
                  <div class="answer-robot-content">
                    <div class="p-content-markdown" v-html="renderMarkdown(msg.content)"></div>
                  </div>
                </div>
                <div class="answer-robot-tool">
                  <template v-for="(toolCall, toolIndex) in msg.tool_calls" :key="toolIndex">
                    <div class="answer-robot-tool-name-extra">
                      🛠️ {{ toolCall.function.name }} 
                    </div>
                    <div class="answer-robot-tool-args">
                      <div v-for="(value, key) in parseArguments(toolCall.function.arguments)" :key="key" class="arg-item">
                        <span class="arg-key">{{ key }}:</span>
                        <span class="arg-value">{{ value }}</span>
                      </div>
                    </div>
                  </template>
                </div>
              </div>
              
              <div v-else-if="msg.type === 'get_agents' && msg.tool_calls && msg.role !== 'agent'" class="answer-robot-tool-wrapper">
                <!-- 先显示 content（如果存在） -->
                <div v-if="msg.content && msg.content.trim()" class="text-message-wrapper">
                  <div class="answer-robot-content">
                    <div class="p-content-markdown" v-html="renderMarkdown(msg.content)"></div>
                  </div>
                </div>
                <div class="answer-robot-tool">
                  <template v-for="(toolCall, toolIndex) in msg.tool_calls" :key="toolIndex">
                    <div class="answer-robot-tool-name-extra">
                      ⚙️ {{ toolCall.function.name }} 
                    </div>
                    <div class="answer-robot-tool-args">
                      <div v-for="(value, key) in parseArguments(toolCall.function.arguments)" :key="key" class="arg-item">
                        <span class="arg-key">{{ key }}:</span>
                        <span class="arg-value">{{ value }}</span>
                      </div>
                    </div>
                  </template>
                </div>
              </div>
              
              <div v-else-if="msg.type === 'agent_for_frontend'" class="answer-robot-tool">
                <div class="answer-robot-tool-name-extra">
                  ⚙️ {{ msg.content }} 
                </div>
              </div>
              
              <div v-else-if="msg.role === 'agent' && msg.type !== 'tool'" class="text-message-wrapper">
                <div class="answer-robot-content">
                  <div class="p-content-markdown" v-html="renderMarkdown(msg.content ?? '')"></div>
                </div>
              </div>
              <div v-else-if="msg.type === 'text' || msg.role === 'tool'" class="text-message-wrapper">
              <div class="answer-robot-content">
                  <div class="p-content-markdown" v-html="renderMarkdown(msg.content ?? '')"></div>
                </div>
              </div>
              <div v-else-if="msg.type === 'reasoner_content'" class="answer-robot-reasoner">
                <div class="p-content-markdown" v-html="renderMarkdown(msg.content ?? '')"></div>
              </div>
            </template>
          </div>
          <button v-if="needsExpand[index] || isExpanded(group.tool_call_id)" @click="toggleExpand(group.tool_call_id, true)" class="expand-button">
            <span class="arrow-icon" v-if="isExpanded(group.tool_call_id)">▲</span>
            <span class="arrow-icon" v-else>▼</span>
          </button>
        </div>
      </div>
    </div>

    <!-- 文件库内容（内嵌显示） -->
    <div v-if="activeTab === 'files'" class="file-library-content">
      <div class="file-library-body">
        <div class="left-preview" v-if="selectedFile">
          <div class="preview-header">
            <h4>{{ selectedFile }}</h4>
            <div class="header-actions">
              <button v-if="isEditableFile && !isEditing" class="edit-button" @click="startEditing">
                编辑
              </button>
              <div v-if="isHtml && !isEditing" class="export-container">
                <button class="export-button" @click="toggleExportOptions">
                  导出
                </button>
                <div v-if="showExportOptions" class="export-dropdown">
                  <button class="dropdown-item" @click="exportWithFormat('pdf')">PDF</button>
                  <button class="dropdown-item" @click="exportWithFormat('pptx')">PPTX</button>
                </div>
              </div>
              <img v-if="!isEditing" :src="DownloadIcon" alt="下载" class="icon-button" @click="downloadFile(selectedFile)" />
            </div>
            <div v-if="exporting" class="export-feedback">导出中...</div>
            <div v-if="exportSuccess" class="export-feedback success">导出成功！</div>
            <div v-if="exportError" class="export-feedback error">{{ exportError }}</div>
          </div>
          <div class="preview-content">
            <div v-if="previewError" class="error">{{ previewError }}</div>
            <img v-else-if="isImage" :src="fileUrl" alt="Image Preview" class="preview-image" />
            <iframe v-else-if="isHtml" :src="fileUrl" class="html-iframe" frameborder="0" sandbox="allow-scripts allow-same-origin allow-forms"></iframe>
            <VueOfficeExcel v-else-if="isExcel" :src="fileUrl" />
            <VueOfficePdf v-else-if="isPdf" :src="fileUrl" />
            <VueOfficePptx v-else-if="isPpt" :src="fileUrl" />
            <div v-else-if="isDocx" v-html="fileContent"></div>
            <div v-else v-html="renderMarkdown(processedFileContent)"></div>
          </div>
        </div>
        <div class="left-preview" v-else>
          <p class="no-selection">请选择一个文件进行预览</p>
        </div>
        <div class="right-sidebar" :class="{ 'collapsed': !isFileListExpanded }">
          <div class="file-list-header">
            <button class="file-list-toggle-button" @click="toggleFileList" :title="isFileListExpanded ? '收起' : '展开'">
              <img :src="InfoIcon" alt="" class="file-toggle-icon" :class="{ 'rotated-left': isFileListExpanded, 'rotated-right': !isFileListExpanded }" />
            </button>
            <span class="file-list-title" v-if="isFileListExpanded">文件列表</span>
            <div class="header-actions-group">
              <img v-if="isFileListExpanded" :src="RefreshIcon" alt="刷新" title="刷新" class="icon-button" @click="fetchFiles" />
            </div>
          </div>
          <div v-if="isFileListExpanded" class="file-list-content">
            <div v-if="visibleFileNodes.length > 0" class="file-tree">
              <div
                v-for="node in visibleFileNodes"
                :key="node.key"
                class="file-tree-node"
                :class="{
                  folder: node.type === 'folder',
                  file: node.type === 'file',
                  selected: node.type === 'file' && node.path === selectedFileNormalized
                }"
                :style="{ paddingLeft: `${12 + node.level * 16}px` }"
                @click="handleTreeNodeClick(node)"
              >
                <span class="tree-arrow" :class="{ placeholder: node.type === 'file' }">
                  {{ node.type === 'folder' ? (isFolderExpanded(node.path) ? '▾' : '▸') : '·' }}
                </span>
                <span class="tree-icon">
                  {{ node.type === 'folder' ? (isFolderExpanded(node.path) ? '📂' : '📁') : '📄' }}
                </span>
                <span class="file-name">{{ node.name }}</span>
              </div>
            </div>
            <div v-else class="empty-file-list">
              <p>暂无文件</p>
              <p class="empty-hint">文件将在这里显示</p>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 全屏文件库弹窗 -->
    <div v-if="showFileLibrary" class="file-library-full-panel">
      <div class="full-panel-header">
        <h3>
          <span class="header-title">
            文件库
            <img :src="RefreshIcon" alt="刷新" class="icon-button" @click="fetchFiles" />
          </span>
          <span @click="closeEditPanel" class="close-button">×</span>
        </h3>
      </div>
      <div class="full-panel-content">
        <div class="left-sidebar" :class="{ 'collapsed': !isFileListExpanded }">
          <div class="file-list-header">
            <button class="file-list-toggle-button" @click="toggleFileList" :title="isFileListExpanded ? '收起' : '展开'">
              <img :src="InfoIcon" alt="" class="file-toggle-icon" :class="{ 'rotated-left': isFileListExpanded, 'rotated-right': !isFileListExpanded }" />
            </button>
            <span class="file-list-title" v-if="isFileListExpanded">文件列表</span>
            <div class="header-actions-group">
              <img v-if="isFileListExpanded" :src="RefreshIcon" alt="刷新" title="刷新" class="icon-button" @click="fetchFiles" />
            </div>
          </div>
          <div v-if="isFileListExpanded" class="file-list-content">
            <div v-if="visibleFileNodes.length > 0" class="file-tree">
              <div
                v-for="node in visibleFileNodes"
                :key="node.key"
                class="file-tree-node"
                :class="{
                  folder: node.type === 'folder',
                  file: node.type === 'file',
                  selected: node.type === 'file' && node.path === selectedFileNormalized
                }"
                :style="{ paddingLeft: `${12 + node.level * 16}px` }"
                @click="handleTreeNodeClick(node)"
              >
                <span class="tree-arrow" :class="{ placeholder: node.type === 'file' }">
                  {{ node.type === 'folder' ? (isFolderExpanded(node.path) ? '▾' : '▸') : '·' }}
                </span>
                <span class="tree-icon">
                  {{ node.type === 'folder' ? (isFolderExpanded(node.path) ? '📂' : '📁') : '📄' }}
                </span>
                <span class="file-name">{{ node.name }}</span>
              </div>
            </div>
            <div v-else class="empty-file-list">
              <p>暂无文件</p>
              <p class="empty-hint">文件将在这里显示</p>
            </div>
          </div>
        </div>
        <div class="right-preview" v-if="selectedFile">
          <div class="preview-header">
            <h4>{{ selectedFile }}</h4>
            <div class="header-actions">
              <button v-if="isEditableFile && !isEditing" class="edit-button" @click="startEditing">
                编辑
              </button>
              <button v-if="isEditing && isMarkdownFile" :class="{ 'mode-button': true, 'active': editMode === 'markdown' }" @click="switchEditMode('markdown')">
                📝 Markdown
              </button>
              <button v-if="isEditing && isMarkdownFile" :class="{ 'mode-button': true, 'active': editMode === 'source' }" @click="switchEditMode('source')">
                💻 源码
              </button>
              <div class="button-separator"></div>
              <button v-if="isEditing" class="save-button" @click="saveFile" :disabled="saving">
                {{ saving ? '保存中...' : '保存' }}
              </button>
              <button v-if="isEditing" class="cancel-button last-button" @click="() => cancelEditing()">
                退出编辑
              </button>
              <div v-if="isHtml && !isEditing" class="export-container">
                <button class="export-button" @click="toggleExportOptions">
                  导出
                </button>
                <div v-if="showExportOptions" class="export-dropdown">
                  <button class="dropdown-item" @click="exportWithFormat('pdf')">PDF</button>
                  <button class="dropdown-item" @click="exportWithFormat('pptx')">PPTX</button>
                </div>
              </div>
              <img v-if="!isEditing" :src="DownloadIcon" alt="下载" class="icon-button" @click="downloadFile(selectedFile)" />
            </div>
            <div v-if="exporting" class="export-feedback">导出中...</div>
            <div v-if="exportSuccess" class="export-feedback success">导出成功！</div>
            <div v-if="exportError" class="export-feedback error">{{ exportError }}</div>
          </div>
          <div class="preview-content">
            <div v-if="previewError" class="error">{{ previewError }}</div>
            <div v-else-if="isEditing" class="edit-content">
              <!-- Markdown模式 -->
              <div v-if="editMode === 'markdown' && isMarkdownFile" class="markdown-editor-container">
                <div id="markdown-editor" class="markdown-editor"></div>
              </div>
              <!-- 源码模式 -->
              <textarea
                v-else
                v-model="editedContent"
                class="edit-textarea"
                placeholder="在此编辑文件内容..."
                @keydown="handleKeyDown"
                ref="editTextarea"
              ></textarea>
              <div v-if="saveSuccess" class="save-feedback success">保存成功</div>
              <div v-if="saveError" class="save-feedback error">{{ saveError }}</div>
            </div>
            <img v-else-if="isImage" :src="fileUrl" alt="Image Preview" class="preview-image" />
            <iframe v-else-if="isHtml" :src="fileUrl" class="html-iframe" frameborder="0" sandbox="allow-scripts allow-same-origin allow-forms"></iframe>
            <VueOfficeExcel v-else-if="isExcel" :src="fileUrl" />
            <VueOfficePdf v-else-if="isPdf" :src="fileUrl" />
            <VueOfficePptx v-else-if="isPpt" :src="fileUrl" />
            <div v-else-if="isDocx" v-html="fileContent"></div>
            <div v-else v-html="renderMarkdown(processedFileContent)"></div>
          </div>
        </div>
        <div class="right-preview" v-else>
          <p class="no-selection">请选择一个文件进行预览</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script lang="ts" setup>
import { computed, ref, onMounted, onUnmounted, nextTick, watch, onErrorCaptured } from 'vue'
import type { AgentMessage } from '../types/interface'
import MarkdownIt from 'markdown-it'
import hljs from 'highlight.js'
import 'highlight.js/styles/github.css'
// @ts-ignore
import CopyIcon from '@/assets/images/copy_icon.svg?url'
// @ts-ignore
import SuccessIcon from '@/assets/images/success_icon.svg?url'
import axios from 'axios'; // 假设使用axios，如果有自定义api，请调整
// @ts-ignore
import RefreshIcon from '@/assets/images/refresh_icon.svg?url'
// @ts-ignore
import DownloadIcon from '@/assets/images/download_icon.svg?url'
// @ts-ignore
import FileLibraryIcon from '@/assets/images/file_library_icon.svg?url'
// @ts-ignore
import InfoIcon from '@/assets/images/info_icon.svg?url'
// Import vue-office components (user needs to install @vue-office/docx, @vue-office/excel, @vue-office/pdf, etc.)
import VueOfficeDocx from '@vue-office/docx'
import '@vue-office/docx/lib/index.css'
import VueOfficeExcel from '@vue-office/excel'
import '@vue-office/excel/lib/index.css'
import VueOfficePdf from '@vue-office/pdf'
// For PPT, there might not be a direct vue-office, so handle as needed

import VueOfficePptx from '@vue-office/pptx'
import mammoth from 'mammoth';

// Toast UI Editor imports
import Editor from '@toast-ui/editor'
import '@toast-ui/editor/dist/toastui-editor.css'
import codeSyntaxHighlight from '@toast-ui/editor-plugin-code-syntax-highlight'
import 'highlight.js/styles/github.css'

const props = defineProps<{ 
  toolMessages: AgentMessage[]
  fileMessages: AgentMessage[] // 新增：文件消息列表
  highlightedId: string | null
  scrollToId: string | null
  toggleTrigger: number
  conversationId: string // 新增
}>()

const groupedToolMessages = computed(() => {
  const groups: any[] = []  // 或定义接口
  const map = new Map()
  props.toolMessages.forEach(msg => {
    // 对于 role=agent 的消息：直接使用 tool_call_id（这个应该对应初始 get_agents 的 id）
    // 这个判断要放在最前面，因为 role=agent 的消息可能也有 tool_calls
    if (msg.role === 'agent' && msg.tool_call_id) {
      const id = msg.tool_call_id
      if (!map.has(id)) {
        map.set(id, {
          tool_call_id: id,
          messages: []
        })
      }
      const group = map.get(id)
      if (msg.type === 'text' || msg.type === 'reasoner_content') {
        if (group.messages.length && group.messages[group.messages.length - 1].type === msg.type) {
          group.messages[group.messages.length - 1].content += (msg.content || '')
        } else {
          group.messages.push({
            type: msg.type,
            content: msg.content || ''
          })
        }
      } else {
        group.messages.push(msg)
      }
    }
    // 如果消息有多个 tool_calls，需要为每个 tool_call 创建单独的组
    else if (msg.tool_calls && msg.tool_calls.length > 0) {
      // 对于 get_agents 类型（且 role !== 'agent'）：只使用第一个 tool_call.id（因为 get_agents 应该只有一个 tool_call）
      if (msg.type === 'get_agents' && msg.role !== 'agent' && msg.tool_calls[0].id) {
        const id = msg.tool_calls[0].id
        if (!map.has(id)) {
          map.set(id, {
            tool_call_id: id,
            messages: []
          })
        }
        const group = map.get(id)
        group.messages.push(msg)
      }
      // 对于其他类型（如 get_tools）：为每个 tool_call 创建单独的组
      else {
        msg.tool_calls.forEach((toolCall) => {
          if (toolCall.id) {
            const id = toolCall.id
            if (!map.has(id)) {
              map.set(id, {
                tool_call_id: id,
                messages: []
              })
            }
            const group = map.get(id)
            // 创建只包含当前 tool_call 的消息副本
            const msgCopy = { ...msg, tool_calls: [toolCall] }
            group.messages.push(msgCopy)
          }
        })
      }
    }
    // 对于 role=tool 的消息：根据 tool_call_id 匹配到对应的组
    else if (msg.role === 'tool' && msg.tool_call_id) {
      const id = msg.tool_call_id
      if (!map.has(id)) {
        map.set(id, {
          tool_call_id: id,
          messages: []
        })
      }
      const group = map.get(id)
      group.messages.push(msg)
    }
    // 对于其他没有 tool_calls 的消息
    else {
      let id: string
      if (msg.tool_call_id) {
        id = msg.tool_call_id
      } else {
        id = String(msg.created_at)
      }
      
      if (!map.has(id)) {
        map.set(id, {
          tool_call_id: id,
          messages: []
        })
      }
      const group = map.get(id)
      if (msg.type === 'text' || msg.type === 'reasoner_content') {
        if (group.messages.length && group.messages[group.messages.length - 1].type === msg.type) {
          group.messages[group.messages.length - 1].content += (msg.content || '')
        } else {
          group.messages.push({
            type: msg.type,
            content: msg.content || ''
          })
        }
      } else if (msg.type === 'plan') {
        if (group.messages.length && group.messages[group.messages.length - 1].type === 'plan') {
          group.messages[group.messages.length - 1].content += (msg.content || '')
        } else {
          group.messages.push({
            type: 'plan',
            content: msg.content || ''
          })
        }
      } else {
        group.messages.push(msg)
      }
    }
  })
  map.forEach(g => {
    groups.push(g)
  })
  // plan 已在 ChatWindow 主对话展示，侧栏不再展示，并去掉仅含 plan 的空框
  return groups
    .map((g) => ({
      ...g,
      messages: g.messages.filter((m) => m.type !== 'plan')
    }))
    .filter((g) => g.messages.length > 0)
})

// 移除占位符renderMarkdown和相关注释
// 添加必要的导入和markdown配置

// 定义md - 使用 'default' preset 确保表格支持
const md = new MarkdownIt('default', {
  html: true,
  breaks: true,
  linkify: true,
  typographer: true,
  highlight: function (str, lang) {
    if (lang && hljs.getLanguage(lang)) {
      try {
        return hljs.highlight(str, { language: lang }).value
      } catch (__) {}
    }
    return ''
  }
})

md.renderer.rules.fence = (tokens, idx, options, env, slf) => {
  const token = tokens[idx]
  const lang = token.info.trim() || 'text'
  const code = token.content
  let highlighted = ''
  if (lang && hljs.getLanguage(lang)) {
    try {
      highlighted = hljs.highlight(code, { language: lang }).value
    } catch (e) {
      // Ignore highlight error
    }
  }
  if (!highlighted) {
    highlighted = md.utils.escapeHtml(code)
  }
  const titleBar = `
<div class="code-title">
  <span class="code-lang">${lang}</span>
  <img src="${CopyIcon}" alt="copy" class="code-copy-btn" />
</div>
  `
  const codeBlock = `<pre class="hljs"><code>${highlighted}</code></pre>`
  return `<div class="code-wrapper">${titleBar}${codeBlock}</div>`
}

// 自定义表格渲染规则，确保表格有正确的样式
md.renderer.rules.table_open = () => '<table class="markdown-table">'
md.renderer.rules.table_close = () => '</table>'

// renderMarkdown 结果缓存：流式时大量内容不变，避免重复解析
const markdownCache = new Map<string, string>()
const MARKDOWN_CACHE_MAX = 150

function renderMarkdown(content: string) {
  const key = content ?? ''
  const cached = markdownCache.get(key)
  if (cached !== undefined) return cached

  let html: string
  try {
    const parsed = JSON.parse(content)
    html = renderStructured(parsed)
  } catch (e) {
    html = md.render(content ?? '')
    html = html.replace(/<a /g, '<a target="_blank" rel="noopener noreferrer" ')
  }

  markdownCache.set(key, html)
  if (markdownCache.size > MARKDOWN_CACHE_MAX) {
    const firstKey = markdownCache.keys().next().value
    if (firstKey !== undefined) markdownCache.delete(firstKey)
  }
  return html
}

// 添加renderStructured函数
function renderStructured(data: any): string {
  if (Array.isArray(data)) {
    return data.map((item: any, index: number) => 
      '<div class="structured-item">' +
      (typeof item === 'object' && item !== null ? renderStructured(item) : escapeHtml(item.toString())) +
      '</div>'
    ).join('');
  } else if (typeof data === 'object' && data !== null) {
    return '<table class="structured-table"><tbody>' + 
      Object.entries(data).map(([key, value]: [string, any]) => '<tr><td>' + escapeHtml(key) + '</td><td>' + (typeof value === 'object' && value !== null ? renderStructured(value) : escapeHtml(value.toString())) + '</td></tr>').join('') + 
      '</tbody></table>';
  } else {
    return escapeHtml(data.toString());
  }
}

// 添加escapeHtml函数以防止XSS
function escapeHtml(unsafe) {
  return unsafe
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

// 为refs添加类型
const expanded = ref<Map<string, boolean>>(new Map())
  const contentRefs = ref<any[]>([])
const needsExpand = ref<boolean[]>([])
  const isManuallyCollapsed = ref<Map<string, boolean>>(new Map())
const toolRefs = ref<HTMLElement[]>([])
const toolMessagesContainer = ref<HTMLElement | null>(null)
const isAutoScroll = ref(true)

const files = ref<string[]>([]);
const selectedFile = ref<string | null>(null)
const fileContent = ref<string>('')
const previewError = ref<string>('')
const expandedFolders = ref<Set<string>>(new Set())

type TreeNodeType = 'folder' | 'file'
type FileTreeNode = {
  name: string
  path: string
  type: TreeNodeType
  children: Map<string, FileTreeNode>
}

type VisibleFileTreeNode = {
  key: string
  name: string
  path: string
  type: TreeNodeType
  level: number
}

const normalizeFilePath = (filePath: string): string => {
  return (filePath || '')
    .replace(/\\/g, '/')
    .replace(/^\/+/, '')
    .trim()
}

const selectedFileNormalized = computed(() => {
  return selectedFile.value ? normalizeFilePath(selectedFile.value) : ''
})

const normalizedFilePathMap = computed(() => {
  const map = new Map<string, string>()
  files.value.forEach((rawPath) => {
    const normalizedPath = normalizeFilePath(rawPath)
    if (normalizedPath && !map.has(normalizedPath)) {
      map.set(normalizedPath, rawPath)
    }
  })
  return map
})

const fileTree = computed(() => {
  const root = new Map<string, FileTreeNode>()

  files.value.forEach((rawPath) => {
    const normalizedPath = normalizeFilePath(rawPath)
    if (!normalizedPath) return

    const segments = normalizedPath.split('/').filter(Boolean)
    let cursor = root
    let currentPath = ''

    segments.forEach((segment, index) => {
      const isLeaf = index === segments.length - 1
      currentPath = currentPath ? `${currentPath}/${segment}` : segment

      if (!cursor.has(segment)) {
        cursor.set(segment, {
          name: segment,
          path: currentPath,
          type: isLeaf ? 'file' : 'folder',
          children: new Map()
        })
      }

      const node = cursor.get(segment)!
      if (!isLeaf) {
        node.type = 'folder'
      }
      cursor = node.children
    })
  })

  return root
})

const sortTreeNodes = (nodes: FileTreeNode[]) => {
  return nodes.sort((a, b) => {
    if (a.type !== b.type) {
      return a.type === 'folder' ? -1 : 1
    }
    return a.name.localeCompare(b.name, 'zh-CN')
  })
}

const visibleFileNodes = computed<VisibleFileTreeNode[]>(() => {
  const result: VisibleFileTreeNode[] = []

  const walk = (nodesMap: Map<string, FileTreeNode>, level: number) => {
    const nodes = sortTreeNodes(Array.from(nodesMap.values()))
    nodes.forEach((node) => {
      result.push({
        key: `${node.type}:${node.path}`,
        name: node.name,
        path: node.path,
        type: node.type,
        level
      })

      if (node.type === 'folder' && expandedFolders.value.has(node.path)) {
        walk(node.children, level + 1)
      }
    })
  }

  walk(fileTree.value, 0)
  return result
})

const isFolderExpanded = (folderPath: string) => {
  return expandedFolders.value.has(folderPath)
}

const toggleFolderExpand = (folderPath: string) => {
  const next = new Set(expandedFolders.value)
  if (next.has(folderPath)) {
    next.delete(folderPath)
  } else {
    next.add(folderPath)
  }
  expandedFolders.value = next
}

const handleTreeNodeClick = async (node: VisibleFileTreeNode) => {
  if (node.type === 'folder') {
    toggleFolderExpand(node.path)
    return
  }

  const rawPath = normalizedFilePathMap.value.get(node.path) || node.path
  await fetchFileContent(rawPath)
}

// 文件流式更新相关状态
const streamingFileContent = ref<string>('') // 当前流式更新的文件内容
const currentFileOperation = ref<'read' | 'write' | 'edit' | null>(null)
const currentStreamingFileName = ref<string | null>(null) // 当前正在流式更新的文件名
const pastTextBuffer = ref<string>('') // edit 的 past_text 删除位置索引（字符串格式）
const replaceTextInsertIndex = ref<number>(-1) // replace_text 的插入位置（用于流式输出时累积）
const isDeletingText = ref(false) // 是否正在删除文本
const isAddingText = ref(false) // 是否正在添加文本
const streamingFileInitialized = ref(false) // 流式文件内容是否已初始化（从后端获取过原始内容）

const fetchFiles = async () => {
  // 先清空文件列表，让用户看到刷新效果
  files.value = [];
  
  // 短暂延迟，确保用户能看到刷新效果
  await new Promise(resolve => setTimeout(resolve, 100));
  
  try {
    const response = await axios.get(`/api/files?conversation_id=${props.conversationId}`);
    // 处理不同的响应格式
    if (Array.isArray(response.data)) {
      files.value = response.data;
    } else if (response.data && Array.isArray(response.data.files)) {
      files.value = response.data.files;
    } else if (response.data && Array.isArray(response.data.data)) {
      files.value = response.data.data;
    } else {
      files.value = [];
    }
  } catch (error) {
    files.value = [];
  }
};

const downloadFile = async (filename: string) => {
  try {
    const response = await axios.get(`/api/download/${filename}?conversation_id=${props.conversationId}`, {
      responseType: 'blob'
    });
    const url = window.URL.createObjectURL(new Blob([response.data]));
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', filename);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    window.URL.revokeObjectURL(url);
  } catch (error) {
    // 下载失败，静默处理
  }
};

const fileUrl = ref<string>('')
const fileBlob = ref<Blob | null>(null)

// 检查是否有未保存的更改
const checkUnsavedChanges = async (): Promise<boolean> => {
  if (isEditing.value && isContentModified.value) {
    const result = await showUnsavedChangesDialog()
    if (result === 'save') {
      await saveFile()
      return true
    } else if (result === 'cancel') {
      return false // 用户取消操作
    }
  }
  return true // 没有未保存的更改或用户选择直接退出
}

// 显示未保存更改对话框
const showUnsavedChangesDialog = (): Promise<'save' | 'discard' | 'cancel'> => {
  return new Promise((resolve) => {
    // 创建自定义对话框
    const dialog = document.createElement('div')
    dialog.style.cssText = `
      position: fixed;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      background-color: rgba(0, 0, 0, 0.5);
      display: flex;
      justify-content: center;
      align-items: center;
      z-index: 9999;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    `

    const dialogContent = document.createElement('div')
    dialogContent.style.cssText = `
      background: white;
      border-radius: 12px;
      padding: 24px;
      max-width: 400px;
      width: 90%;
      box-shadow: 0 10px 25px rgba(0, 0, 0, 0.2);
    `

    const title = document.createElement('h3')
    title.textContent = '未保存的更改'
    title.style.cssText = `
      margin: 0 0 16px 0;
      color: #1f2937;
      font-size: 18px;
      font-weight: 600;
    `

    const message = document.createElement('p')
    message.textContent = '您的更改尚未保存，确定要退出吗？'
    message.style.cssText = `
      margin: 0 0 24px 0;
      color: #6b7280;
      line-height: 1.5;
    `

    const buttonContainer = document.createElement('div')
    buttonContainer.style.cssText = `
      display: flex;
      gap: 12px;
      justify-content: flex-end;
    `

    const createButton = (text: string, primary = false) => {
      const button = document.createElement('button')
      button.textContent = text
      button.style.cssText = `
        padding: 8px 16px;
        border: 1px solid ${primary ? '#3b82f6' : '#d1d5db'};
        border-radius: 6px;
        background: ${primary ? '#3b82f6' : 'white'};
        color: ${primary ? 'white' : '#374151'};
        cursor: pointer;
        font-size: 14px;
        font-weight: 500;
        transition: all 0.2s;
      `
      button.onmouseover = () => {
        button.style.background = primary ? '#2563eb' : '#f9fafb'
        button.style.borderColor = primary ? '#2563eb' : '#9ca3af'
      }
      button.onmouseout = () => {
        button.style.background = primary ? '#3b82f6' : 'white'
        button.style.borderColor = primary ? '#3b82f6' : '#d1d5db'
      }
      return button
    }

    const saveButton = createButton('保存并退出', true)
    const discardButton = createButton('直接退出')
    const cancelButton = createButton('取消')

    saveButton.onclick = () => {
      document.body.removeChild(dialog)
      resolve('save')
    }

    discardButton.onclick = () => {
      document.body.removeChild(dialog)
      resolve('discard')
    }

    cancelButton.onclick = () => {
      document.body.removeChild(dialog)
      resolve('cancel')
    }

    buttonContainer.appendChild(cancelButton)
    buttonContainer.appendChild(discardButton)
    buttonContainer.appendChild(saveButton)

    dialogContent.appendChild(title)
    dialogContent.appendChild(message)
    dialogContent.appendChild(buttonContainer)
    dialog.appendChild(dialogContent)

    document.body.appendChild(dialog)
  })
}

// Modify fetchFileContent to fetch blob
const fetchFileContent = async (filename: string) => {
  // 如果当前在编辑模式，检查是否有未保存的更改并退出编辑模式
  if (isEditing.value) {
    const canProceed = await cancelEditing()
    if (!canProceed) return // 用户取消了操作
  }

  selectedFile.value = filename
  
  // 如果切换到正在流式更新的文件，使用 streamingFileContent
  if (currentStreamingFileName.value === filename && streamingFileInitialized.value) {
    fileContent.value = streamingFileContent.value
    previewError.value = ''
    
    // 为流式内容创建 blob URL
    if (isTextFile.value) {
      const blob = new Blob([streamingFileContent.value], { type: 'text/plain' })
      if (fileUrl.value) {
        URL.revokeObjectURL(fileUrl.value)
      }
      fileUrl.value = URL.createObjectURL(blob)
      fileBlob.value = blob
    }
    return
  }
  
  try {
    const response = await axios.get(`/api/file_content/${filename}?conversation_id=${props.conversationId}`, {
      responseType: 'blob'
    })
    const blob = response.data
    fileBlob.value = blob
    fileUrl.value = URL.createObjectURL(blob)
    previewError.value = ''
    
    if (isDocx.value) {
      const reader = new FileReader();
      reader.onload = async (e) => {
        const arrayBuffer = e.target?.result;
        if (arrayBuffer instanceof ArrayBuffer) {
          try {
            const result = await mammoth.convertToHtml({ arrayBuffer });
            fileContent.value = result.value;
          } catch (err) {
            previewError.value = '无法转换该 DOCX 文件';
          }
        } else {
          previewError.value = '无法读取 DOCX 文件';
        }
      };
      reader.onerror = () => {
        previewError.value = '读取 DOCX 文件失败';
      };
      reader.readAsArrayBuffer(blob);
    } else if (isTextFile.value) {
      blob.text().then(text => {
        fileContent.value = text
      }).catch(err => {
        previewError.value = '无法读取文件内容'
      })
    } else {
      fileContent.value = ''
    }
    
    nextTick(() => {
      // Handle iframe scaling if HTML
      if (isHtml.value) {
        const iframe = document.querySelector('.html-iframe') as HTMLIFrameElement
        if (iframe) {
          iframe.src = fileUrl.value
          iframe.onload = () => {
            const contentDocument = iframe.contentDocument
            if (!contentDocument) return
            const body = contentDocument.body
            if (!body) return
            
            // 自适应高度
            iframe.style.height = `${body.scrollHeight}px`;
            
            // 缩放如果内容过宽
            const contentWidth = body.scrollWidth;
            const container = iframe.parentElement;
            if (!container) return
            const containerWidth = container.clientWidth;
            const scale = Math.min(1, containerWidth / contentWidth);
            if (scale < 1) {
              iframe.style.transform = `scale(${scale})`;
              iframe.style.transformOrigin = 'top left';
              iframe.style.width = `${100 / scale}%`;
              iframe.style.height = `${body.scrollHeight / scale}px`;  // Fixed: / scale instead of * scale
            }
          }
        }
      }
    })
  } catch (error) {
    previewError.value = '无法显示该文件类型'
    fileUrl.value = ''
    fileContent.value = ''
  }
}

// Add computed properties for file types
const fileExtension = computed(() => {
  return selectedFile.value?.split('.').pop()?.toLowerCase() || ''
})

const isImage = computed(() => ['jpg', 'jpeg', 'png'].includes(fileExtension.value))
const isHtml = computed(() => selectedFile.value?.endsWith('.html'))
const isDocx = computed(() => ['doc', 'docx'].includes(fileExtension.value))
const isExcel = computed(() => ['xls', 'xlsx'].includes(fileExtension.value))
const isPdf = computed(() => fileExtension.value === 'pdf')
const isPpt = computed(() => ['ppt', 'pptx'].includes(fileExtension.value))
const isTextFile = computed(() => {
  // Files that can be opened with open() or markdown - assuming txt, md, etc.
  return ['txt', 'md', 'json', 'csv'].includes(fileExtension.value) || (!isImage.value && !isHtml.value && !isDocx.value && !isExcel.value && !isPdf.value && !isPpt.value)
})
const isEditableFile = computed(() => {
  // Files that can be edited as text
  return ['txt', 'md', 'json', 'csv', 'js', 'ts', 'py', 'html', 'css', 'xml', 'yml', 'yaml', 'ini', 'conf'].includes(fileExtension.value) || isTextFile.value
})

const isMarkdownFile = computed(() => fileExtension.value === 'md' || fileExtension.value === 'txt')

// 处理转义字符的函数（将 \n 等转义字符转换为实际字符）
function unescapeString(str: string): string {
  if (!str) return ''
  // 处理常见的转义字符
  return str
    .replace(/\\n/g, '\n')      // \n -> 换行
    .replace(/\\r/g, '\r')      // \r -> 回车
    .replace(/\\t/g, '\t')      // \t -> 制表符
    .replace(/\\"/g, '"')       // \" -> 双引号
    .replace(/\\'/g, "'")       // \' -> 单引号
    .replace(/\\\\/g, '\\')     // \\ -> 反斜杠
}

// 处理文件内容用于渲染（类似 ChatWindow.vue 的方式）
const processedFileContent = computed(() => {
  if (!isTextFile.value) {
    return ''
  }
  // 先处理转义字符，将 \n 等转换为实际字符
  return unescapeString(fileContent.value || '')
})

// Add cleanup for URL
watch(selectedFile, () => {
  if (fileUrl.value) {
    URL.revokeObjectURL(fileUrl.value)
  }
  fileUrl.value = ''
  fileContent.value = ''
})

// parseArguments
const parseArguments = (argsString: string): Record<string, any> => {
  try {
    return JSON.parse(argsString)
  } catch (e) {
    return {}
  }
}

// isExpanded
const isExpanded = (id: string): boolean => expanded.value.get(id) || false

  // toggleExpand with animation
  const toggleExpand = (id: string, isManual: boolean = false) => {
    const index = groupedToolMessages.value.findIndex(g => g.tool_call_id === id)
    if (index === -1) return
    const contentEl = contentRefs.value[index] as HTMLElement | null
    if (!contentEl) return
    const toExpand = !isExpanded(id)
    if (toExpand) {
      expanded.value.set(id, true)
      isManuallyCollapsed.value.set(id, false)
      // Expand
      contentEl.style.maxHeight = `${contentEl.clientHeight}px`
      nextTick(() => {
        contentEl.style.maxHeight = `${contentEl.scrollHeight}px`
        setTimeout(() => {
          contentEl.style.maxHeight = ''
          checkOverflow()
          scrollToBottom()
        }, 1000)
      })
    } else {
      expanded.value.set(id, false)
      isManuallyCollapsed.value.set(id, isManual)
      // Collapse
      contentEl.style.maxHeight = `${contentEl.scrollHeight}px`
      const _ = contentEl.offsetHeight // Force reflow to ensure transition
      nextTick(() => {
        contentEl.style.maxHeight = '250px'
      setTimeout(() => {
        expanded.value.set(id, false)
        contentEl.style.maxHeight = ''
        checkOverflow()
        scrollToBottom()
      }, 1000)
      })
    }
}

// checkOverflow
const checkOverflow = () => {
  nextTick(() => {
    needsExpand.value = contentRefs.value.map(ref => {
      if (!ref) return false
      const htmlRef = ref as HTMLElement
      return htmlRef.scrollHeight > htmlRef.clientHeight
    })
    attachCopyListeners()
  })
}

// 防抖版 checkOverflow：流式时频繁触发，避免每 chunk 都做 DOM 查询和事件绑定
let checkOverflowTimer: ReturnType<typeof setTimeout> | null = null
let pendingGroupsRef: { groups: typeof groupedToolMessages.value } | null = null
const debouncedCheckOverflow = (groups?: typeof groupedToolMessages.value) => {
  if (groups) pendingGroupsRef = { groups }
  if (checkOverflowTimer) clearTimeout(checkOverflowTimer)
  checkOverflowTimer = setTimeout(() => {
    checkOverflowTimer = null
    checkOverflow()
    const pending = pendingGroupsRef
    pendingGroupsRef = null
    if (pending && pending.groups.length > 0) {
      const lastIndex = pending.groups.length - 1
      const lastId = pending.groups[lastIndex].tool_call_id
      nextTick(() => {
        if (needsExpand.value[lastIndex] && !expanded.value.get(lastId) && !isManuallyCollapsed.value.get(lastId)) {
          toggleExpand(lastId, false)
        }
      })
    }
  }, 80)
}

// watch
watch(groupedToolMessages, (newGroups, oldGroups) => {
  if (newGroups.length > oldGroups.length) {
    const newId = newGroups[newGroups.length - 1].tool_call_id
    toggleExpand(newId)  // This will expand since initially false
    if (newGroups.length >= 2) {
      const prevId = newGroups[newGroups.length - 2].tool_call_id
      if (isExpanded(prevId)) {
        toggleExpand(prevId, false)  // Force collapse the previous one
      }
    }
  }
  newGroups.forEach(group => {
    const id = group.tool_call_id
    if (!expanded.value.has(id)) {
      expanded.value.set(id, false)
      isManuallyCollapsed.value.set(id, false)
    }
  })
  nextTick(() => {
    debouncedCheckOverflow(newGroups)
  })
}, { deep: true })

watch(() => [props.scrollToId, props.toggleTrigger], () => {
  if (props.scrollToId) {
    const index = groupedToolMessages.value.findIndex(g => g.tool_call_id === props.scrollToId)
    if (index !== -1) {
      const ref = toolRefs.value[index]
      if (ref) {
        ref.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
      }
      toggleExpand(props.scrollToId, false)
    }
  }
})

// 监听工具消息变化，自动滚动到底部
watch(() => props.toolMessages, () => {
  nextTick(() => {
    scrollToBottom()
  })
}, { deep: true, immediate: true })

// 监听页面关闭或刷新事件
const handleBeforeUnload = (event: BeforeUnloadEvent) => {
  if (isEditing.value && isContentModified.value) {
    event.preventDefault()
    event.returnValue = '您的更改尚未保存，确定要离开吗？'
    return event.returnValue
  }
}

onMounted(() => {
  checkOverflow()
  attachCopyListeners()

  // 添加页面关闭/刷新的监听
  window.addEventListener('beforeunload', handleBeforeUnload)
})

// 清理事件监听器
onUnmounted(() => {
  window.removeEventListener('beforeunload', handleBeforeUnload)
})

// 添加滚动到底部的方法
const scrollToBottom = () => {
  if (isAutoScroll.value && toolMessagesContainer.value) {
    nextTick(() => {
      if (toolMessagesContainer.value) {
        toolMessagesContainer.value.scrollTop = toolMessagesContainer.value.scrollHeight
      }
    })
  }
}

// 添加处理用户手动滚动的方法
const handleScroll = () => {
  if (toolMessagesContainer.value) {
    const { scrollTop, scrollHeight, clientHeight } = toolMessagesContainer.value
    // 如果用户滚动到接近底部，恢复自动滚动
    if (scrollHeight - scrollTop - clientHeight < 50) {
      isAutoScroll.value = true
    } else {
      // 用户手动滚动到其他位置，停止自动滚动
      isAutoScroll.value = false
    }
  }
}

// 添加attachCopyListeners函数
const attachCopyListeners = () => {
  nextTick(() => {
    const buttons = document.querySelectorAll('.code-copy-btn')
    buttons.forEach(btn => {
      btn.removeEventListener('click', handleCodeCopy)
      btn.addEventListener('click', handleCodeCopy)
    })
  })
}

const handleCodeCopy = (e) => {
  const btn = e.target
  const wrapper = btn.closest('.code-wrapper')
  if (!wrapper) return
  const codeElement = wrapper.querySelector('pre code')
  if (!codeElement) return
  const code = codeElement.textContent || ''
  if (navigator.clipboard) {
    navigator.clipboard.writeText(code).then(() => {
      const originalSrc = btn.src
      btn.src = SuccessIcon
      setTimeout(() => {
        btn.src = originalSrc
      }, 2000)
    }).catch(() => {
      // 复制失败，静默处理
    });
  } else {
    const textarea = document.createElement('textarea');
    textarea.value = code;
    textarea.style.position = 'fixed';
    document.body.appendChild(textarea);
    textarea.focus();
    textarea.select();
    try {
      const successful = document.execCommand('copy');
      if (successful) {
        const originalSrc = btn.src
        btn.src = SuccessIcon
        setTimeout(() => {
          btn.src = originalSrc
        }, 2000)
      }
    } catch (err) {
      // 复制失败，静默处理
    }
    document.body.removeChild(textarea);
  }
}

// Tab 切换状态
const activeTab = ref<'tools' | 'files'>('tools')

// 文件列表展开/收缩状态（默认展开）
const isFileListExpanded = ref(true)

// 切换文件列表展开/收缩
const toggleFileList = () => {
  isFileListExpanded.value = !isFileListExpanded.value
}

// showFileLibrary 用于控制全屏文件库弹窗的显示（编辑模式和预览模式都会使用）
const showFileLibrary = ref(false)
const isEditing = ref(false)
const editedContent = ref('')

// 关闭编辑弹窗
const closeEditPanel = async () => {
  // 如果正在编辑，检查未保存更改并退出编辑模式
  if (isEditing.value) {
    const canProceed = await cancelEditing()
    if (!canProceed) return // 用户取消了操作
  }
  showFileLibrary.value = false
}

// 添加watch for conversationId
watch(() => props.conversationId, (newId, oldId) => {
  // 切换对话时，清空预览文件
  if (oldId && oldId !== newId) {
    // 清理文件 URL
    if (fileUrl.value) {
      URL.revokeObjectURL(fileUrl.value)
    }
    selectedFile.value = null
    fileUrl.value = ''
    fileContent.value = ''
    previewError.value = ''
    fileBlob.value = null
    expandedFolders.value = new Set()
    // 重置流式更新状态
    streamingFileContent.value = ''
    currentFileOperation.value = null
    currentStreamingFileName.value = null
    pastTextBuffer.value = ''
    replaceTextInsertIndex.value = -1
    isDeletingText.value = false
    isAddingText.value = false
    streamingFileInitialized.value = false
  }
  
  // 如果当前在文件库 tab，刷新文件列表
  if (activeTab.value === 'files') {
    fetchFiles();
  }
})

// 监听 activeTab 变化，切换到文件库时自动获取文件列表
watch(activeTab, (newTab) => {
  if (newTab === 'files') {
    fetchFiles()
  } else if (newTab === 'tools') {
    // 切换回工具库时，重新检查溢出状态以显示展开按钮
    nextTick(() => {
      checkOverflow()
    })
  }
})

// 直接获取文件内容用于流式更新（不影响 selectedFile 状态）
const fetchFileContentForStreaming = async (filename: string): Promise<string> => {
  try {
    const response = await axios.get(`/api/file_content/${filename}?conversation_id=${props.conversationId}`, {
      responseType: 'blob'
    })
    const blob = response.data
    const text = await blob.text()
    return text
  } catch (error) {
    return ''
  }
}

// 刷新当前正在流式更新的文件（流式输出结束后调用）
const refreshCurrentFileAfterStreaming = async () => {
  if (!currentStreamingFileName.value) {
    return
  }
  
  const fileName = currentStreamingFileName.value
  
  // 延迟2秒后再刷新
  await new Promise(resolve => setTimeout(resolve, 2000))
  
  // 检查文件是否仍然需要刷新（防止在延迟期间切换了文件）
  if (currentStreamingFileName.value !== fileName) {
    return
  }
  
  try {
    // 如果当前预览的文件就是正在流式更新的文件，重新获取内容
    if (selectedFile.value === fileName) {
      await fetchFileContent(fileName)
      streamingFileContent.value = fileContent.value
    }
    
    // 重置流式更新状态
    currentStreamingFileName.value = null
    currentFileOperation.value = null
    streamingFileInitialized.value = false
  } catch (error) {
    // 刷新失败，静默处理
  }
}

// 处理文件流式更新
const handleFileStreaming = async (message: AgentMessage) => {
  if (!message) {
    return
  }
  if (message.role !== 'file') {
    return
  }
  
  const fileType = message.type as 'read' | 'write' | 'edit'
  const jsonTable = message.table || {}
  
  // 判断当前预览的文件是否是正在流式更新的文件
  const isPreviewingStreamingFile = () => {
    return selectedFile.value === currentStreamingFileName.value && activeTab.value === 'files'
  }
  
  // 检测流式输出结束标志
  if (jsonTable.file_stop === 'true' || jsonTable.file_stop === true) {
    // 流式更新结束
    // 只有当用户不在预览正在更新的文件时，才清空队列
    // 如果用户正在预览，让队列中的消息正常处理完毕
    if (!isPreviewingStreamingFile()) {
      fileMessageQueue.value = []
    }
    // 重置 replace_text 插入位置
    replaceTextInsertIndex.value = -1
    pastTextBuffer.value = ''
    streamingFileInitialized.value = false
    await refreshCurrentFileAfterStreaming()
    return
  }
  
  // 不再自动切换 tab，只在后台更新文件列表
  if (files.value.length === 0) {
    await fetchFiles()
  }
  
  // 更新 UI（仅当用户正在预览该文件时）
  const updateUIIfPreviewing = () => {
    if (isPreviewingStreamingFile()) {
      fileContent.value = streamingFileContent.value
      
      // 更新预览 blob URL（对于文本文件）
      if (isTextFile.value) {
        const blob = new Blob([streamingFileContent.value], { type: 'text/plain' })
        if (fileUrl.value) {
          URL.revokeObjectURL(fileUrl.value)
        }
        fileUrl.value = URL.createObjectURL(blob)
        fileBlob.value = blob
      }
    }
  }
  
  if (fileType === 'read') {
    // read: 第一次识别到 file_name 时定位到预览文件
    if (jsonTable.file_name) {
      const fileName = jsonTable.file_name
      
      // 确保文件在列表中
      if (!files.value.includes(fileName)) {
        files.value.push(fileName)
      }
      
      // 第一次识别到 file_name，定位到预览文件
      activeTab.value = 'files'
      selectedFile.value = fileName
      await nextTick()
      await fetchFileContent(fileName)
      
      // 重置流式状态（read 不需要流式更新）
      currentFileOperation.value = null
      currentStreamingFileName.value = null
      streamingFileContent.value = ''
      streamingFileInitialized.value = false
    }
  } else if (fileType === 'write') {
    // write: 流式追加 content
    const fileName = jsonTable.file_name
    const content = jsonTable.content
    
    if (!fileName) {
      return
    }
    
    // 检查是否是新的流式文件
    const isNewFile = !files.value.includes(fileName)
    const isFirstTimeForThisFile = currentStreamingFileName.value !== fileName
    
    // 如果是新文件或切换到另一个文件，需要初始化并定位
    if (isNewFile || isFirstTimeForThisFile) {
      currentStreamingFileName.value = fileName
      currentFileOperation.value = 'write'
      streamingFileInitialized.value = false
      
      // 第一次识别到 file_name，定位到预览文件
      if (isNewFile) {
        files.value.push(fileName)
      }
      activeTab.value = 'files'
      selectedFile.value = fileName
      await nextTick()
      
      if (isNewFile) {
        // 新文件：创建空预览
        streamingFileContent.value = ''
        fileContent.value = ''
        previewError.value = ''
        
        // 创建空的 blob URL
        if (fileUrl.value) {
          URL.revokeObjectURL(fileUrl.value)
        }
        const emptyBlob = new Blob([''], { type: 'text/plain' })
        fileUrl.value = URL.createObjectURL(emptyBlob)
        fileBlob.value = emptyBlob
        streamingFileInitialized.value = true
      } else {
        // 已存在的文件：获取内容
        try {
          await fetchFileContent(fileName)
          streamingFileContent.value = fileContent.value
          streamingFileInitialized.value = true
        } catch (e) {
          streamingFileContent.value = ''
          fileContent.value = ''
          streamingFileInitialized.value = true
        }
      }
    }
    
    // 流式追加 content
    if (content !== undefined && content !== null && content !== '') {
      // 确保 streamingFileContent 已初始化
      if (!streamingFileInitialized.value) {
        try {
          const existingContent = await fetchFileContentForStreaming(fileName)
          streamingFileContent.value = existingContent
          streamingFileInitialized.value = true
        } catch (e) {
          streamingFileContent.value = ''
          streamingFileInitialized.value = true
        }
      }
      
      // 追加内容
      streamingFileContent.value += content
      
      // 如果用户正在预览这个文件，更新 UI
      updateUIIfPreviewing()
      
      // 等待 DOM 更新后滚动（仅当用户正在预览时）
      if (isPreviewingStreamingFile()) {
        await nextTick()
        nextTick(() => {
          const previewContent = document.querySelector('.preview-content') as HTMLElement
          if (previewContent) {
            previewContent.scrollTop = previewContent.scrollHeight
          }
        })
      }
    }
  } else if (fileType === 'edit') {
    // edit: 处理 past_text 和 replace_text
    const fileName = jsonTable.file_name
    
    // 如果有 file_name，初始化流式状态并定位
    if (fileName) {
      // 确保文件在列表中
      if (!files.value.includes(fileName)) {
        files.value.push(fileName)
      }
      
      // 检查是否切换到新文件
      const isFirstTimeForThisFile = currentStreamingFileName.value !== fileName
      
      if (isFirstTimeForThisFile) {
        currentStreamingFileName.value = fileName
        currentFileOperation.value = 'edit'
        streamingFileInitialized.value = false
        
        // 第一次识别到 file_name，定位到预览文件
        activeTab.value = 'files'
        selectedFile.value = fileName
        await nextTick()
        
        // 获取文件内容 - 使用 fetchFileContentForStreaming 确保同步获取文本内容
        try {
          let content = await fetchFileContentForStreaming(fileName)
          // 统一换行符格式（将 \r\n 和 \r 都转换为 \n）
          content = content.replace(/\r\n/g, '\n').replace(/\r/g, '\n')
          streamingFileContent.value = content
          fileContent.value = content
          streamingFileInitialized.value = true
          
          // 更新 UI 显示
          if (isTextFile.value) {
            const blob = new Blob([content], { type: 'text/plain' })
            if (fileUrl.value) {
              URL.revokeObjectURL(fileUrl.value)
            }
            fileUrl.value = URL.createObjectURL(blob)
            fileBlob.value = blob
          }
        } catch (e) {
          streamingFileContent.value = ''
          fileContent.value = ''
          streamingFileInitialized.value = true
        }
      }
    }
    
    // 处理 past_text - 检测到就立即处理
    if (jsonTable.past_text !== undefined && jsonTable.past_text !== null && currentStreamingFileName.value) {
      // 重置 replace_text 的插入位置（开始新的替换操作）
      replaceTextInsertIndex.value = -1
      
      // 确保文件内容已加载
      if (!streamingFileInitialized.value && currentStreamingFileName.value) {
        try {
          let content = await fetchFileContentForStreaming(currentStreamingFileName.value)
          // 统一换行符格式
          content = content.replace(/\r\n/g, '\n').replace(/\r/g, '\n')
          streamingFileContent.value = content
          streamingFileInitialized.value = true
          updateUIIfPreviewing()
        } catch (e) {
          streamingFileContent.value = ''
          streamingFileInitialized.value = true
        }
        await nextTick()
      }
      
      // 处理转义字符（将 \n 等转换为实际字符）
      let cleanedPastText = unescapeString(jsonTable.past_text)
      
      // 统一换行符格式（将 \r\n 和 \r 都转换为 \n）
      const normalizedFileContent = streamingFileContent.value.replace(/\r\n/g, '\n').replace(/\r/g, '\n')
      const normalizedPastText = cleanedPastText.replace(/\r\n/g, '\n').replace(/\r/g, '\n')
      
      // 在标准化的内容中查找匹配位置
      const matchIndex = normalizedFileContent.indexOf(normalizedPastText)
      
      if (matchIndex !== -1) {
        // 保存删除位置，用于后续 replace_text 的插入
        pastTextBuffer.value = matchIndex.toString()
        // 执行删除动画（仅当用户正在预览时有动画效果）
        // 使用标准化后的 past_text，因为 streamingFileContent 也已经标准化了
        const showAnim = isPreviewingStreamingFile()
        await deleteTextWithAnimation(normalizedPastText, matchIndex, showAnim)
      } else {
        // 如果找不到匹配，清空缓冲区
        pastTextBuffer.value = ''
      }
    }
    
    // 处理 replace_text - 从 past_text 的位置流式输出
    if (jsonTable.replace_text !== undefined && jsonTable.replace_text !== null && currentStreamingFileName.value) {
      // 等待删除动画完成（如果正在删除）
      while (isDeletingText.value) {
        await new Promise(resolve => setTimeout(resolve, 50))
      }
      
      // 确保文件内容已加载
      if (!streamingFileInitialized.value && currentStreamingFileName.value) {
        try {
          let content = await fetchFileContentForStreaming(currentStreamingFileName.value)
          // 统一换行符格式
          content = content.replace(/\r\n/g, '\n').replace(/\r/g, '\n')
          streamingFileContent.value = content
          streamingFileInitialized.value = true
          updateUIIfPreviewing()
        } catch (e) {
          streamingFileContent.value = ''
          streamingFileInitialized.value = true
        }
        await nextTick()
      }
      
      // 如果是第一次收到 replace_text，从 past_text 的删除位置开始
      let insertIndex = replaceTextInsertIndex.value
      if (insertIndex < 0 && pastTextBuffer.value) {
        insertIndex = parseInt(pastTextBuffer.value)
        replaceTextInsertIndex.value = insertIndex
      }
      
      // 执行添加动画（仅当用户正在预览时有动画效果）
      if (jsonTable.replace_text && insertIndex >= 0) {
        const showAnim = isPreviewingStreamingFile()
        await addTextWithAnimation(jsonTable.replace_text, insertIndex, showAnim)
        // 更新插入位置，用于后续流式输出
        replaceTextInsertIndex.value += jsonTable.replace_text.length
      }
    }
  }
}

// 删除文本动画（从第一个字到最后一个字一个字一个字删除）
// showAnimation: 是否显示动画效果（如果用户不在预览该文件，直接删除不需要动画）
const deleteTextWithAnimation = async (text: string, startIndex?: number, showAnimation: boolean = true): Promise<void> => {
  if (!text) return
  
  // 必须提供 startIndex，否则无法确定删除位置
  if (startIndex === undefined || startIndex === -1) {
    return
  }
  
  const matchIndex = startIndex
  const textLength = text.length
  
  // 验证匹配位置是否正确
  const actualText = streamingFileContent.value.substring(matchIndex, matchIndex + textLength)
  if (actualText !== text) {
    return
  }
  
  isDeletingText.value = true
  
  // 保存删除位置前后的内容（这些内容保持不变）
  const beforeText = streamingFileContent.value.substring(0, matchIndex)
  const afterText = streamingFileContent.value.substring(matchIndex + textLength)
  
  // 如果不需要动画，直接删除
  if (!showAnimation) {
    streamingFileContent.value = beforeText + afterText
    isDeletingText.value = false
    return
  }
  
  // 从第一个字到最后一个字删除（一个字一个字删除，创造动画效果）
  // 从开头开始删除：每次删除一个字符，从 matchIndex 位置开始
  for (let i = 0; i <= textLength; i++) {
    // 保留之前的内容（不变） + 从第 i 个字符开始的剩余文本（逐渐减少） + 之后的内容（不变）
    const remainingText = text.substring(i) // 从第 i 个字符开始保留，逐渐减少
    streamingFileContent.value = beforeText + remainingText + afterText
    fileContent.value = streamingFileContent.value
    
    // 更新预览 blob
    if (isTextFile.value) {
      const blob = new Blob([streamingFileContent.value], { type: 'text/plain' })
      if (fileUrl.value) {
        URL.revokeObjectURL(fileUrl.value)
      }
      fileUrl.value = URL.createObjectURL(blob)
      fileBlob.value = blob
    }
    
    // 等待 Vue 更新 DOM
    await nextTick()
    
    // 每删除一个字符等待一小段时间，创造打字效果
    // 对于长文本，适当加快速度；对于短文本，保持较慢速度以便观察
    const delay = textLength > 100 ? 10 : 30
    await new Promise(resolve => setTimeout(resolve, delay))
  }
  
  isDeletingText.value = false
}

// 添加文本动画（流式输出，从指定位置插入）
// showAnimation: 是否显示动画效果（如果用户不在预览该文件，直接添加不需要动画）
const addTextWithAnimation = async (text: string, insertIndex?: number, showAnimation: boolean = true): Promise<void> => {
  if (!text) return
  
  isAddingText.value = true
  const textLength = text.length
  
  // 如果提供了插入位置，从该位置插入；否则追加到末尾
  const startIndex = insertIndex !== undefined && insertIndex >= 0 ? insertIndex : streamingFileContent.value.length
  
  // 如果不需要动画，直接插入
  if (!showAnimation) {
    const beforeText = streamingFileContent.value.substring(0, startIndex)
    const afterText = streamingFileContent.value.substring(startIndex)
    streamingFileContent.value = beforeText + text + afterText
    isAddingText.value = false
    return
  }
  
  for (let i = 0; i < textLength; i++) {
    // 在指定位置插入字符
    const beforeText = streamingFileContent.value.substring(0, startIndex + i)
    const afterText = streamingFileContent.value.substring(startIndex + i)
    streamingFileContent.value = beforeText + text[i] + afterText
    fileContent.value = streamingFileContent.value
    
    // 更新预览 blob
    if (isTextFile.value) {
      const blob = new Blob([streamingFileContent.value], { type: 'text/plain' })
      if (fileUrl.value) {
        URL.revokeObjectURL(fileUrl.value)
      }
      fileUrl.value = URL.createObjectURL(blob)
      fileBlob.value = blob
    }
    
    // 等待 Vue 更新 DOM
    await nextTick()
    
    // 每添加一个字符等待一小段时间，创造流式输出效果
    await new Promise(resolve => setTimeout(resolve, 20))
  }
  
  isAddingText.value = false
  
  // 滚动到插入位置附近
  nextTick(() => {
    const previewContent = document.querySelector('.preview-content') as HTMLElement
    if (previewContent) {
      // 计算插入位置对应的滚动位置
      const scrollRatio = startIndex / Math.max(1, streamingFileContent.value.length)
      previewContent.scrollTop = scrollRatio * (previewContent.scrollHeight - previewContent.clientHeight)
    }
  })
}

// 文件消息队列相关（模仿 Chat.vue 的队列机制）
const fileMessageQueue = ref<AgentMessage[]>([])
let isProcessingFileQueue = false

// 队列处理函数（同步处理，避免 Vue 响应不过来导致丢数据）
async function processFileMessageQueue() {
  if (isProcessingFileQueue || fileMessageQueue.value.length === 0) return

  isProcessingFileQueue = true

  while (fileMessageQueue.value.length > 0) {
    const message = fileMessageQueue.value.shift()
    if (!message) continue

    // 处理文件流式更新
    await handleFileStreaming(message)

    // 每个消息处理后等待一帧，让Vue有时间更新UI
    await new Promise(resolve => setTimeout(resolve, 0))
  }

  isProcessingFileQueue = false
}

// 监听 fileMessages 数组长度变化，将新消息添加到队列
watch(() => props.fileMessages.length, (newLength, oldLength) => {
  const oldLengthValue = oldLength || 0
  
  if (newLength > oldLengthValue) {
    // 有新消息，添加到队列
    for (let i = oldLengthValue; i < newLength; i++) {
      const message = props.fileMessages[i]
      if (message && message.role === 'file') {
        fileMessageQueue.value.push(message)
      }
    }
    
    // 触发队列处理
    processFileMessageQueue()
  }
}, { immediate: true })

// 重置队列（当对话切换时）
watch(() => props.conversationId, () => {
  fileMessageQueue.value = []
  isProcessingFileQueue = false
  streamingFileInitialized.value = false
})

const exportFormat = ref('pdf')

// 在 script 中添加新 refs 和函数
const showExportOptions = ref(false)
const exporting = ref(false)
const exportSuccess = ref(false)
const exportError = ref('')

// 编辑相关状态
const saving = ref(false)
const saveSuccess = ref(false)
const saveError = ref('')

// 编辑模式状态 (仅对.md文件)
const editMode = ref<'markdown' | 'source'>('markdown')
const markdownEditor = ref<any>(null) // Toast UI Editor实例

// 文件修改状态跟踪
const isContentModified = ref(false)
const originalContent = ref('')

// 标记是否正在初始化编辑器，避免初始化时的change事件触发内容修改检测
let isInitializingEditor = false

// 编辑时的滚动位置管理
const previewScrollRatio = ref(0) // 预览区域的滚动比例 (0-1)
const editingScrollRatio = ref(0) // 编辑区域的滚动比例 (0-1)
const isEditModeScrollSet = ref(false)

// Markdown编辑器的键盘事件处理函数
const handleMarkdownKeyDown = (event: Event) => {
  const keyboardEvent = event as KeyboardEvent
  if ((keyboardEvent.ctrlKey || keyboardEvent.metaKey) && keyboardEvent.key === 's') {
    event.preventDefault()
    event.stopPropagation()
    saveFile()
  }
}

// 监听编辑状态变化，设置滚动位置
watch(isEditing, (newVal) => {
  if (newVal) {
    // 进入编辑模式，等待DOM更新后设置滚动位置
    nextTick(() => {
      nextTick(() => {
        setEditingScrollPosition()
      })
    })
  }
})

// 设置编辑区域的滚动位置
const setEditingScrollPosition = () => {
  const textarea = document.querySelector('.edit-textarea') as HTMLTextAreaElement
  if (textarea && previewScrollRatio.value > 0) {
    const scrollableHeight = textarea.scrollHeight - textarea.clientHeight
    if (scrollableHeight > 0) {
      const targetScrollTop = previewScrollRatio.value * scrollableHeight
      textarea.scrollTop = Math.max(0, targetScrollTop)
    }
    textarea.focus()
    textarea.setSelectionRange(textarea.value.length, textarea.value.length)
    isEditModeScrollSet.value = true
  }
}

// 监听编辑内容变化，重新设置滚动位置
watch(() => editedContent.value, () => {
  if (isEditing.value) {
    // 如果正在初始化编辑器，不更新修改状态（避免误触发）
    if (!isInitializingEditor) {
      // 检查内容是否被修改
      isContentModified.value = editedContent.value !== originalContent.value
    }

    if (!isEditModeScrollSet.value) {
      nextTick(() => {
        setEditingScrollPosition()
      })
    }
  }
})

const toggleExportOptions = () => {
  showExportOptions.value = !showExportOptions.value
}

const exportWithFormat = async (format) => {
  showExportOptions.value = false
  if (!selectedFile.value) {
    exportError.value = '请选择文件'
    setTimeout(() => { exportError.value = '' }, 3000)
    return
  }
  exporting.value = true
  exportSuccess.value = false
  exportError.value = ''
  exportFormat.value = format

  try {
    const response = await axios.get(`/api/export/${selectedFile.value}?conversation_id=${props.conversationId}&format=${format}`, { responseType: 'blob' })
    const url = window.URL.createObjectURL(new Blob([response.data]))
    const link = document.createElement('a')
    link.href = url
    const ext = format
    let baseName = selectedFile.value
    if (baseName.includes('.')) {
      baseName = baseName.replace(/\.[^/.]+$/, "")
    }
    const downloadName = `${baseName}.${ext}`
    link.setAttribute('download', downloadName)
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    window.URL.revokeObjectURL(url)

    exporting.value = false
    exportSuccess.value = true
    setTimeout(() => { exportSuccess.value = false }, 3000) // 3秒后隐藏成功提示
  } catch (error) {
    exporting.value = false
    exportError.value = '导出失败，请重试'
    setTimeout(() => { exportError.value = '' }, 3000)
  }
}

// 编辑相关函数
const startEditing = () => {
  if (!selectedFile.value) return

  // 保存预览区域的滚动比例
  const previewContent = document.querySelector('.preview-content') as HTMLElement
  if (previewContent) {
    const scrollableHeight = previewContent.scrollHeight - previewContent.clientHeight
    if (scrollableHeight > 0) {
      previewScrollRatio.value = previewContent.scrollTop / scrollableHeight
    } else {
      previewScrollRatio.value = 0
    }
  }

  // 显示全屏编辑弹窗
  showFileLibrary.value = true
  isEditing.value = true
  editedContent.value = fileContent.value
  originalContent.value = fileContent.value // 保存原始内容
  isContentModified.value = false // 重置修改状态

  // 根据文件类型设置默认编辑模式
  if (isMarkdownFile.value) {
    editMode.value = 'markdown'
    nextTick(() => {
      initMarkdownEditor()
    })
  } else {
    editMode.value = 'source'
  }

  saveSuccess.value = false
  saveError.value = ''
  isEditModeScrollSet.value = false
}

const cancelEditing = async (skipCheck = false): Promise<boolean> => {
  // 检查是否有未保存的更改（如果skipCheck为true，则跳过检查）
  if (!skipCheck && isContentModified.value) {
    const result = await showUnsavedChangesDialog()
    if (result === 'save') {
      await saveFile()
    } else if (result === 'cancel') {
      return false // 用户取消退出
    }
  }

  // 保存编辑区域的滚动比例
  const textarea = document.querySelector('.edit-textarea') as HTMLTextAreaElement
  if (textarea) {
    const scrollableHeight = textarea.scrollHeight - textarea.clientHeight
    if (scrollableHeight > 0) {
      editingScrollRatio.value = textarea.scrollTop / scrollableHeight
    } else {
      editingScrollRatio.value = 0
    }
  }

  isEditing.value = false
  editedContent.value = ''
  saveSuccess.value = false
  saveError.value = ''
  isContentModified.value = false // 重置修改状态
  // 不关闭全屏弹窗，保持文件库页面打开，只退出编辑模式

  // 销毁markdown编辑器
  if (markdownEditor.value) {
    const editorElement = document.querySelector('#markdown-editor')
    if (editorElement) {
      // 移除键盘事件监听
      editorElement.removeEventListener('keydown', handleMarkdownKeyDown, true)
      // 移除编辑器内部输入元素的事件监听
      const editorInputs = editorElement.querySelectorAll('textarea, .ProseMirror')
      editorInputs.forEach((input) => {
        input.removeEventListener('keydown', handleMarkdownKeyDown, true)
      })
    }
    markdownEditor.value.destroy()
    markdownEditor.value = null
  }

  // 恢复预览区域的滚动位置
  nextTick(() => {
    const previewContent = document.querySelector('.preview-content') as HTMLElement
    if (previewContent) {
      const scrollableHeight = previewContent.scrollHeight - previewContent.clientHeight
      if (scrollableHeight > 0) {
        const targetScrollTop = editingScrollRatio.value * scrollableHeight
        previewContent.scrollTop = Math.max(0, targetScrollTop)
      }
    }
  })

  return true // 成功退出编辑模式
}

// 初始化Markdown编辑器
const initMarkdownEditor = () => {
  const editorElement = document.querySelector('#markdown-editor')
  if (!editorElement || markdownEditor.value) return

  // 保存初始化前的内容，用于比较
  const contentBeforeInit = editedContent.value
  isInitializingEditor = true

  markdownEditor.value = new Editor({
    el: editorElement,
    height: '600px',
    initialEditType: 'markdown',
    previewStyle: 'vertical', // 左右分栏布局，类似Typora
    initialValue: editedContent.value,
    plugins: [codeSyntaxHighlight],
    toolbarItems: [
      ['heading', 'bold', 'italic', 'strike'],
      ['hr', 'quote'],
      ['ul', 'ol', 'task', 'indent', 'outdent'],
      ['table', 'image', 'link'],
      ['code', 'codeblock'],
      ['scrollSync']
    ],
    events: {
      change: () => {
        if (markdownEditor.value) {
          const newContent = markdownEditor.value.getMarkdown()
          // 如果正在初始化，且内容与初始化前相同，则不触发修改检测
          if (isInitializingEditor && newContent === contentBeforeInit) {
            // 静默更新内容，但不触发修改状态
            editedContent.value = newContent
            return
          }
          // 只有在内容真正变化时才更新
          if (newContent !== editedContent.value) {
            editedContent.value = newContent
          }
        }
      },
      keydown: (editorType: string, event: KeyboardEvent) => {
        // 拦截Ctrl+S快捷键
        if ((event.ctrlKey || event.metaKey) && event.key === 's') {
          event.preventDefault()
          event.stopPropagation()
          saveFile()
          return false
        }
      }
    }
  })

  // 初始化完成后，延迟重置初始化标志
  nextTick(() => {
    setTimeout(() => {
      isInitializingEditor = false
    }, 500)
  })

  // 禁用编辑器的默认快捷键
  if (markdownEditor.value) {
    // 延迟执行，确保编辑器完全初始化
    nextTick(() => {
      // 查找编辑器内部的输入元素并添加事件监听
      const editorInputs = editorElement.querySelectorAll('textarea, .ProseMirror')
      editorInputs.forEach((input) => {
        input.addEventListener('keydown', handleMarkdownKeyDown, true)
      })
    })
  }

  // 为编辑器容器添加键盘事件监听（捕获阶段，确保在我们的事件处理前执行）
  if (editorElement) {
    editorElement.addEventListener('keydown', handleMarkdownKeyDown, true)
  }
}

// 切换编辑模式
const switchEditMode = (mode: 'markdown' | 'source') => {
  if (!isMarkdownFile.value) return

  // 保存切换前的编辑内容和修改状态
  const contentBeforeSwitch = editedContent.value
  const wasModifiedBeforeSwitch = isContentModified.value

  // 如果从markdown模式切换到源码模式，先销毁编辑器
  if (editMode.value === 'markdown' && mode === 'source' && markdownEditor.value) {
    const editorElement = document.querySelector('#markdown-editor')
    if (editorElement) {
      // 移除键盘事件监听
      editorElement.removeEventListener('keydown', handleMarkdownKeyDown, true)
      // 移除编辑器内部输入元素的事件监听
      const editorInputs = editorElement.querySelectorAll('textarea, .ProseMirror')
      editorInputs.forEach((input) => {
        input.removeEventListener('keydown', handleMarkdownKeyDown, true)
      })
    }
    markdownEditor.value.destroy()
    markdownEditor.value = null
  }

  editMode.value = mode

  nextTick(() => {
    if (mode === 'markdown') {
      // 切换到markdown模式时，确保内容一致，避免触发修改检测
      editedContent.value = contentBeforeSwitch
      // 恢复修改状态
      isContentModified.value = wasModifiedBeforeSwitch
      initMarkdownEditor()
    } else {
      // 切换到源码模式时，确保内容一致
      editedContent.value = contentBeforeSwitch
      // 恢复修改状态
      isContentModified.value = wasModifiedBeforeSwitch
    }
  })
}

const saveFile = async () => {
  if (!selectedFile.value) return

  saving.value = true
  saveSuccess.value = false
  saveError.value = ''

  try {
    const formData = new FormData()
    formData.append('file_content', editedContent.value)
    formData.append('conversation_id', props.conversationId)

    const response = await axios.post(`/api/save_file/${selectedFile.value}`, formData, {
      headers: {
        'Content-Type': 'multipart/form-data'
      }
    })

    saving.value = false
    saveSuccess.value = true
    fileContent.value = editedContent.value // 更新本地内容
    originalContent.value = editedContent.value // 更新原始内容
    isContentModified.value = false // 重置修改状态

    // 保存编辑区域的滚动比例（用于恢复预览位置）
    const textarea = document.querySelector('.edit-textarea') as HTMLTextAreaElement
    if (textarea) {
      const scrollableHeight = textarea.scrollHeight - textarea.clientHeight
      if (scrollableHeight > 0) {
        editingScrollRatio.value = textarea.scrollTop / scrollableHeight
      }
    }

    // 3秒后隐藏成功提示
    setTimeout(() => {
      saveSuccess.value = false
    }, 3000)

  } catch (error) {
    saving.value = false
    saveError.value = '保存失败，请重试'
    setTimeout(() => {
      saveError.value = ''
    }, 3000)
  }
}

const handleKeyDown = (event: KeyboardEvent) => {
  // Ctrl+S 或 Cmd+S 保存
  if ((event.ctrlKey || event.metaKey) && event.key === 's') {
    event.preventDefault()
    saveFile()
  }
  // ESC 取消编辑
  if (event.key === 'Escape') {
    cancelEditing()
  }
}

// 移除原有 exportFile 函数
</script>

<style scoped>
@import '@/assets/css/chat.css';

.extra-info {
  display: flex;
  flex-direction: column;
  height: 100%;
  background-color: #f8f9fa; /* 调整为更柔和的背景 */
  padding: 0;
  box-sizing: border-box;
  overflow: hidden;
  position: relative;
}

/* Tab 切换栏样式（类似书签下拉栏） */
.tab-container {
  display: flex;
  background-color: #ffffff;
  border-bottom: 2px solid #e9ecef;
  padding: 0;
  margin: 0;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
  z-index: 10;
}

.tab-item {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 12px 20px;
  cursor: pointer;
  background-color: #ffffff;
  border: none;
  border-bottom: 3px solid transparent;
  transition: all 0.3s ease;
  position: relative;
  font-size: 14px;
  font-weight: 500;
  color: #6c757d;
}

.tab-item:hover {
  background-color: #f8f9fa;
  color: #495057;
}

.tab-item.active {
  background-color: #f8f9fa;
  color: #6b7280;
  border-bottom-color: #9ca3af;
  font-weight: 600;
}

.tab-item.active::after {
  content: '';
  position: absolute;
  bottom: -2px;
  left: 0;
  right: 0;
  height: 3px;
  background-color: #9ca3af;
}

.tab-icon {
  font-size: 16px;
}

.tab-text {
  font-size: 14px;
}

.tool-messages {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
  padding-bottom: 24px;
  background: linear-gradient(180deg, #f8f9fb 0%, #f4f5f7 100%);
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* WebKit-based browsers (Chrome, Safari) */
.tool-messages::-webkit-scrollbar {
    width: 10px;
}

.tool-messages::-webkit-scrollbar-thumb {
    background-color: rgba(88, 88, 88, 0.209);
    border-radius: 5px
}

.tool-messages::-webkit-scrollbar-track {
    background-color: rgba(255, 255, 255, 0.4);
    border-radius: 5px;
}

.tool-messages::-webkit-scrollbar-thumb:hover {
    background-color: rgba(83, 83, 83, 0.339);
}

/* 文件库内容样式（内嵌显示，非全屏） */
.file-library-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
  background: #f3f4f6;
  position: relative;
}

.file-library-content::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 1px;
  background: linear-gradient(90deg, transparent, rgba(0,0,0,0.08), transparent);
  pointer-events: none;
}

.file-library-body {
  flex: 1;
  display: flex;
  overflow: hidden;
  position: relative;
}

/* 整体面板固定宽高，并使用flex防止挤压 */
.file-library-full-panel {
  position: fixed;
  top: 8%;
  left: 8%;
  width: 84vw;
  height: 84vh;
  background: #f3f4f6;
  border-radius: 16px;
  box-shadow: 0 20px 60px rgba(0,0,0,0.15), 
              0 8px 24px rgba(0,0,0,0.1);
  z-index: 100;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border: 1px solid rgba(0,0,0,0.08);
  animation: panelFadeIn 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

@keyframes panelFadeIn {
  from {
    opacity: 0;
    transform: scale(0.96) translateY(-10px);
  }
  to {
    opacity: 1;
    transform: scale(1) translateY(0);
  }
}

.full-panel-header {
  position: sticky;
  top: 0;
  background: #ffffff;
  padding: 18px 24px;
  border-bottom: 1px solid rgba(0,0,0,0.08);
  z-index: 10;
  border-top-left-radius: 16px;
  border-top-right-radius: 16px;
  box-shadow: 0 2px 4px rgba(0,0,0,0.04);
}

.full-panel-header::after {
  content: '';
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  height: 1px;
  background: linear-gradient(90deg, transparent, rgba(0,0,0,0.05), transparent);
}

.full-panel-header h3 {
  margin: 0;
  font-size: 17px;
  font-weight: 600;
  color: #6b7280;
  display: flex;
  align-items: center;
  justify-content: space-between;
  letter-spacing: -0.01em;
}

.header-title {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #6b7280;
}

.full-panel-content {
  display: flex;
  flex-grow: 1;
  overflow: hidden;
}

.right-sidebar {
  width: 280px;
  flex: 0 0 280px;
  background: linear-gradient(180deg, #f9fafb 0%, #f3f4f6 100%);
  border-left: 1px solid rgba(229, 231, 235, 0.8);
  overflow-y: auto;
  overflow-x: hidden;
  padding: 0;
  position: relative;
  box-shadow: 
    inset 2px 0 8px rgba(0, 0, 0, 0.02),
    inset -1px 0 0 rgba(255, 255, 255, 0.5);
  display: flex;
  flex-direction: column;
  transition: width 0.3s ease, flex-basis 0.3s ease;
}

.right-sidebar.collapsed {
  width: 50px;
  flex: 0 0 50px;
  overflow: visible;
}

.right-sidebar::-webkit-scrollbar {
  width: 8px;
}

.right-sidebar::-webkit-scrollbar-track {
  background: rgba(243, 244, 246, 0.5);
  border-radius: 4px;
  margin: 8px 0;
}

.right-sidebar::-webkit-scrollbar-thumb {
  background: linear-gradient(180deg, 
    rgba(156, 163, 175, 0.4) 0%, 
    rgba(156, 163, 175, 0.3) 50%, 
    rgba(156, 163, 175, 0.4) 100%);
  border-radius: 4px;
  transition: background 0.3s ease;
  border: 2px solid transparent;
  background-clip: padding-box;
}

.right-sidebar::-webkit-scrollbar-thumb:hover {
  background: linear-gradient(180deg, 
    rgba(107, 114, 128, 0.5) 0%, 
    rgba(107, 114, 128, 0.4) 50%, 
    rgba(107, 114, 128, 0.5) 100%);
  background-clip: padding-box;
}

.file-list-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 15px 20px;
  background: #f5f5f5;
  border-bottom: 1px solid rgba(0,0,0,0.08);
  position: sticky;
  top: 0;
  z-index: 5;
  box-shadow: 0 2px 4px rgba(0,0,0,0.04);
  transition: padding 0.3s ease;
  min-height: 38px;
}

.right-sidebar.collapsed .file-list-header,
.left-sidebar.collapsed .file-list-header {
  padding: 16px 8px;
  justify-content: center;
  gap: 0;
}

.file-list-title {
  font-size: 15px;
  font-weight: 600;
  color: #6b7280;
  letter-spacing: -0.01em;
  transition: opacity 0.3s ease;
}

.file-list-content {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
}

.file-tree {
  padding: 10px 8px;
}

.file-tree-node {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 34px;
  margin-bottom: 4px;
  padding-top: 6px;
  padding-bottom: 6px;
  border-radius: 8px;
  cursor: pointer;
  user-select: none;
  transition: background-color 0.2s ease, transform 0.2s ease;
}

.file-tree-node:hover {
  background: rgba(59, 130, 246, 0.08);
}

.file-tree-node.selected {
  background: linear-gradient(135deg, #d1fae5 0%, #ecfdf5 100%);
  border: 1px solid rgba(16, 185, 129, 0.25);
}

.file-tree-node.folder {
  font-weight: 600;
}

.file-tree-node.file .file-name {
  color: #374151;
}

.file-tree-node.folder .file-name {
  color: #1f2937;
}

.file-tree-node.selected .file-name {
  color: #065f46;
}

.tree-arrow {
  width: 12px;
  color: #6b7280;
  text-align: center;
  flex-shrink: 0;
}

.tree-arrow.placeholder {
  opacity: 0.5;
}

.tree-icon {
  width: 18px;
  text-align: center;
  flex-shrink: 0;
}

.header-actions-group {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-left: auto;
}

/* 文件库展开/收缩按钮 - 独立样式（与刷新按钮相同的背景、边框和悬停效果） */
.file-list-toggle-button {
  position: static;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  padding: 4px;
  margin: 0;
  background: none;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
  opacity: 0.7;
  box-sizing: border-box;
}

.file-list-toggle-button:hover {
  background-color: rgba(0, 0, 0, 0.06);
  opacity: 1;
  transform: scale(1.1);
}

.file-list-toggle-button:active {
  transform: scale(0.95);
}

.file-list-toggle-button .file-toggle-icon {
  width: 12px;
  height: 12px;
  transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  display: block;
}

.file-list-toggle-button .file-toggle-icon.rotated-left {
  transform: rotate(-90deg);
}

.file-list-toggle-button .file-toggle-icon.rotated-right {
  transform: rotate(90deg);
}

.file-list-toggle-button:hover .file-toggle-icon.rotated-left {
  transform: rotate(-90deg);
}

.file-list-toggle-button:hover .file-toggle-icon.rotated-right {
  transform: rotate(90deg);
}

.right-sidebar.collapsed .file-list-header .file-list-toggle-button,
.left-sidebar.collapsed .file-list-header .file-list-toggle-button {
  margin: 0 auto;
}

.right-sidebar.collapsed .file-list-title,
.left-sidebar.collapsed .file-list-title {
  display: none;
}

.right-sidebar.collapsed .icon-button,
.left-sidebar.collapsed .icon-button {
  display: none;
}

.right-sidebar.collapsed .header-actions-group,
.left-sidebar.collapsed .header-actions-group {
  display: none;
}

.right-sidebar ul {
  list-style: none;
  padding: 12px 10px;
  margin: 0;
  flex: 1;
  overflow-y: auto;
  background: linear-gradient(180deg, rgba(249, 250, 251, 0.5) 0%, rgba(243, 244, 246, 0.3) 100%);
}

.right-sidebar li {
  display: flex;
  justify-content: flex-start;
  align-items: center;
  padding: 14px 16px;
  margin-bottom: 8px;
  background: linear-gradient(135deg, #ffffff 0%, #fafbfc 100%);
  border-radius: 12px;
  border: 1px solid rgba(229, 231, 235, 0.8);
  box-shadow: 
    0 1px 3px rgba(0, 0, 0, 0.04),
    0 1px 2px rgba(0, 0, 0, 0.02),
    inset 0 1px 0 rgba(255, 255, 255, 0.9);
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  cursor: pointer;
  position: relative;
  overflow: hidden;
  backdrop-filter: blur(10px);
}

.right-sidebar li::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  width: 4px;
  height: 100%;
  background: linear-gradient(180deg, 
    rgba(156, 163, 175, 0.3) 0%, 
    rgba(156, 163, 175, 0.15) 50%, 
    rgba(156, 163, 175, 0.3) 100%);
  opacity: 0;
  transition: opacity 0.3s ease, width 0.3s ease;
  border-radius: 12px 0 0 12px;
}

.right-sidebar li::after {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: linear-gradient(135deg, 
    rgba(255, 255, 255, 0.6) 0%, 
    rgba(249, 250, 251, 0.4) 100%);
  opacity: 0;
  transition: opacity 0.3s ease;
  pointer-events: none;
  border-radius: 12px;
}

.right-sidebar li:hover {
  background: linear-gradient(135deg, #ffffff 0%, #f8f9fa 50%, #f1f3f5 100%);
  border-color: rgba(209, 213, 219, 0.9);
  box-shadow: 
    0 4px 12px rgba(0, 0, 0, 0.08),
    0 2px 4px rgba(0, 0, 0, 0.04),
    inset 0 1px 0 rgba(255, 255, 255, 0.95),
    inset 0 -1px 0 rgba(0, 0, 0, 0.02);
  transform: translateY(-2px) scale(1.01);
}

.right-sidebar li:hover::before {
  opacity: 1;
  width: 4px;
}

.right-sidebar li:hover::after {
  opacity: 1;
}

.right-sidebar li.selected {
  background: linear-gradient(135deg, #d1fae5 0%, #ecfdf5 100%);
  border-color: rgba(16, 185, 129, 0.25);
  font-weight: 600;
  color: #065f46;
  box-shadow: 0 2px 10px rgba(16, 185, 129, 0.15), 
              0 1px 0 rgba(255,255,255,0.9) inset,
              0 0 0 1px rgba(16, 185, 129, 0.1) inset;
  transform: translateY(-1px);
}

.right-sidebar li.selected::before {
  opacity: 1;
  background: linear-gradient(180deg, #10b981, rgba(16, 185, 129, 0.4));
}

.right-sidebar li:active {
  transform: translateY(0) scale(0.98);
  box-shadow: 
    0 2px 4px rgba(0, 0, 0, 0.06),
    inset 0 1px 2px rgba(0, 0, 0, 0.05);
}

.right-sidebar li:last-child {
  margin-bottom: 0;
}

/* 全屏弹窗中的左侧边栏样式 */
.left-sidebar {
  width: 280px;
  flex: 0 0 280px;
  background: #e5e7eb;
  border-right: 1px solid rgba(0,0,0,0.1);
  overflow-y: auto;
  overflow-x: hidden;
  padding: 0;
  position: relative;
  box-shadow: inset -2px 0 4px rgba(0,0,0,0.03);
  display: flex;
  flex-direction: column;
  transition: width 0.3s ease, flex-basis 0.3s ease;
}

.left-sidebar.collapsed {
  width: 50px;
  flex: 0 0 50px;
  overflow: visible;
}

.left-sidebar::-webkit-scrollbar {
  width: 6px;
}

.left-sidebar::-webkit-scrollbar-track {
  background: transparent;
}

.left-sidebar::-webkit-scrollbar-thumb {
  background: rgba(0,0,0,0.12);
  border-radius: 3px;
  transition: background 0.2s ease;
}

.left-sidebar::-webkit-scrollbar-thumb:hover {
  background: rgba(0,0,0,0.18);
}

.left-sidebar .file-list-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 16px 24px;
  background: #f5f5f5;
  border-bottom: 1px solid rgba(0,0,0,0.08);
  position: sticky;
  top: 0;
  z-index: 5;
  box-shadow: 0 2px 4px rgba(0,0,0,0.04);
  transition: padding 0.3s ease;
  min-height: 56px;
}

.left-sidebar ul {
  list-style: none;
  padding: 20px 16px;
  margin: 0;
  flex: 1;
  overflow-y: auto;
}

.left-sidebar li {
  display: flex;
  justify-content: flex-start;
  align-items: center;
  padding: 12px 14px;
  margin-bottom: 6px;
  background: #ffffff;
  border-radius: 10px;
  border: 1px solid rgba(0,0,0,0.06);
  box-shadow: 0 2px 4px rgba(0,0,0,0.05);
  transition: transform 0.25s cubic-bezier(0.4, 0, 0.2, 1), box-shadow 0.25s cubic-bezier(0.4, 0, 0.2, 1), border-color 0.25s cubic-bezier(0.4, 0, 0.2, 1);
  cursor: pointer;
  position: relative;
  overflow: hidden;
}

.left-sidebar li::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  width: 3px;
  height: 100%;
  background: linear-gradient(180deg, transparent, rgba(0,0,0,0.08), transparent);
  opacity: 0;
  transition: opacity 0.25s ease;
}

.left-sidebar li:hover {
  background: linear-gradient(135deg, #ffffff 0%, #f8f9fa 100%);
  border-color: rgba(0,0,0,0.08);
  box-shadow: 0 2px 8px rgba(0,0,0,0.06), 
              0 1px 0 rgba(255,255,255,0.9) inset,
              0 -1px 0 rgba(0,0,0,0.02) inset;
  transform: translateY(-1px);
}

.left-sidebar li:hover::before {
  opacity: 1;
}

.left-sidebar li.selected {
  background: linear-gradient(135deg, #d1fae5 0%, #ecfdf5 100%);
  border-color: rgba(16, 185, 129, 0.25);
  font-weight: 600;
  color: #065f46;
  box-shadow: 0 2px 10px rgba(16, 185, 129, 0.15), 
              0 1px 0 rgba(255,255,255,0.9) inset,
              0 0 0 1px rgba(16, 185, 129, 0.1) inset;
  transform: translateY(-1px);
}

.left-sidebar li.selected::before {
  opacity: 1;
  background: linear-gradient(180deg, #10b981, rgba(16, 185, 129, 0.4));
}

.left-sidebar li:active {
  transform: translateY(0);
  box-shadow: 0 1px 3px rgba(0,0,0,0.05);
}

.left-sidebar li:last-child {
  margin-bottom: 0;
}

.file-name {
  flex: 1;
  word-break: break-all;
  overflow-wrap: break-word;
  font-size: 13.5px;
  line-height: 1.6;
  color: #4b5563;
  transition: color 0.3s ease, font-weight 0.3s ease;
  font-weight: 500;
  letter-spacing: -0.01em;
  position: relative;
  z-index: 1;
}

.right-sidebar li:hover .file-name {
  color: #1f2937;
}

.right-sidebar li.selected .file-name,
.left-sidebar li.selected .file-name {
  color: #065f46;
}

.right-sidebar .empty-file-list,
.left-sidebar .empty-file-list {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 20px;
  text-align: center;
  color: #6b7280;
  flex: 1;
  background: linear-gradient(180deg, 
    rgba(249, 250, 251, 0.3) 0%, 
    rgba(243, 244, 246, 0.2) 100%);
  border-radius: 12px;
  margin: 12px 10px;
}

.empty-file-list p {
  margin: 8px 0;
  font-size: 14px;
  font-weight: 500;
  color: #9ca3af;
  letter-spacing: -0.01em;
}

.empty-file-list .empty-hint {
  font-size: 12px;
  color: #d1d5db;
  font-weight: 400;
  letter-spacing: 0.01em;
}

.left-preview {
  flex: 1;
  display: flex;
  flex-direction: column;
  background: #f9fafb;
  overflow: hidden;
  position: relative;
}

.right-preview {
  flex: 1;
  display: flex;
  flex-direction: column;
  background: #f9fafb;
  overflow: hidden;
  position: relative;
}

.preview-header {
  position: sticky;
  top: 0;
  background: #ffffff;
  padding: 16px 24px;
  border-bottom: 1px solid rgba(0,0,0,0.08);
  z-index: 5;
  box-shadow: 0 2px 4px rgba(0,0,0,0.04);
  min-height: 38px;
}

.preview-header::after {
  content: '';
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  height: 1px;
  background: linear-gradient(90deg, transparent, rgba(0,0,0,0.05), transparent);
}

.preview-header h4 {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: #1a1a1a;
  display: flex;
  align-items: center;
  justify-content: space-between;
  letter-spacing: -0.01em;
}

.preview-content {
  padding: 28px 32px;
  height: auto;
  background: #ffffff;
  max-width: 100%;
  overflow-y: auto;
  word-break: break-word;
  font-size: 15px !important;
  line-height: 1.7;
  color: #374151;
  position: relative;
  box-shadow: inset 0 1px 2px rgba(0,0,0,0.02);
}

/* Custom scrollbar for preview content */
.preview-content::-webkit-scrollbar {
  width: 8px;
}

.preview-content::-webkit-scrollbar-track {
  background: transparent;
  margin: 8px 0;
}

.preview-content::-webkit-scrollbar-thumb {
  background: rgba(0,0,0,0.12);
  border-radius: 4px;
  transition: background 0.2s ease;
  border: 2px solid transparent;
  background-clip: padding-box;
}

.preview-content::-webkit-scrollbar-thumb:hover {
  background: rgba(0,0,0,0.2);
  background-clip: padding-box;
}

/* 文件预览中的 Markdown 表格样式 - 灰白色系高级配色 */
.preview-content :deep(table),
.preview-content :deep(.markdown-table) {
  width: 100%;
  border-collapse: separate !important;
  border-spacing: 0;
  margin: 20px 0;
  border: none !important;
  background-color: #ffffff;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06),
              0 1px 3px rgba(0, 0, 0, 0.04),
              inset 0 1px 0 rgba(255, 255, 255, 0.9);
  border-radius: 8px;
  overflow: hidden;
}

.preview-content :deep(table th),
.preview-content :deep(table td),
.preview-content :deep(.markdown-table th),
.preview-content :deep(.markdown-table td) {
  padding: 14px 16px;
  border: none !important;
  text-align: left;
  vertical-align: top;
  transition: background-color 0.2s ease, color 0.2s ease;
}

.preview-content :deep(table th),
.preview-content :deep(.markdown-table th) {
  background: linear-gradient(180deg, #f8f9fa 0%, #f1f3f5 100%);
  font-weight: 600;
  color: #1f2937;
  border-bottom: 2px solid #e5e7eb !important;
  position: relative;
  text-transform: uppercase;
  font-size: 12px;
  letter-spacing: 0.5px;
}

.preview-content :deep(table th:not(:last-child)),
.preview-content :deep(.markdown-table th:not(:last-child)) {
  border-right: 1px solid #e5e7eb !important;
}

.preview-content :deep(table td:not(:last-child)),
.preview-content :deep(.markdown-table td:not(:last-child)) {
  border-right: 1px solid #f3f4f6 !important;
}

.preview-content :deep(table tr:nth-child(even) td),
.preview-content :deep(.markdown-table tr:nth-child(even) td) {
  background-color: #fafbfc;
}

.preview-content :deep(table tr:nth-child(odd) td),
.preview-content :deep(.markdown-table tr:nth-child(odd) td) {
  background-color: #ffffff;
}

.preview-content :deep(table tr:hover td),
.preview-content :deep(.markdown-table tr:hover td) {
  background-color: #f0f4f8 !important;
  color: #111827;
}

.preview-content :deep(table tr:first-child th:first-child),
.preview-content :deep(.markdown-table tr:first-child th:first-child) {
  border-top-left-radius: 8px;
}

.preview-content :deep(table tr:first-child th:last-child),
.preview-content :deep(.markdown-table tr:first-child th:last-child) {
  border-top-right-radius: 8px;
}

.preview-content :deep(table tr:last-child td:first-child),
.preview-content :deep(.markdown-table tr:last-child td:first-child) {
  border-bottom-left-radius: 8px;
}

.preview-content :deep(table tr:last-child td:last-child),
.preview-content :deep(.markdown-table tr:last-child td:last-child) {
  border-bottom-right-radius: 8px;
}

/* 全局表格样式 - 灰白色系高级配色 */
:deep(table),
:deep(.markdown-table) {
  border-collapse: separate !important;
  border-spacing: 0;
  border: none !important;
}

:deep(table th),
:deep(table td),
:deep(.markdown-table th),
:deep(.markdown-table td) {
  border: none !important;
}

.no-selection {
  color: #9ca3af;
  text-align: center;
  flex: 1;
  display: flex;
  justify-content: center;
  align-items: center;
  font-size: 14px;
  font-weight: 500;
  letter-spacing: -0.01em;
}

.tool-frame {
  border: 1px solid #e6e8ec;
  border-radius: 12px;
  margin-bottom: 0;
  background: linear-gradient(180deg, #ffffff 0%, #f9fafb 100%);
  box-shadow:
    0 6px 18px rgba(17, 24, 39, 0.06),
    0 1px 6px rgba(17, 24, 39, 0.04);
  position: relative;
  transition: background-color 0.3s ease, box-shadow 0.3s ease, transform 0.3s ease;
  --end-color: #f9fafb;
}

.tool-frame:hover {
  box-shadow:
    0 12px 28px rgba(17, 24, 39, 0.08),
    0 4px 12px rgba(17, 24, 39, 0.05);
  transform: translateY(-2px);
}

.content-container {
  position: relative;
  padding: 18px 20px 28px;
  overflow: hidden;
  background: #ffffff;
  border-radius: 10px;
  transition: max-height 1s ease;
}

.content-container:not(.expanded) {
  max-height: 300px;
}

.content-container.expanded {
  max-height: none; /* Changed to none for full expansion */
}

.content-container.needs-expand:not(.expanded)::after {
  content: '';
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  height: 60px; /* 调整渐变高度 */
  background: linear-gradient(to bottom, transparent, var(--end-color)); /* 使用变量匹配背景 */
  pointer-events: none;
  transition: background 0.3s ease-in-out; /* 添加过渡效果 */
}

.highlighted .content-container.needs-expand:not(.expanded)::after {
  background: linear-gradient(to bottom, transparent, rgba(217, 244, 227, 0.9)); /* 匹配高亮背景 */
}

.answer-robot-content {
  padding-bottom: 10px;
}

.expand-button {
  position: absolute;
  bottom: 12px;
  left: 50%;
  transform: translateX(-50%);
  background: rgba(243, 244, 246, 0.9);
  border: 1px solid #e5e7eb;
  border-radius: 999px;
  cursor: pointer;
  font-size: 12px;
  color: #4b5563;
  z-index: 1;
  padding: 6px 14px;
  margin: 0;
  box-shadow: 0 4px 12px rgba(17, 24, 39, 0.06);
  transition: all 0.2s ease;
}

.expand-button:hover {
  color: #111827;
  background: #ffffff;
  transform: translateX(-50%) translateY(-1px);
}

.arrow-icon {
  display: inline-block;
  transform: scaleY(0.6); /* 调整箭头形状 */
}

.answer-robot-tool {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 10px;
  row-gap: 12px;
}

.answer-robot-tool-name-extra {
  font-size: 15px;
  font-weight: 600;
  color: #1f2937;
  letter-spacing: 0.01em;
  display: flex;
  align-items: center;
  gap: 8px;
}

/* 新增arguments列表样式 */
.answer-robot-tool-args {
  margin-top: 0;
  padding: 10px 12px;
  background: #f6f7f9;
  border-radius: 10px;
  border: 1px solid #e6e8ec;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.85);
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 8px 14px;
  align-items: center;
  max-width: 100%;
}

.arg-item {
  display: contents; /* 使子元素成为grid items */
}

.arg-key {
  font-weight: 600;
  color: #374151;
  padding: 4px 8px 4px 6px;
  border-right: none;
  background: transparent;
  letter-spacing: 0.01em;
  border-radius: 6px;
}

.arg-value {
  color: #4b5563;
  font-weight: 500;
  word-break: break-all;
  overflow-wrap: break-word;
  padding: 6px 10px;
  background: #ffffff;
  border: 1px solid #e5e7eb;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.9);
  border-radius: 8px;
}

.highlighted {
  background-color: #d9f4e3;
  box-shadow:
    0 14px 28px rgba(15, 23, 42, 0.1),
    0 5px 12px rgba(15, 23, 42, 0.07);
  transform: translateY(-2px);
  border: 2px solid #6ec48d;
  --end-color: #d9f4e3;
  position: relative;
}

.highlighted::before {
  content: '';
  position: absolute;
  top: 10px;
  bottom: 10px;
  left: 8px;
  width: 3px;
  border-radius: 999px;
  background: linear-gradient(180deg, #6ec48d 0%, #4fa86f 100%);
  box-shadow: 0 4px 10px rgba(79, 168, 111, 0.28);
}

:deep(.structured-list) {
  list-style-type: disc;
  padding-left: 20px;
  margin: 10px 0;
}

:deep(.structured-list li) {
  margin-bottom: 5px;
}

:deep(.structured-dict) {
  margin: 10px 0;
}

:deep(.structured-dict dt) {
  font-weight: bold;
  margin-top: 10px;
}

:deep(.structured-dict dd) {
  margin-left: 20px;
  margin-bottom: 5px;
}

:deep(.structured-table) {
  width: 100%;
  border-collapse: collapse;
  margin: 10px 0;
  background-color: #f8f9fa;
  box-shadow: 0 1px 3px rgba(0,0,0,0.1);
}

:deep(.structured-table th) {
  background-color: #e9ecef;
  padding: 8px;
  text-align: left;
  border-bottom: 2px solid #dee2e6;
}

:deep(.structured-table td) {
  padding: 8px;
  border-bottom: 1px solid #dee2e6;
  vertical-align: top;
}

:deep(.structured-table td:nth-child(1)) {
  word-break: normal;
  white-space: nowrap;
  background-color: #e9ecef; /* 加深 key 列背景 */
}

:deep(.structured-table td:nth-child(2)) {
  word-break: break-all;
  overflow-wrap: break-word;
}

:deep(.structured-table table) {
  margin: 0;
  width: 100%;
}

:deep(.structured-item) {
  margin-bottom: 20px;
  padding: 10px;
  background-color: transparent;

}

:deep(.structured-item h4) {
  margin: 0 0 10px 0;
  font-size: 16px;
  color: #333;
}

:deep(.p-content-markdown) {
  font-size: 12px !important;
  color: #4d4d4d;
  line-height: 1.6;
}

/* Markdown 表格样式 - 用于工具消息显示 - 灰白色系高级配色 */
:deep(.p-content-markdown table) {
  width: 100%;
  border-collapse: separate !important;
  border-spacing: 0;
  margin: 20px 0;
  border: none !important;
  background-color: #ffffff;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06),
              0 1px 3px rgba(0, 0, 0, 0.04),
              inset 0 1px 0 rgba(255, 255, 255, 0.9);
  border-radius: 8px;
  overflow: hidden;
}

:deep(.p-content-markdown table th),
:deep(.p-content-markdown table td) {
  padding: 14px 16px;
  border: none !important;
  text-align: left;
  vertical-align: top;
  transition: background-color 0.2s ease, color 0.2s ease;
}

:deep(.p-content-markdown table th) {
  background: linear-gradient(180deg, #f8f9fa 0%, #f1f3f5 100%);
  font-weight: 600;
  color: #1f2937;
  border-bottom: 2px solid #e5e7eb !important;
  position: relative;
  text-transform: uppercase;
  font-size: 12px;
  letter-spacing: 0.5px;
}

:deep(.p-content-markdown table th:not(:last-child)) {
  border-right: 1px solid #e5e7eb !important;
}

:deep(.p-content-markdown table td:not(:last-child)) {
  border-right: 1px solid #f3f4f6 !important;
}

:deep(.p-content-markdown table tr:nth-child(even) td) {
  background-color: #fafbfc;
}

:deep(.p-content-markdown table tr:nth-child(odd) td) {
  background-color: #ffffff;
}

:deep(.p-content-markdown table tr:hover td) {
  background-color: #f0f4f8 !important;
  color: #111827;
}

:deep(.p-content-markdown table tr:first-child th:first-child) {
  border-top-left-radius: 8px;
}

:deep(.p-content-markdown table tr:first-child th:last-child) {
  border-top-right-radius: 8px;
}

:deep(.p-content-markdown table tr:last-child td:first-child) {
  border-bottom-left-radius: 8px;
}

:deep(.p-content-markdown table tr:last-child td:last-child) {
  border-bottom-right-radius: 8px;
}

.icon-button {
  width: 18px;
  height: 18px;
  cursor: pointer;
  margin-left: 10px;
  vertical-align: middle;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
  border-radius: 6px;
  padding: 4px;
  opacity: 0.7;
}

.icon-button:hover {
  background-color: rgba(0,0,0,0.06);
  opacity: 1;
  transform: scale(1.1);
}

.icon-button:active {
  transform: scale(0.95);
}

.preview-panel {
  position: fixed;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  width: 80%;
  max-height: 80%;
  background: linear-gradient(135deg, #ffffff, #f8f9fa);
  padding: 0;
  border-radius: 12px;
  box-shadow: 0 8px 24px rgba(0,0,0,0.2);
  z-index: 100;
  display: flex;
  flex-direction: column;
}

.preview-header {
  position: sticky;
  top: 0;
  background-color: #ffffff;
  padding: 15px 20px;
  border-bottom: 1px solid #eee;
  z-index: 1;
  border-top-left-radius: 12px;
  border-top-right-radius: 12px;
}

.preview-header h3 {
  margin: 0;
  font-size: 18px;
  color: #333;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.preview-content {
  padding: 20px;
  overflow-y: auto;
  flex-grow: 1;
}

/* Custom scrollbar for preview content */
.preview-content::-webkit-scrollbar {
  width: 6px;
}

.preview-content::-webkit-scrollbar-track {
  background: #f1f1f1;
  border-radius: 10px;
}

.preview-content::-webkit-scrollbar-thumb {
  background: #ccc;
  border-radius: 10px;
}

.preview-content::-webkit-scrollbar-thumb:hover {
  background: #aaa;
}

.close-button {
  cursor: pointer;
  float: right;
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  font-size: 24px;
  color: #6b7280;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
  line-height: 1;
  font-weight: 300;
}

.close-button:hover {
  background-color: rgba(0,0,0,0.06);
  color: #374151;
  transform: scale(1.1);
}

.close-button:active {
  transform: scale(0.95);
}

.error {
  color: #dc2626;
  padding: 12px 16px;
  background: linear-gradient(135deg, #fef2f2 0%, #fee2e2 100%);
  border-radius: 8px;
  border: 1px solid rgba(239, 68, 68, 0.2);
  font-size: 14px;
  font-weight: 500;
  margin: 16px 0;
}

/* 对于HTML预览，添加缩放以压缩内容 */
:deep(.html-preview) {
  width: 100%;
  word-wrap: break-word;
  overflow-wrap: break-word;
  white-space: normal;
  box-sizing: border-box;
  transform-origin: top left;
  transform: scale(var(--scale-factor, 1));
  overflow: visible; /* 允许内容扩展以计算宽度 */
}

:deep(.html-preview *) {
  max-width: 100%;
  box-sizing: border-box;
}

:deep(.html-preview table) {
  width: 100%;
  table-layout: fixed;
  border-collapse: collapse;
}

:deep(.html-preview td, .html-preview th) {
  word-break: break-all;
  padding: 8px;
  border: 1px solid #ddd;
  vertical-align: top;
}

:deep(.html-preview img) {
  max-width: 100%;
  height: auto;
  display: block;
}

.html-iframe {
  width: 100%;
  height: auto;
  min-height: 300px;
  border: none;
  background: white;
  overflow: hidden;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.06);
}

.preview-image {
  max-width: 100%;
  height: auto;
  display: block;
  margin: 0 auto;
  border-radius: 8px;
  box-shadow: 0 4px 12px rgba(0,0,0,0.08);
  transition: transform 0.3s ease, box-shadow 0.3s ease;
}

.preview-image:hover {
  transform: scale(1.01);
  box-shadow: 0 6px 20px rgba(0,0,0,0.12);
}

.unsupported {
  color: #666;
  text-align: center;
  padding: 20px;
}

.answer-robot-reasoner {
  background-color: #f5f5f5;
  padding: 8px 12px;
  border-radius: 6px;
  margin-bottom: 8px;
  border-left: 3px solid rgba(47, 79, 79, 0.565);
}

:deep(.pptx-preview-wrapper) {
  height: auto !important;
  overflow-y: visible !important;
  background: transparent !important;
  width: 100% !important;
  margin: 0 !important;
}

/* 简单灰白色按钮 */
.export-button {
  background: linear-gradient(135deg, #ffffff 0%, #f8f9fa 100%);
  color: #374151;
  border: 1px solid rgba(0,0,0,0.08);
  padding: 8px 16px;
  border-radius: 8px;
  cursor: pointer;
  font-weight: 500;
  font-size: 13px;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
  box-shadow: 0 1px 2px rgba(0,0,0,0.04), 
              0 1px 0 rgba(255,255,255,0.9) inset;
}

.export-button:hover {
  background: linear-gradient(135deg, #f8f9fa 0%, #f1f3f5 100%);
  border-color: rgba(0,0,0,0.12);
  box-shadow: 0 2px 4px rgba(0,0,0,0.06), 
              0 1px 0 rgba(255,255,255,0.9) inset;
  transform: translateY(-1px);
}

.export-button:active {
  transform: translateY(0);
  box-shadow: 0 1px 2px rgba(0,0,0,0.04);
}

/* 下拉菜单样式 */
.export-container {
  position: relative;
  display: inline-block;
}

.export-dropdown {
  position: absolute;
  top: calc(100% + 4px);
  left: 0;
  background: #ffffff;
  border: 1px solid rgba(0,0,0,0.08);
  border-radius: 10px;
  box-shadow: 0 4px 12px rgba(0,0,0,0.1), 
              0 1px 0 rgba(255,255,255,0.9) inset;
  z-index: 20;
  min-width: 120px;
  overflow: hidden;
  animation: dropdownFadeIn 0.2s cubic-bezier(0.4, 0, 0.2, 1);
}

@keyframes dropdownFadeIn {
  from {
    opacity: 0;
    transform: translateY(-4px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.dropdown-item {
  display: block;
  width: 100%;
  padding: 10px 16px;
  background: none;
  border: none;
  text-align: left;
  cursor: pointer;
  transition: all 0.15s ease;
  font-size: 13px;
  color: #374151;
  font-weight: 500;
}

.dropdown-item:first-child {
  border-top-left-radius: 10px;
  border-top-right-radius: 10px;
}

.dropdown-item:last-child {
  border-bottom-left-radius: 10px;
  border-bottom-right-radius: 10px;
}

.dropdown-item:hover {
  background: linear-gradient(135deg, #f8f9fa 0%, #f1f3f5 100%);
  color: #1a1a1a;
}

.dropdown-item:active {
  background: #e9ecef;
}

/* 导出反馈消息样式 */
.export-feedback {
  position: absolute;
  top: calc(100% + 8px);
  left: 50%;
  transform: translateX(-50%);
  padding: 10px 18px;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 500;
  z-index: 15;
  box-shadow: 0 4px 12px rgba(0,0,0,0.12), 
              0 1px 0 rgba(255,255,255,0.9) inset;
  animation: feedbackFadeIn 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  white-space: nowrap;
}

.export-feedback.success {
  background: linear-gradient(135deg, #d1fae5 0%, #ecfdf5 100%);
  color: #065f46;
  border: 1px solid rgba(16, 185, 129, 0.2);
}

.export-feedback.error {
  background: linear-gradient(135deg, #fee2e2 0%, #fef2f2 100%);
  color: #991b1b;
  border: 1px solid rgba(239, 68, 68, 0.2);
}

.export-feedback:not(.success):not(.error) {
  background: linear-gradient(135deg, #f3f4f6 0%, #ffffff 100%);
  color: #374151;
  border: 1px solid rgba(0,0,0,0.08);
}

@keyframes feedbackFadeIn {
  from {
    opacity: 0;
    transform: translateX(-50%) translateY(-4px);
  }
  to {
    opacity: 1;
    transform: translateX(-50%) translateY(0);
  }
}

/* 添加样式调整 */
.preview-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
  position: relative;
}

.preview-header h4 {
  margin: 0;
  flex-grow: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
  position: relative;
}

.icon-button {
  cursor: pointer;
  width: 20px;
  height: 20px;
}

/* 编辑相关样式 */
.edit-button, .save-button, .cancel-button {
  background: linear-gradient(135deg, #ffffff 0%, #f8f9fa 100%);
  color: #64748b;
  border: 1px solid rgba(0,0,0,0.08);
  padding: 8px 16px;
  border-radius: 8px;
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
  margin-right: 6px;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04), 
              0 1px 0 rgba(255,255,255,0.9) inset;
}

.edit-button:hover {
  background: linear-gradient(135deg, #f8f9fa 0%, #f1f3f5 100%);
  border-color: rgba(0,0,0,0.12);
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.06), 
              0 1px 0 rgba(255,255,255,0.9) inset;
  transform: translateY(-1px);
}

.edit-button:active {
  transform: translateY(0);
}

.save-button {
  color: #059669;
  border-color: rgba(16, 185, 129, 0.3);
  min-width: 80px;
  background: linear-gradient(135deg, #f0fdf4 0%, #ffffff 100%);
}

.save-button:hover:not(:disabled) {
  background: linear-gradient(135deg, #d1fae5 0%, #f0fdf4 100%);
  border-color: #10b981;
  color: #047857;
  box-shadow: 0 2px 8px rgba(16, 185, 129, 0.2), 
              0 1px 0 rgba(255,255,255,0.9) inset;
  transform: translateY(-1px);
}

.save-button:active:not(:disabled) {
  transform: translateY(0);
}

.save-button:disabled {
  color: #94a3b8;
  border-color: rgba(0,0,0,0.06);
  cursor: not-allowed;
  background: #f9fafb;
  opacity: 0.6;
}

.cancel-button {
  color: #dc2626;
  border-color: rgba(248, 113, 113, 0.3);
  background: linear-gradient(135deg, #fef2f2 0%, #ffffff 100%);
}

.cancel-button:hover {
  background: linear-gradient(135deg, #fee2e2 0%, #fef2f2 100%);
  border-color: #f87171;
  color: #b91c1c;
  box-shadow: 0 2px 8px rgba(248, 113, 113, 0.2), 
              0 1px 0 rgba(255,255,255,0.9) inset;
  transform: translateY(-1px);
}

.cancel-button:active {
  transform: translateY(0);
}

.last-button {
  margin-right: 0; /* 最后一个按钮没有右边距 */
}

.edit-content {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.edit-textarea {
  flex: 1;
  width: 100%;
  padding: 15px;
  border: none;
  outline: none;
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
  font-size: 14px;
  line-height: 1.5;
  resize: none;
  background-color: #f8f9fa;
  border-radius: 4px;
  box-sizing: border-box;
}

.edit-textarea:focus {
  background-color: #ffffff;
  box-shadow: inset 0 0 0 2px #007bff;
}

.save-feedback {
  position: fixed;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  padding: 12px 24px;
  border-radius: 8px;
  font-size: 16px;
  font-weight: 500;
  z-index: 200;
  text-align: center;
  box-shadow: 0 4px 12px rgba(0,0,0,0.15);
  animation: fadeInOut 2s ease-in-out forwards;
}

.save-feedback.success {
  background-color: #d4edda;
  color: #155724;
  border: 1px solid #c3e6cb;
}

.save-feedback.error {
  background-color: #f8d7da;
  color: #721c24;
  border: 1px solid #f5c6cb;
}

@keyframes fadeInOut {
  0% {
    opacity: 0;
    transform: translate(-50%, -50%) scale(0.8);
  }
  20% {
    opacity: 1;
    transform: translate(-50%, -50%) scale(1);
  }
  80% {
    opacity: 1;
    transform: translate(-50%, -50%) scale(1);
  }
  100% {
    opacity: 0;
    transform: translate(-50%, -50%) scale(0.8);
  }
}

/* Markdown编辑器样式 */
.markdown-editor-container {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.markdown-editor {
  flex: 1;
  border-radius: 4px;
  overflow: hidden;
}

/* 按钮分隔符 */
.button-separator {
  width: 1px;
  height: 20px;
  background-color: #e2e8f0;
  margin: 0 12px;
  display: inline-block;
}

/* 模式切换按钮样式 */
.mode-button {
  background: linear-gradient(135deg, #ffffff 0%, #f8f9fa 100%);
  color: #64748b;
  border: 1px solid rgba(0,0,0,0.08);
  padding: 8px 16px;
  border-radius: 8px;
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
  margin-right: 6px;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04), 
              0 1px 0 rgba(255,255,255,0.9) inset;
}

.mode-button:hover {
  background: linear-gradient(135deg, #f8f9fa 0%, #f1f3f5 100%);
  border-color: rgba(0,0,0,0.12);
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.06), 
              0 1px 0 rgba(255,255,255,0.9) inset;
  transform: translateY(-1px);
}

.mode-button:active {
  transform: translateY(0);
}

.mode-button.active {
  background: linear-gradient(135deg, #d1fae5 0%, #ecfdf5 100%);
  color: #059669;
  border-color: rgba(16, 185, 129, 0.3);
  box-shadow: 0 2px 6px rgba(16, 185, 129, 0.15), 
              0 1px 0 rgba(255,255,255,0.9) inset;
}

.mode-button.active:hover {
  background: linear-gradient(135deg, #a7f3d0 0%, #d1fae5 100%);
  box-shadow: 0 3px 8px rgba(16, 185, 129, 0.2), 
              0 1px 0 rgba(255,255,255,0.9) inset;
}

/* Toast UI Editor 自定义样式 */
:deep(.toastui-editor-defaultUI) {
  border: none !important;
  border-radius: 4px;
  font-size: 16px !important;
}

:deep(.toastui-editor-defaultUI .toastui-editor-main) {
  border: none !important;
  font-size: 16px !important;
}

:deep(.toastui-editor-defaultUI .toastui-editor-md-container) {
  border-right: 1px solid #e9ecef !important;
  font-size: 16px !important;
}

:deep(.toastui-editor-defaultUI .toastui-editor-ww-container) {
  border: none !important;
  font-size: 16px !important;
}

/* 确保Toast UI Editor预览区域字体大小 */
:deep(.toastui-editor-defaultUI .toastui-editor-md-preview) {
  font-size: 16px !important;
  line-height: 1.6 !important;
}

:deep(.toastui-editor-defaultUI .toastui-editor-md-preview *) {
  font-size: 16px !important;
  line-height: 1.6 !important;
}

:deep(.toastui-editor-defaultUI .toastui-editor-md-preview h1),
:deep(.toastui-editor-defaultUI .toastui-editor-md-preview h2),
:deep(.toastui-editor-defaultUI .toastui-editor-md-preview h3),
:deep(.toastui-editor-defaultUI .toastui-editor-md-preview h4),
:deep(.toastui-editor-defaultUI .toastui-editor-md-preview h5),
:deep(.toastui-editor-defaultUI .toastui-editor-md-preview h6),
:deep(.toastui-editor-defaultUI .toastui-editor-md-preview p),
:deep(.toastui-editor-defaultUI .toastui-editor-md-preview li),
:deep(.toastui-editor-defaultUI .toastui-editor-md-preview blockquote) {
  font-size: 16px !important;
  line-height: 1.6 !important;
}

/* 修复Toast UI Editor预览区域表格表头颜色 */
:deep(.toastui-editor-defaultUI .toastui-editor-md-preview table th),
:deep(.toastui-editor-defaultUI .toastui-editor-ww-container table th) {
  color: #1f2937 !important;
  background: linear-gradient(180deg, #f8f9fa 0%, #f1f3f5 100%) !important;
}

:deep(.toastui-editor-defaultUI .toastui-editor-md-preview table th *),
:deep(.toastui-editor-defaultUI .toastui-editor-ww-container table th *) {
  color: #1f2937 !important;
}

/* 增大编辑器内所有文本的字体大小 */
:deep(.toastui-editor-defaultUI textarea) {
  font-size: 16px !important;
  line-height: 1.6 !important;
}

:deep(.toastui-editor-defaultUI .ProseMirror) {
  font-size: 16px !important;
  line-height: 1.6 !important;
}
</style>

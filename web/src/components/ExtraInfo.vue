<template>
  <div class="extra-info">
    <div class="preview-viewport-body">
      <!-- 左侧预览主区域 -->
      <div class="preview-main">
        <div class="preview-tab-bar">
          <div
            class="preview-tab-switch"
            role="tablist"
            aria-label="预览视窗切换"
            :data-active="activeTab"
          >
            <span class="preview-tab-thumb" aria-hidden="true"></span>
            <button
              type="button"
              role="tab"
              class="preview-tab-option"
              :class="{ 'preview-tab-option--active': activeTab === 'files' }"
              :aria-selected="activeTab === 'files'"
              @click="activeTab = 'files'"
            >文件</button>
            <button
              type="button"
              role="tab"
              class="preview-tab-option"
              :class="{ 'preview-tab-option--active': activeTab === 'agents' }"
              :aria-selected="activeTab === 'agents'"
              @click="activeTab = 'agents'"
            >子智能体</button>
            <button
              type="button"
              role="tab"
              class="preview-tab-option"
              :class="{ 'preview-tab-option--active': activeTab === 'web' }"
              :aria-selected="activeTab === 'web'"
              @click="activeTab = 'web'"
            >网页</button>
          </div>
        </div>

        <div class="preview-content-area">
        <!-- 文件 Tab -->
        <template v-if="activeTab === 'files'">
          <div v-if="selectedFile" class="preview-pane">
            <div class="preview-header">
              <h4 class="preview-header-title">{{ selectedFile }}</h4>
              <div class="header-actions">
                <button v-if="isEditableFile && !isEditing" class="edit-button" @click="startEditing">编辑</button>
                <div v-if="isHtml && !isEditing" class="export-container">
                  <button class="export-button" @click="toggleExportOptions">导出</button>
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
          <div v-else class="preview-empty">
            <p class="preview-empty-text">预览窗口</p>
          </div>
        </template>

        <!-- 子智能体 Tab -->
        <template v-else-if="activeTab === 'agents'">
          <div
            v-if="groupedSubAgentMessages.length"
            class="agent-messages"
            ref="agentMessagesContainer"
            @scroll="handleScroll"
          >
            <article
              v-for="(group, index) in groupedSubAgentMessages"
              :key="`${group.tool_call_id}-${index}`"
              class="sub-agent-card"
              :class="{
                'sub-agent-card--focused': props.scrollToId === group.tool_call_id,
                'sub-agent-card--streaming': isSubAgentStreaming(index),
              }"
              :ref="el => toolRefs[index] = el as HTMLElement"
            >
              <header class="sub-agent-header">
                <div class="sub-agent-identity">
                  <span class="sub-agent-avatar" aria-hidden="true">
                    <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                      <circle cx="12" cy="8" r="3.5" />
                      <path d="M5 20c0-3.3 3.1-5 7-5s7 1.7 7 5" />
                    </svg>
                  </span>
                  <h4 class="sub-agent-name">{{ getSubAgentName(group) }}</h4>
                </div>
                <span v-if="isSubAgentStreaming(index)" class="sub-agent-live-badge">
                  <span class="sub-agent-live-dot" aria-hidden="true"></span>
                  生成中
                </span>
              </header>

              <div
                class="sub-agent-body"
                :class="{ 'sub-agent-body--expanded': isSubAgentExpanded(group, index) }"
                :ref="el => setSubAgentBodyRef(getSubAgentStateKey(group, index), el as HTMLElement | null)"
              >
                <template v-for="(msg, msgIndex) in sortSubAgentMessages(group.messages)" :key="msgIndex">
                  <div v-if="msg.type === 'reasoner_content'" class="sub-agent-reasoner">
                    <div class="p-content-markdown" v-html="renderMarkdown(msg.content ?? '')"></div>
                  </div>
                  <div v-else-if="msg.type === 'get_tools' && msg.tool_calls?.length" class="sub-agent-tools">
                    <ToolCallsBlock
                      :calls="buildToolCallItems(msg.tool_calls, msg.tool_call_id, msg.type)"
                      :show-results="false"
                    />
                  </div>
                  <div
                    v-else-if="(msg.type === 'text' || (msg.role === 'agent' && msg.type !== 'get_tools' && msg.type !== 'tool')) && msg.content"
                    class="sub-agent-text"
                  >
                    <div class="p-content-markdown" v-html="renderMarkdown(msg.content)"></div>
                  </div>
                  <div v-else-if="msg.role === 'tool' && msg.type === 'agent' && msg.content" class="sub-agent-text">
                    <div class="p-content-markdown" v-html="renderMarkdown((msg.content || '').replace(SESSION_ID_PREFIX, ''))"></div>
                  </div>
                </template>
              </div>

              <footer class="sub-agent-footer">
                <button
                  type="button"
                  class="sub-agent-expand-btn"
                  :aria-expanded="isSubAgentExpanded(group, index)"
                  :aria-label="isSubAgentExpanded(group, index) ? '收起' : '展开'"
                  @click.stop="toggleSubAgentExpand(group, index)"
                >
                  <svg
                    class="sub-agent-expand-icon"
                    :class="{ 'sub-agent-expand-icon--up': isSubAgentExpanded(group, index) }"
                    viewBox="0 0 16 16"
                    width="14"
                    height="14"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="1.8"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                    aria-hidden="true"
                  >
                    <path d="M4 6l4 4 4-4" />
                  </svg>
                </button>
              </footer>
            </article>
          </div>
          <div v-else class="preview-empty">
            <p class="preview-empty-text">预览窗口</p>
          </div>
        </template>

        <!-- 网页 Tab -->
        <template v-else-if="activeTab === 'web'">
          <div v-if="selectedWebUrl" class="preview-pane web-preview-pane">
            <div class="preview-header web-preview-header">
              <h4 class="preview-header-title web-preview-title" :title="selectedWebUrl">{{ extractDomain(selectedWebUrl) }}</h4>
              <div class="header-actions">
                <button type="button" class="edit-button" @click="openWebInNewTab">在新标签页打开</button>
              </div>
            </div>
            <div class="preview-content web-preview-content">
              <div v-if="webIframeBlocked" class="web-blocked-notice">
                <p>该网页无法嵌入预览，已为你在新标签页打开。</p>
                <button type="button" class="edit-button" @click="openWebInNewTab">重新打开</button>
              </div>
              <template v-else>
                <div v-if="webIframeLoading" class="web-preview-loading" role="status" aria-live="polite">
                  <div class="web-preview-spinner" aria-hidden="true"></div>
                  <p class="web-preview-loading-text">网页加载中…</p>
                </div>
                <iframe
                  :key="selectedWebUrl"
                  :src="selectedWebUrl"
                  class="web-iframe"
                  frameborder="0"
                  sandbox="allow-scripts allow-same-origin allow-forms allow-popups"
                  referrerpolicy="no-referrer-when-downgrade"
                  @load="onWebIframeLoad"
                  @error="onWebIframeError"
                ></iframe>
              </template>
            </div>
          </div>
          <div v-else class="preview-empty">
            <p class="preview-empty-text">预览窗口</p>
          </div>
        </template>
        </div>

        <!-- 浮动文件列表（overlay 于预览区右侧） -->
        <aside
          class="file-list-float"
          :class="{ 'file-list-float--collapsed': !isFileListExpanded }"
          aria-label="文件列表"
        >
          <button
            v-if="!isFileListExpanded"
            type="button"
            class="file-list-rail"
            aria-label="展开文件列表"
            @click="isFileListExpanded = true"
          >
            <span class="file-list-rail-icon" aria-hidden="true">
              <svg viewBox="0 0 16 16" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                <path d="M2 4.5A1.5 1.5 0 0 1 3.5 3h3l1.2 1.5H12.5A1.5 1.5 0 0 1 14 6v6.5A1.5 1.5 0 0 1 12.5 14h-9A1.5 1.5 0 0 1 2 12.5V4.5z" />
              </svg>
            </span>
          </button>

          <template v-else>
            <header class="file-list-float-head">
              <button
                type="button"
                class="file-list-float-collapse"
                aria-label="收起文件列表"
                @click="isFileListExpanded = false"
              >
                <svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                  <path d="M6 4l4 4-4 4" />
                </svg>
              </button>
              <div class="file-list-float-heading">
                <span class="file-list-float-title">文件</span>
                <span class="file-list-float-count">{{ floatFileCount }}</span>
              </div>
              <button
                type="button"
                class="file-list-float-refresh"
                aria-label="刷新文件列表"
                @click="fetchFiles"
              >
                <svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                  <path d="M2.5 8a5.5 5.5 0 0 1 9.3-3.9" />
                  <path d="M13.5 8A5.5 5.5 0 0 1 4.2 11.9" />
                  <path d="M11.8 2.5V5h-2.3" />
                  <path d="M4.2 13.5V11h2.3" />
                </svg>
              </button>
            </header>

            <div class="file-list-float-body">
              <ul v-if="visibleFileNodes.length > 0" class="fl-tree" role="tree">
                <li
                  v-for="node in visibleFileNodes"
                  :key="node.key"
                  role="treeitem"
                  class="fl-tree-row"
                >
                  <button
                    type="button"
                    class="fl-tree-item"
                    :class="{
                      'fl-tree-item--folder': node.type === 'folder',
                      'fl-tree-item--selected': node.type === 'file' && node.path === selectedFileNormalized,
                    }"
                    :style="{ paddingLeft: `${10 + node.level * 14}px` }"
                    @click="handleTreeNodeClick(node)"
                  >
                    <span
                      class="fl-tree-leading"
                      :class="{ 'fl-tree-leading--folder': node.type === 'folder' }"
                      aria-hidden="true"
                    >
                      <svg v-if="node.type === 'folder'" viewBox="0 0 16 16" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M2 4.5A1.5 1.5 0 0 1 3.5 3h3l1.2 1.5H12.5A1.5 1.5 0 0 1 14 6v6.5A1.5 1.5 0 0 1 12.5 14h-9A1.5 1.5 0 0 1 2 12.5V4.5z" />
                      </svg>
                      <svg v-else viewBox="0 0 16 16" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M4 2.5h5l2.5 2.5V13a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V3.5a1 1 0 0 1 1-1z" />
                        <path d="M9 2.5V6H12.5" />
                      </svg>
                    </span>
                    <span class="fl-tree-name" :title="node.name">{{ node.name }}</span>
                    <span
                      v-if="node.type === 'folder'"
                      class="fl-tree-folder-chevron"
                      aria-hidden="true"
                    >{{ isFolderExpanded(node.path) ? '▾' : '▸' }}</span>
                  </button>
                </li>
              </ul>
              <div v-else class="fl-tree-empty">
                <p class="fl-tree-empty-title">暂无文件</p>
              </div>
            </div>
          </template>
        </aside>
      </div>
    </div>

    <!-- 全屏文件库弹窗 -->
    <div v-if="showFileLibrary" class="file-library-full-panel">
      <header class="full-panel-header">
        <span class="full-panel-title">文件编辑</span>
        <button type="button" class="full-panel-close" aria-label="关闭" @click="closeEditPanel">
          <svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true">
            <path d="M4 4l8 8M12 4l-8 8" />
          </svg>
        </button>
      </header>
      <div class="full-panel-body">
        <aside
          class="full-panel-sidebar"
          :class="{ 'full-panel-sidebar--collapsed': !isFullPanelFileListExpanded }"
          aria-label="文件列表"
        >
          <button
            v-if="!isFullPanelFileListExpanded"
            type="button"
            class="file-list-rail full-panel-rail"
            aria-label="展开文件列表"
            @click="isFullPanelFileListExpanded = true"
          >
            <span class="file-list-rail-icon" aria-hidden="true">
              <svg viewBox="0 0 16 16" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                <path d="M2 4.5A1.5 1.5 0 0 1 3.5 3h3l1.2 1.5H12.5A1.5 1.5 0 0 1 14 6v6.5A1.5 1.5 0 0 1 12.5 14h-9A1.5 1.5 0 0 1 2 12.5V4.5z" />
              </svg>
            </span>
          </button>

          <template v-else>
            <header class="file-list-float-head">
              <button
                type="button"
                class="file-list-float-collapse"
                aria-label="收起文件列表"
                @click="isFullPanelFileListExpanded = false"
              >
                <svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                  <path d="M6 4l4 4-4 4" />
                </svg>
              </button>
              <div class="file-list-float-heading">
                <span class="file-list-float-title">文件</span>
                <span class="file-list-float-count">{{ floatFileCount }}</span>
              </div>
              <button
                type="button"
                class="file-list-float-refresh"
                aria-label="刷新文件列表"
                @click="fetchFiles"
              >
                <svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                  <path d="M2.5 8a5.5 5.5 0 0 1 9.3-3.9" />
                  <path d="M13.5 8A5.5 5.5 0 0 1 4.2 11.9" />
                  <path d="M11.8 2.5V5h-2.3" />
                  <path d="M4.2 13.5V11h2.3" />
                </svg>
              </button>
            </header>

            <div class="file-list-float-body">
              <ul v-if="visibleFileNodes.length > 0" class="fl-tree" role="tree">
                <li
                  v-for="node in visibleFileNodes"
                  :key="node.key"
                  role="treeitem"
                  class="fl-tree-row"
                >
                  <button
                    type="button"
                    class="fl-tree-item"
                    :class="{
                      'fl-tree-item--folder': node.type === 'folder',
                      'fl-tree-item--selected': node.type === 'file' && node.path === selectedFileNormalized,
                    }"
                    :style="{ paddingLeft: `${10 + node.level * 14}px` }"
                    @click="handleTreeNodeClick(node)"
                  >
                    <span
                      class="fl-tree-leading"
                      :class="{ 'fl-tree-leading--folder': node.type === 'folder' }"
                      aria-hidden="true"
                    >
                      <svg v-if="node.type === 'folder'" viewBox="0 0 16 16" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M2 4.5A1.5 1.5 0 0 1 3.5 3h3l1.2 1.5H12.5A1.5 1.5 0 0 1 14 6v6.5A1.5 1.5 0 0 1 12.5 14h-9A1.5 1.5 0 0 1 2 12.5V4.5z" />
                      </svg>
                      <svg v-else viewBox="0 0 16 16" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M4 2.5h5l2.5 2.5V13a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V3.5a1 1 0 0 1 1-1z" />
                        <path d="M9 2.5V6H12.5" />
                      </svg>
                    </span>
                    <span class="fl-tree-name" :title="node.name">{{ node.name }}</span>
                    <span
                      v-if="node.type === 'folder'"
                      class="fl-tree-folder-chevron"
                      aria-hidden="true"
                    >{{ isFolderExpanded(node.path) ? '▾' : '▸' }}</span>
                  </button>
                </li>
              </ul>
              <div v-else class="fl-tree-empty">
                <p class="fl-tree-empty-title">暂无文件</p>
              </div>
            </div>
          </template>
        </aside>

        <main class="full-panel-main">
          <div v-if="selectedFile" class="preview-pane">
            <div class="preview-header">
              <h4 class="preview-header-title" :title="selectedFile">{{ selectedFile }}</h4>
              <div class="header-actions">
                <button v-if="isEditableFile && !isEditing" class="edit-button" @click="startEditing">编辑</button>
                <div
                  v-if="isEditing && isMarkdownFile"
                  class="edit-mode-switch"
                  role="tablist"
                  aria-label="编辑模式切换"
                  :data-active="editMode"
                >
                  <span class="edit-mode-thumb" aria-hidden="true"></span>
                  <button
                    type="button"
                    role="tab"
                    class="edit-mode-option"
                    :class="{ 'edit-mode-option--active': editMode === 'markdown' }"
                    :aria-selected="editMode === 'markdown'"
                    @click="switchEditMode('markdown')"
                  >Markdown</button>
                  <button
                    type="button"
                    role="tab"
                    class="edit-mode-option"
                    :class="{ 'edit-mode-option--active': editMode === 'source' }"
                    :aria-selected="editMode === 'source'"
                    @click="switchEditMode('source')"
                  >源码</button>
                </div>
                <button v-if="isEditing" class="save-button" @click="saveFile" :disabled="saving">
                  {{ saving ? '保存中...' : '保存' }}
                </button>
                <button v-if="isEditing" class="cancel-button" @click="() => cancelEditing()">退出编辑</button>
                <div v-if="isHtml && !isEditing" class="export-container">
                  <button class="export-button" @click="toggleExportOptions">导出</button>
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
                <div v-if="editMode === 'markdown' && isMarkdownFile" class="markdown-editor-container">
                  <div id="markdown-editor" class="markdown-editor"></div>
                </div>
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
          <div v-else class="preview-empty">
            <p class="preview-empty-text">预览窗口</p>
          </div>
        </main>
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
import DownloadIcon from '@/assets/images/download_icon.svg?url'
// Import vue-office components (user needs to install @vue-office/docx, @vue-office/excel, @vue-office/pdf, etc.)
import VueOfficeDocx from '@vue-office/docx'
import '@vue-office/docx/lib/index.css'
import VueOfficeExcel from '@vue-office/excel'
import '@vue-office/excel/lib/index.css'
import VueOfficePdf from '@vue-office/pdf'
// For PPT, there might not be a direct vue-office, so handle as needed

import VueOfficePptx from '@vue-office/pptx'
import mammoth from 'mammoth';
import ToolCallsBlock from './ToolCallsBlock.vue'
import { buildToolCallItems } from '../utils/toolCallDisplay'

// Toast UI Editor imports
import Editor from '@toast-ui/editor'
import '@toast-ui/editor/dist/toastui-editor.css'
import codeSyntaxHighlight from '@toast-ui/editor-plugin-code-syntax-highlight'
import 'highlight.js/styles/github.css'

const props = defineProps<{ 
  toolMessages: AgentMessage[]
  fileMessages: AgentMessage[]
  highlightedId: string | null
  scrollToId: string | null
  toggleTrigger: number
  conversationId: string
  webOpenTrigger?: { url: string; nonce: number } | null
  fileOpenTrigger?: { filePath: string; nonce: number } | null
  isGenerating?: boolean
}>()

type PreviewTab = 'files' | 'agents' | 'web'

const SUB_AGENT_TOOL_NAMES = new Set(['call_sub_agent', 'soulprout_kb_agent'])

function isSubAgentToolName(name: string): boolean {
  return SUB_AGENT_TOOL_NAMES.has(name)
}

const SUB_AGENT_SKIP_TYPES = new Set(['get_agents', 'agent_for_frontend', 'agent_session_id'])

function resolveSubAgentCallId(msg: AgentMessage): string | null {
  if (msg.type === 'get_agents') {
    const tc = msg.tool_calls?.[0]
    if (tc?.id && isSubAgentToolName(tc.function?.name || '')) return tc.id
    return null
  }
  if (!msg.tool_call_id) return null
  if (
    msg.type === 'agent_for_frontend' ||
    msg.type === 'text' ||
    msg.type === 'reasoner_content' ||
    msg.type === 'agent_session_id' ||
    (msg.type === 'get_tools' && msg.role === 'agent') ||
    (msg.role === 'tool' && msg.type === 'agent')
  ) {
    return msg.tool_call_id
  }
  return null
}

function sortSubAgentMessages(messages: AgentMessage[]): AgentMessage[] {
  return [...messages]
    .filter((m) => !SUB_AGENT_SKIP_TYPES.has(m.type))
    .sort((a, b) => {
      const pick = (t: unknown) => (typeof t === 'number' ? t : Date.parse(String(t)) || 0)
      return pick(a.created_at) - pick(b.created_at)
    })
}

const groupedSubAgentMessages = computed(() => {
  const map = new Map<string, { tool_call_id: string; messages: AgentMessage[] }>()
  for (const msg of props.toolMessages) {
    const callId = resolveSubAgentCallId(msg)
    if (!callId) continue
    if (!map.has(callId)) {
      map.set(callId, { tool_call_id: callId, messages: [] })
    }
    const group = map.get(callId)!
    if (msg.type === 'text' || msg.type === 'reasoner_content') {
      const last = group.messages[group.messages.length - 1]
      if (last?.type === msg.type && last.role !== 'tool') {
        last.content = (last.content || '') + (msg.content || '')
      } else {
        group.messages.push({ ...msg, content: msg.content || '' })
      }
    } else {
      group.messages.push(msg)
    }
  }
  return [...map.values()]
    .filter((g) => g.messages.some((m) =>
      m.type === 'agent_for_frontend' ||
      m.type === 'text' ||
      m.type === 'get_tools' ||
      (m.role === 'tool' && m.type === 'agent')
    ))
    .sort((a, b) => {
      const pickTime = (g: { messages: AgentMessage[] }) => {
        const t = g.messages[0]?.created_at
        return typeof t === 'number' ? t : Date.parse(String(t)) || 0
      }
      return pickTime(a) - pickTime(b)
    })
})

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
            role: msg.role || 'agent',
            content: msg.content || '',
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
            role: msg.role || 'agent',
            content: msg.content || '',
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
  // web_search 已在 ChatWindow 主对话内联展示，侧栏不再展示
  return groups
    .map((g) => ({
      ...g,
      messages: g.messages.filter((m) => m.type !== 'plan')
    }))
    .filter((g) => g.messages.length > 0)
    .filter((g) => {
      // 过滤掉 web_search 工具组
      for (const msg of g.messages) {
        if (msg.tool_calls && msg.tool_calls.length > 0) {
          if (msg.tool_calls[0].function?.name === 'web_search') return false
        }
      }
      return true
    })
})

const SESSION_ID_PREFIX = /^当前子智能体session_id=\w+\n?/

function getSubAgentName(group: { messages: AgentMessage[] }): string {
  for (const msg of group.messages) {
    if (msg.type === 'agent_for_frontend' && msg.content) return msg.content
  }
  const args = getGroupToolArgs(group)
  return args.name ? String(args.name) : '子智能体'
}

const subAgentBodyRefs = ref<Record<string, HTMLElement | null>>({})
const subAgentExpanded = ref<Record<string, boolean>>({})

function getSubAgentStateKey(group: { tool_call_id: string }, index: number): string {
  return group.tool_call_id ? String(group.tool_call_id) : `sub-agent-${index}`
}

function setSubAgentBodyRef(key: string, el: HTMLElement | null) {
  if (el) {
    subAgentBodyRefs.value[key] = el
  } else {
    const next = { ...subAgentBodyRefs.value }
    delete next[key]
    subAgentBodyRefs.value = next
  }
}

function isSubAgentExpanded(group: { tool_call_id: string }, index: number): boolean {
  return !!subAgentExpanded.value[getSubAgentStateKey(group, index)]
}

function toggleSubAgentExpand(group: { tool_call_id: string }, index: number) {
  const key = getSubAgentStateKey(group, index)
  subAgentExpanded.value = {
    ...subAgentExpanded.value,
    [key]: !subAgentExpanded.value[key],
  }
}

function isSubAgentStreaming(groupIndex: number): boolean {
  if (!props.isGenerating) return false
  return groupIndex === groupedSubAgentMessages.value.length - 1
}

function scrollSubAgentBodiesToTail() {
  nextTick(() => {
    for (const [key, el] of Object.entries(subAgentBodyRefs.value)) {
      if (el && !subAgentExpanded.value[key]) {
        el.scrollTop = el.scrollHeight
      }
    }
  })
}

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
const toolRefs = ref<HTMLElement[]>([])
const agentMessagesContainer = ref<HTMLElement | null>(null)
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

const floatFileCount = computed(() =>
  visibleFileNodes.value.filter((n) => n.type === 'file').length,
)

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

  activeTab.value = 'files'
  const rawPath = normalizedFilePathMap.value.get(node.path) || node.path
  await fetchFileContent(rawPath)
}

function resolveFilePathForPreview(filePath: string): string {
  const normalized = normalizeFilePath(filePath)
  if (!normalized) return filePath

  const fromMap = normalizedFilePathMap.value.get(normalized)
  if (fromMap) return fromMap

  const baseName = normalized.split('/').pop()
  for (const rawPath of files.value) {
    const candidate = normalizeFilePath(rawPath)
    if (candidate === normalized) return rawPath
    if (baseName && candidate.split('/').pop() === baseName) return rawPath
  }

  return normalized
}

function expandFoldersForPath(filePath: string) {
  const normalized = normalizeFilePath(filePath)
  const segments = normalized.split('/').filter(Boolean)
  if (segments.length <= 1) return

  const next = new Set(expandedFolders.value)
  let current = ''
  for (let i = 0; i < segments.length - 1; i++) {
    current = current ? `${current}/${segments[i]}` : segments[i]
    next.add(current)
  }
  expandedFolders.value = next
}

async function ensureFilesLoaded() {
  if (files.value.length || !props.conversationId) return

  try {
    const response = await axios.get(`/api/files?conversation_id=${props.conversationId}`)
    if (Array.isArray(response.data)) {
      files.value = response.data
    } else if (response.data && Array.isArray(response.data.files)) {
      files.value = response.data.files
    } else if (response.data && Array.isArray(response.data.data)) {
      files.value = response.data.data
    }
  } catch {
    // 预览仍可通过 file_content 接口尝试加载
  }
}

async function openFilePreview(filePath: string) {
  if (!filePath || !props.conversationId) return

  activeTab.value = 'files'
  isFileListExpanded.value = true
  await ensureFilesLoaded()

  const resolved = resolveFilePathForPreview(filePath)
  const resolvedNormalized = normalizeFilePath(resolved)
  if (resolvedNormalized && !files.value.some((f) => normalizeFilePath(f) === resolvedNormalized)) {
    files.value.push(resolved)
  }
  expandFoldersForPath(resolved)
  await nextTick()
  await fetchFileContent(resolved)
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
  if (!props.conversationId) {
    files.value = []
    return
  }

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

// ─── 工具卡片辅助函数 ──────────────────────────────────────────────────

/** 从 group 中提取第一个 tool_call 的 parsed arguments */
function getGroupToolArgs(group: any): Record<string, any> {
  for (const msg of group.messages) {
    if (msg.tool_calls && msg.tool_calls.length > 0) {
      return parseArguments(msg.tool_calls[0].function?.arguments || '{}')
    }
  }
  return {}
}

/** 从 group 中提取工具调用结果（role=tool 消息） */
function getGroupToolResult(group: any): string {
  for (const msg of group.messages) {
    if (msg.role === 'tool' && msg.content != null) {
      return msg.content
    }
  }
  return ''
}

/** 提取域名 */
function extractDomain(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, '')
  } catch {
    return url
  }
}

/** 解析 web_search 工具结果为数组 */
function parseWebSearchResults(group: any): { title: string; link: string; content: string; media: string; publish_date: string }[] {
  const raw = getGroupToolResult(group)
  if (!raw) return []
  try {
    const parsed = JSON.parse(raw)
    if (Array.isArray(parsed)) return parsed
    return []
  } catch {
    return []
  }
}

/** 获取 web_search 结果数量 */
function getWebSearchResultCount(group: any): number {
  return parseWebSearchResults(group).length
}

// checkOverflow（仅保留 copy 监听器绑定）
const checkOverflow = () => {
  nextTick(() => {
    attachCopyListeners()
  })
}

// 防抖版 checkOverflow（已移除自动展开逻辑）
let checkOverflowTimer: ReturnType<typeof setTimeout> | null = null
const debouncedCheckOverflow = () => {
  if (checkOverflowTimer) clearTimeout(checkOverflowTimer)
  checkOverflowTimer = setTimeout(() => {
    checkOverflowTimer = null
    attachCopyListeners()
  }, 80)
}

// watch
const autoSwitchedSubAgents = ref(new Set<string>())

watch(groupedSubAgentMessages, (newGroups) => {
  newGroups.forEach((group) => {
    const id = group.tool_call_id
    if (!autoSwitchedSubAgents.value.has(id)) {
      autoSwitchedSubAgents.value.add(id)
      activeTab.value = 'agents'
    }
  })
  nextTick(() => {
    scrollAgentMessagesToBottom()
    scrollSubAgentBodiesToTail()
  })
}, { deep: true })

watch(() => [props.scrollToId, props.toggleTrigger], () => {
  if (props.scrollToId) {
    const index = groupedSubAgentMessages.value.findIndex(g => g.tool_call_id === props.scrollToId)
    if (index === -1) return
    activeTab.value = 'agents'
    const ref = toolRefs.value[index]
    if (ref) {
      ref.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
    }
  }
})

// 监听子智能体消息变化，自动滚动到底部
watch(() => props.toolMessages, () => {
  nextTick(() => {
    scrollAgentMessagesToBottom()
    scrollSubAgentBodiesToTail()
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
  fetchFiles()
  window.addEventListener('beforeunload', handleBeforeUnload)
})

// 清理事件监听器
onUnmounted(() => {
  window.removeEventListener('beforeunload', handleBeforeUnload)
  clearWebIframeTimer()
})

// 添加滚动到底部的方法
const scrollAgentMessagesToBottom = () => {
  if (isAutoScroll.value && agentMessagesContainer.value) {
    nextTick(() => {
      if (agentMessagesContainer.value) {
        agentMessagesContainer.value.scrollTop = agentMessagesContainer.value.scrollHeight
      }
    })
  }
}

// 添加处理用户手动滚动的方法
const handleScroll = () => {
  if (agentMessagesContainer.value) {
    const { scrollTop, scrollHeight, clientHeight } = agentMessagesContainer.value
    if (scrollHeight - scrollTop - clientHeight < 50) {
      isAutoScroll.value = true
    } else {
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
const activeTab = ref<PreviewTab>('files')

// 网页预览
const selectedWebUrl = ref<string | null>(null)
const webIframeBlocked = ref(false)
const webIframeLoading = ref(false)
let webIframeLoadTimer: ReturnType<typeof setTimeout> | null = null

function openWebPreview(url: string) {
  if (!url) return
  webIframeLoading.value = true
  selectedWebUrl.value = url
  webIframeBlocked.value = false
  activeTab.value = 'web'
}

function openWebInNewTab() {
  if (selectedWebUrl.value) {
    window.open(selectedWebUrl.value, '_blank', 'noopener,noreferrer')
  }
}

function clearWebIframeTimer() {
  if (webIframeLoadTimer) {
    clearTimeout(webIframeLoadTimer)
    webIframeLoadTimer = null
  }
}

function handleWebIframeBlocked() {
  webIframeLoading.value = false
  webIframeBlocked.value = true
  openWebInNewTab()
}

function onWebIframeLoad(event: Event) {
  clearWebIframeTimer()
  webIframeLoading.value = false
  const iframe = event.target as HTMLIFrameElement | null
  if (!iframe) return

  webIframeLoadTimer = setTimeout(() => {
    try {
      const doc = iframe.contentDocument
      if (doc && doc.body && doc.body.innerHTML.trim() === '') {
        handleWebIframeBlocked()
      }
    } catch {
      // 跨域页面无法读取 document，视为正常加载
    }
  }, 2500)
}

function onWebIframeError() {
  clearWebIframeTimer()
  webIframeLoading.value = false
  handleWebIframeBlocked()
}

watch(
  () => props.webOpenTrigger,
  (trigger) => {
    if (trigger?.url) {
      openWebPreview(trigger.url)
    }
  },
  { deep: true, immediate: true },
)

watch(
  () => props.fileOpenTrigger,
  (trigger) => {
    if (trigger?.filePath) {
      void openFilePreview(trigger.filePath)
    }
  },
  { deep: true, immediate: true },
)

// 文件列表展开/收缩状态（默认展开）
const isFileListExpanded = ref(true)
const isFullPanelFileListExpanded = ref(true)

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
    selectedWebUrl.value = null
    webIframeBlocked.value = false
    webIframeLoading.value = false
    autoSwitchedSubAgents.value = new Set()
    clearWebIframeTimer()
  }
  
  fetchFiles()
})

// 监听 activeTab 变化
watch(activeTab, (newTab) => {
  if (newTab === 'files') {
    fetchFiles()
  } else if (newTab === 'agents') {
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
    // read: 第一次识别到 file_path 时定位到预览文件
    const readFilePath = jsonTable.file_path || jsonTable.file_name
    if (readFilePath) {
      const fileName = readFilePath
      
      // 确保文件在列表中
      if (!files.value.includes(fileName)) {
        files.value.push(fileName)
      }
      
      // 第一次识别到 file_path，定位到预览文件
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
    const fileName = jsonTable.file_path || jsonTable.file_name
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
      
      // 第一次识别到 file_path，定位到预览文件
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
    const fileName = jsonTable.file_path || jsonTable.file_name
    
    // 如果有 file_path，初始化流式状态并定位
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
        
        // 第一次识别到 file_path，定位到预览文件
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
  isFullPanelFileListExpanded.value = true
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
  background-color: rgb(242, 242, 242);
  padding: 0;
  box-sizing: border-box;
  overflow: hidden;
  position: relative;
}

/* 紧凑型 Tab 切换（居中） */
.preview-tab-bar {
  flex-shrink: 0;
  display: flex;
  justify-content: center;
  align-items: center;
  padding: 8px 12px 10px;
  border-bottom: 1px solid rgba(0, 0, 0, 0.05);
  background-color: rgb(242, 242, 242);
}

.preview-tab-switch {
  position: relative;
  display: inline-flex;
  width: auto;
  padding: 3px;
  background-color: rgba(0, 0, 0, 0.05);
  border: 1px solid rgba(0, 0, 0, 0.04);
  border-radius: 10px;
  box-sizing: border-box;
}

.preview-tab-thumb {
  position: absolute;
  top: 3px;
  left: 3px;
  width: calc((100% - 6px) / 3);
  height: calc(100% - 6px);
  background-color: rgb(33, 33, 33);
  border-radius: 7px;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.16);
  transition: transform 0.28s cubic-bezier(0.4, 0, 0.2, 1);
  pointer-events: none;
  z-index: 0;
}

.preview-tab-switch[data-active="agents"] .preview-tab-thumb {
  transform: translateX(100%);
}

.preview-tab-switch[data-active="web"] .preview-tab-thumb {
  transform: translateX(200%);
}

.preview-tab-option {
  position: relative;
  z-index: 1;
  flex: none;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  height: 28px;
  min-width: 68px;
  padding: 0 14px;
  border: none;
  border-radius: 7px;
  background-color: transparent;
  color: rgb(110, 110, 110);
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.15px;
  cursor: pointer;
  outline: none;
  transition: color 0.22s ease, transform 0.16s ease;
  font-family: inherit;
  white-space: nowrap;
}

.preview-tab-option:hover:not(.preview-tab-option--active) {
  color: rgb(33, 33, 33);
}

.preview-tab-option--active,
.preview-tab-option--active:hover {
  color: #fff;
}

.preview-tab-option:focus-visible {
  outline: 2px solid rgba(0, 0, 0, 0.25);
  outline-offset: 2px;
}

/* 预览主布局 */
.preview-viewport-body {
  flex: 1;
  min-height: 0;
  display: flex;
  overflow: hidden;
}

.preview-main {
  flex: 1;
  min-width: 0;
  width: 100%;
  position: relative;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background-color: rgb(242, 242, 242);
}

.preview-content-area {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* 浮动文件列表 */
.file-list-float {
  position: absolute;
  top: 50%;
  right: 0;
  z-index: 20;
  height: 50%;
  width: 228px;
  transform: translateY(-50%);
  display: flex;
  flex-direction: column;
  background: rgba(255, 255, 255, 0.98);
  border: 1px solid rgba(0, 0, 0, 0.07);
  border-right: none;
  border-radius: 14px 0 0 14px;
  box-shadow: -8px 0 28px rgba(0, 0, 0, 0.06);
  overflow: hidden;
  transition: width 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.file-list-float--collapsed {
  width: 40px;
  height: 40px;
  min-height: 0;
  max-height: none;
}

/* 收起态：仅文件库图标 */
.file-list-rail {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
  padding: 0;
  border: none;
  background: rgba(255, 255, 255, 0.98);
  cursor: pointer;
  font-family: inherit;
  transition: background 0.2s ease;
}

.file-list-rail:hover {
  background: rgba(255, 255, 255, 1);
}

.file-list-rail-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: rgb(110, 110, 110);
  transition: color 0.2s ease;
}

.file-list-rail:hover .file-list-rail-icon {
  color: rgb(33, 33, 33);
}

/* 展开态：顶栏 */
.file-list-float-head {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 10px 10px 9px;
  border-bottom: 1px solid rgba(0, 0, 0, 0.06);
  background: rgb(242, 242, 242);
}

.file-list-float-collapse,
.file-list-float-refresh {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  padding: 0;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: rgb(110, 110, 110);
  cursor: pointer;
  flex-shrink: 0;
  transition: background 0.18s ease, color 0.18s ease;
}

.file-list-float-collapse:hover,
.file-list-float-refresh:hover {
  background: rgba(0, 0, 0, 0.06);
  color: rgb(33, 33, 33);
}

.file-list-float-heading {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: baseline;
  gap: 6px;
}

.file-list-float-title {
  font-size: 13px;
  font-weight: 600;
  color: rgb(61, 61, 61);
  letter-spacing: 0.02em;
}

.file-list-float-count {
  font-size: 11px;
  font-weight: 600;
  color: rgb(130, 130, 130);
  background: rgba(0, 0, 0, 0.05);
  padding: 1px 6px;
  border-radius: 999px;
  line-height: 1.5;
}

.file-list-float-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 6px 6px 8px;
}

.file-list-float-body::-webkit-scrollbar {
  width: 6px;
}

.file-list-float-body::-webkit-scrollbar-thumb {
  background: rgba(0, 0, 0, 0.12);
  border-radius: 3px;
}

.fl-tree {
  list-style: none;
  margin: 0;
  padding: 0;
}

.fl-tree-row {
  margin: 0;
  padding: 0;
}

.fl-tree-item {
  display: flex;
  align-items: center;
  gap: 7px;
  width: 100%;
  min-height: 32px;
  padding: 6px 8px 6px 10px;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: rgb(61, 61, 61);
  font-size: 12.5px;
  font-weight: 500;
  line-height: 1.35;
  text-align: left;
  cursor: pointer;
  font-family: inherit;
  transition: background 0.16s ease, color 0.16s ease;
}

.fl-tree-item:hover {
  background: rgba(0, 0, 0, 0.04);
}

.fl-tree-item--selected {
  background: rgba(0, 0, 0, 0.07);
  color: rgb(33, 33, 33);
  font-weight: 600;
}

.fl-tree-item--folder {
  color: rgb(80, 80, 80);
  font-weight: 600;
}

.fl-tree-leading {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  width: 16px;
  color: rgb(140, 140, 140);
}

.fl-tree-item--selected .fl-tree-leading {
  color: rgb(61, 61, 61);
}

.fl-tree-item--folder .fl-tree-leading {
  color: rgb(110, 110, 110);
}

.fl-tree-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.fl-tree-folder-chevron {
  flex-shrink: 0;
  font-size: 9px;
  color: rgb(160, 160, 160);
  line-height: 1;
}

.fl-tree-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 4px;
  height: 100%;
  min-height: 120px;
  padding: 16px 12px;
  text-align: center;
}

.fl-tree-empty-title {
  margin: 0;
  font-size: 12.5px;
  font-weight: 600;
  color: rgb(110, 110, 110);
}

.preview-pane {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.preview-empty {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 0;
}

.preview-empty-text {
  margin: 0;
  color: rgb(150, 150, 150);
  font-size: 14px;
  font-weight: 500;
  letter-spacing: 0.02em;
}

.preview-header-title {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: rgb(61, 61, 61);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
  min-width: 0;
}

.web-preview-title {
  font-size: 13px;
}

.web-preview-content {
  padding: 0 !important;
  position: relative;
  flex: 1;
  min-height: 0;
}

.web-preview-loading {
  position: absolute;
  inset: 0;
  z-index: 2;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  background: rgb(242, 242, 242);
}

.web-preview-spinner {
  width: 28px;
  height: 28px;
  border: 2.5px solid rgba(0, 0, 0, 0.08);
  border-top-color: rgb(110, 110, 110);
  border-radius: 50%;
  animation: web-preview-spin 0.75s linear infinite;
}

@keyframes web-preview-spin {
  to {
    transform: rotate(360deg);
  }
}

.web-preview-loading-text {
  margin: 0;
  font-size: 13px;
  color: rgb(110, 110, 110);
}

.web-iframe {
  width: 100%;
  height: 100%;
  border: none;
  background: #fff;
}

.web-blocked-notice {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  height: 100%;
  padding: 24px;
  text-align: center;
  color: rgb(110, 110, 110);
  font-size: 13px;
}

.agent-messages {
  flex: 1;
  overflow-y: auto;
  padding: 16px 18px 20px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.agent-messages::-webkit-scrollbar {
  width: 8px;
}

.agent-messages::-webkit-scrollbar-thumb {
  background-color: rgba(0, 0, 0, 0.12);
  border-radius: 4px;
}

.agent-messages::-webkit-scrollbar-track {
  background-color: transparent;
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

/* 全屏文件编辑弹窗 */
.file-library-full-panel {
  position: fixed;
  top: 8%;
  left: 8%;
  width: 84vw;
  height: 84vh;
  background: rgb(242, 242, 242);
  border-radius: 14px;
  box-shadow: 0 24px 64px rgba(0, 0, 0, 0.14), 0 8px 24px rgba(0, 0, 0, 0.08);
  z-index: 100;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border: 1px solid rgba(0, 0, 0, 0.06);
  animation: panelFadeIn 0.28s cubic-bezier(0.4, 0, 0.2, 1);
}

@keyframes panelFadeIn {
  from {
    opacity: 0;
    transform: scale(0.98) translateY(-8px);
  }
  to {
    opacity: 1;
    transform: scale(1) translateY(0);
  }
}

.full-panel-header {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 16px;
  border-bottom: 1px solid rgba(0, 0, 0, 0.06);
  background: rgb(242, 242, 242);
}

.full-panel-title {
  font-size: 14px;
  font-weight: 600;
  color: rgb(61, 61, 61);
  letter-spacing: 0.01em;
}

.full-panel-close {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  padding: 0;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: rgb(110, 110, 110);
  cursor: pointer;
  transition: background 0.18s ease, color 0.18s ease;
}

.full-panel-close:hover {
  background: rgba(0, 0, 0, 0.06);
  color: rgb(33, 33, 33);
}

.full-panel-body {
  flex: 1;
  min-height: 0;
  display: flex;
  overflow: hidden;
}

.full-panel-sidebar {
  flex-shrink: 0;
  width: 228px;
  display: flex;
  flex-direction: column;
  background: rgba(255, 255, 255, 0.98);
  border-right: 1px solid rgba(0, 0, 0, 0.07);
  overflow: hidden;
  transition: width 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.full-panel-sidebar--collapsed {
  width: 40px;
}

.full-panel-rail {
  height: 100%;
}

.full-panel-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: rgb(242, 242, 242);
}

.file-library-full-panel .preview-header {
  position: sticky;
  top: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 16px;
  background: rgb(242, 242, 242);
  border-bottom: 1px solid rgba(0, 0, 0, 0.06);
  box-shadow: none;
  min-height: auto;
  margin-bottom: 0;
  z-index: 5;
}

.file-library-full-panel .preview-header::after {
  display: none;
}

.file-library-full-panel .preview-content {
  flex: 1;
  min-height: 0;
  padding: 16px 20px 20px;
  background: rgb(242, 242, 242);
  box-shadow: none;
  overflow-y: auto;
}

.file-library-full-panel .edit-content,
.file-library-full-panel .markdown-editor-container,
.file-library-full-panel .edit-textarea {
  background: #fff;
  border-radius: 10px;
  border: 1px solid rgba(0, 0, 0, 0.07);
}

.preview-header {
  position: sticky;
  top: 0;
  background: #ffffff;
  padding: 12px 20px;
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
  border: 1px solid rgba(0, 0, 0, 0.07);
  border-radius: 10px;
  margin-bottom: 0;
  background: #fcfcfc;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
  position: relative;
  transition: background-color 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease;
}

.tool-frame:hover {
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06);
  border-color: rgba(0, 0, 0, 0.1);
}

.tool-frame.highlighted {
  border-color: rgba(0, 0, 0, 0.14);
  box-shadow: 0 0 0 2px rgba(0, 0, 0, 0.06);
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

/* 高亮时新卡片内部背景继承高亮色 */
.highlighted .tool-card-header,
.highlighted .web-search-header {
  background: rgba(217, 244, 227, 0.7) !important;
}

.highlighted .tool-result-row {
  background: rgba(217, 244, 227, 0.5);
  border-top-color: rgba(110, 196, 141, 0.2);
}

.highlighted .tool-expanded-body {
  background: rgba(217, 244, 227, 0.3);
  border-top-color: rgba(110, 196, 141, 0.2);
}

.highlighted .web-search-results-panel {
  background: rgba(217, 244, 227, 0.3);
  border-top-color: rgba(110, 196, 141, 0.1);
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
  padding: 12px 18px;
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

.sub-agent-card {
  display: flex;
  flex-direction: column;
  border-radius: 12px;
  border: 1px solid rgba(229, 231, 235, 0.95);
  background: linear-gradient(180deg, #ffffff 0%, #fafafa 100%);
  box-shadow:
    0 1px 2px rgba(17, 24, 39, 0.04),
    0 4px 12px rgba(17, 24, 39, 0.03);
  transition: box-shadow 0.22s ease, border-color 0.22s ease;
}

.sub-agent-card--focused {
  border-color: rgba(107, 114, 128, 0.32);
  box-shadow:
    0 0 0 1px rgba(107, 114, 128, 0.1),
    0 6px 18px rgba(17, 24, 39, 0.07);
}

.sub-agent-card--streaming {
  border-color: rgba(107, 114, 128, 0.24);
}

.sub-agent-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 10px 14px 9px;
  border-bottom: 1px solid rgba(243, 244, 246, 0.95);
  border-radius: 12px 12px 0 0;
}

.sub-agent-identity {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.sub-agent-avatar {
  flex-shrink: 0;
  width: 26px;
  height: 26px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  background: rgba(47, 79, 79, 0.08);
  color: rgba(47, 79, 79, 0.82);
}

.sub-agent-name {
  margin: 0;
  font-size: 13px;
  font-weight: 650;
  letter-spacing: 0.02em;
  color: #1f2937;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.sub-agent-live-badge {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 11px;
  font-weight: 500;
  color: #6b7280;
  padding: 3px 8px;
  border-radius: 999px;
  background: rgba(243, 244, 246, 0.92);
  flex-shrink: 0;
}

.sub-agent-live-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #6b7280;
  animation: sub-agent-pulse 1.4s ease-in-out infinite;
}

@keyframes sub-agent-pulse {
  0%, 100% {
    opacity: 0.4;
    transform: scale(0.85);
  }
  50% {
    opacity: 1;
    transform: scale(1);
  }
}

.sub-agent-body {
  position: relative;
  flex: 0 1 auto;
  min-height: 0;
  max-height: 108px;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 10px 14px 12px;
  scroll-behavior: smooth;
  overscroll-behavior: contain;
}

.sub-agent-body--expanded {
  max-height: min(420px, 45vh);
}

.sub-agent-body:not(.sub-agent-body--expanded)::after {
  content: '';
  position: sticky;
  bottom: 0;
  left: 0;
  right: 0;
  display: block;
  height: 28px;
  margin-top: -28px;
  background: linear-gradient(to bottom, transparent, #fafafa);
  pointer-events: none;
}

.sub-agent-body::-webkit-scrollbar {
  width: 5px;
}

.sub-agent-body::-webkit-scrollbar-thumb {
  background-color: rgba(0, 0, 0, 0.1);
  border-radius: 3px;
}

.sub-agent-footer {
  display: flex;
  flex-shrink: 0;
  justify-content: center;
  padding: 4px 14px 10px;
  border-top: 1px solid rgba(243, 244, 246, 0.95);
  background: linear-gradient(180deg, rgba(250, 250, 250, 0.6) 0%, #fafafa 100%);
  border-radius: 0 0 12px 12px;
  position: relative;
  z-index: 1;
}

.sub-agent-expand-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  padding: 0;
  color: #6b7280;
  background: rgba(243, 244, 246, 0.85);
  border: 1px solid rgba(229, 231, 235, 0.9);
  border-radius: 999px;
  cursor: pointer;
  transition: color 0.18s ease, background 0.18s ease, border-color 0.18s ease;
}

.sub-agent-expand-btn:hover {
  color: #374151;
  background: #ffffff;
  border-color: rgba(209, 213, 219, 0.95);
}

.sub-agent-expand-icon {
  transition: transform 0.2s ease;
}

.sub-agent-expand-icon--up {
  transform: rotate(180deg);
}

.sub-agent-reasoner {
  background: rgba(245, 245, 245, 0.75);
  padding: 8px 10px;
  border-radius: 8px;
  margin-bottom: 8px;
  border-left: 2px solid rgba(47, 79, 79, 0.38);
}

.sub-agent-tools {
  margin: 4px 0 8px;
}

.sub-agent-text {
  margin: 6px 0;
}

:deep(.sub-agent-body .p-content-markdown) {
  font-size: 12px !important;
  color: #4b5563;
  line-height: 1.65;
}

/* ═══════════════════════════════════════════════════════
   新紧凑工具卡片样式
   ═══════════════════════════════════════════════════════ */

.tool-card-new {
  padding: 0;
  overflow: hidden;
  border-radius: 10px;
  border: 1px solid rgba(229, 231, 235, 0.9);
  background: #ffffff;
  box-shadow:
    0 2px 8px rgba(17, 24, 39, 0.05),
    0 1px 3px rgba(17, 24, 39, 0.03);
  transition: box-shadow 0.2s ease, transform 0.2s ease;
}

.tool-card-new:hover {
  box-shadow:
    0 6px 16px rgba(17, 24, 39, 0.08),
    0 2px 6px rgba(17, 24, 39, 0.04);
  transform: translateY(-1px);
}

/* ── 卡片头部（第一行：图标 + 名称 + 参数 + 展开按钮） ── */
.tool-card-header {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 9px 13px 9px 12px;
  cursor: default;
  min-height: 36px;
  background: #ffffff;
}

.web-search-header {
  cursor: pointer;
  background: linear-gradient(135deg, rgba(59, 130, 246, 0.03) 0%, #ffffff 60%);
  transition: background 0.2s ease;
}

.web-search-header:hover {
  background: linear-gradient(135deg, rgba(59, 130, 246, 0.06) 0%, rgba(249, 250, 251, 0.5) 100%);
}

.tool-badge-icon {
  flex-shrink: 0;
  font-size: 13px;
  width: 18px;
  text-align: center;
  line-height: 1;
}

.tool-badge-search {
  filter: none;
}

.tool-name-chip {
  flex-shrink: 0;
  font-size: 12px;
  font-weight: 600;
  color: #374151;
  background: rgba(107, 114, 128, 0.09);
  padding: 2px 8px;
  border-radius: 5px;
  letter-spacing: 0.01em;
  white-space: nowrap;
  max-width: 140px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.tool-name-chip-search {
  background: rgba(59, 130, 246, 0.08);
  color: #1d4ed8;
}

.tool-args-chip {
  flex: 1;
  min-width: 0;
  font-size: 11px;
  color: #9ca3af;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
  letter-spacing: 0.01em;
}

.tool-expand-chevron {
  flex-shrink: 0;
  font-size: 9px;
  color: #d1d5db;
  margin-left: 2px;
  transition: color 0.2s ease;
}

.web-search-header:hover .tool-expand-chevron {
  color: #9ca3af;
}

.tool-expand-btn {
  flex-shrink: 0;
  background: none;
  border: none;
  cursor: pointer;
  font-size: 9px;
  color: #d1d5db;
  padding: 3px 7px;
  border-radius: 4px;
  transition: all 0.2s ease;
  line-height: 1;
}

.tool-expand-btn:hover {
  background: rgba(0, 0, 0, 0.05);
  color: #9ca3af;
}

/* ── 第二行：结果预览（折叠时） ── */
.tool-result-row {
  padding: 5px 13px 8px 38px;
  display: flex;
  align-items: center;
  gap: 8px;
  border-top: 1px solid rgba(0, 0, 0, 0.04);
  background: rgba(249, 250, 251, 0.6);
}

.tool-result-text {
  font-size: 11.5px;
  color: #6b7280;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
  flex: 1;
  min-width: 0;
  line-height: 1.5;
}

.tool-result-empty {
  font-size: 11px;
  color: #d1d5db;
  font-style: italic;
}

.search-count-tag {
  display: inline-flex;
  align-items: center;
  font-size: 11px;
  color: #2563eb;
  font-weight: 500;
  background: rgba(37, 99, 235, 0.07);
  padding: 2px 8px;
  border-radius: 4px;
  white-space: nowrap;
}

/* ── 展开后内容区（普通工具） ── */
.tool-expanded-body {
  padding: 10px 13px 13px;
  border-top: 1px solid rgba(0, 0, 0, 0.06);
  display: flex;
  flex-direction: column;
  gap: 8px;
  background: rgba(249, 250, 251, 0.5);
}

.tool-full-args {
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.tool-arg-full-row {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.tool-arg-key {
  font-size: 10px;
  font-weight: 700;
  color: #9ca3af;
  text-transform: uppercase;
  letter-spacing: 0.07em;
}

.tool-arg-value {
  font-size: 12px;
  color: #374151;
  background: rgba(0, 0, 0, 0.025);
  border: 1px solid rgba(0, 0, 0, 0.06);
  border-radius: 6px;
  padding: 6px 10px;
  margin: 0;
  white-space: pre-wrap;
  word-break: break-all;
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
  max-height: 180px;
  overflow-y: auto;
  line-height: 1.5;
}

.tool-full-result-section {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.tool-result-label {
  font-size: 10px;
  font-weight: 700;
  color: #9ca3af;
  text-transform: uppercase;
  letter-spacing: 0.07em;
}

.tool-result-content {
  font-size: 12px !important;
  color: #4b5563;
  line-height: 1.6;
}

/* ═══════════════════════════════════════════════════════
   web_search 可视化结果样式
   ═══════════════════════════════════════════════════════ */

.web-search-results-panel {
  border-top: 1px solid rgba(59, 130, 246, 0.08);
  display: flex;
  flex-direction: column;
  gap: 0;
  background: rgba(249, 250, 252, 0.6);
  padding: 8px 10px 10px;
  max-height: 460px;
  overflow-y: auto;
}

.web-search-results-panel::-webkit-scrollbar {
  width: 5px;
}

.web-search-results-panel::-webkit-scrollbar-track {
  background: transparent;
}

.web-search-results-panel::-webkit-scrollbar-thumb {
  background: rgba(0, 0, 0, 0.1);
  border-radius: 3px;
}

.search-result-item {
  display: block;
  text-decoration: none;
  padding: 10px 12px;
  border-radius: 8px;
  border: 1px solid transparent;
  transition: all 0.18s ease;
  cursor: pointer;
  background: #ffffff;
  margin-bottom: 5px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
}

.search-result-item:last-child {
  margin-bottom: 0;
}

.search-result-item:hover {
  border-color: rgba(59, 130, 246, 0.2);
  background: rgba(239, 246, 255, 0.6);
  transform: translateY(-1px);
  box-shadow: 0 3px 10px rgba(59, 130, 246, 0.1);
}

.sri-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 3px;
}

.sri-domain {
  font-size: 10.5px;
  color: #059669;
  font-weight: 600;
  letter-spacing: 0.01em;
}

.sri-date {
  font-size: 10px;
  color: #9ca3af;
}

.sri-title {
  font-size: 13px;
  font-weight: 600;
  color: #111827;
  margin-bottom: 4px;
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.search-result-item:hover .sri-title {
  color: #1d4ed8;
}

.sri-snippet {
  font-size: 11.5px;
  color: #6b7280;
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  margin-bottom: 4px;
}

.sri-link {
  font-size: 10.5px;
  color: #60a5fa;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
  opacity: 0.8;
  transition: opacity 0.15s ease;
}

.search-result-item:hover .sri-link {
  opacity: 1;
  color: #2563eb;
}

.search-no-results {
  padding: 20px;
  text-align: center;
  font-size: 12px;
  color: #9ca3af;
  letter-spacing: 0.02em;
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
.edit-button {
  color: rgb(90, 90, 90);
  border: 1px solid rgba(0, 0, 0, 0.08);
  padding: 8px 14px;
  border-radius: 8px;
  cursor: pointer;
  font-size: 12px;
  font-weight: 600;
  margin-right: 6px;
  letter-spacing: 0.02em;
  font-family: inherit;
  transition: background 0.18s ease, color 0.18s ease, border-color 0.18s ease;
  background: rgba(0, 0, 0, 0.04);
  box-shadow: none;
}

.edit-button:hover {
  background: rgba(0, 0, 0, 0.07);
  border-color: rgba(0, 0, 0, 0.1);
  color: rgb(33, 33, 33);
  transform: none;
  box-shadow: none;
}

.edit-button:active {
  background: rgba(0, 0, 0, 0.09);
}

.save-button,
.cancel-button {
  padding: 8px 14px;
  border-radius: 8px;
  cursor: pointer;
  font-size: 12px;
  font-weight: 600;
  margin-right: 6px;
  letter-spacing: 0.02em;
  font-family: inherit;
  transition: background 0.18s ease, color 0.18s ease, border-color 0.18s ease;
  box-shadow: none;
}

.save-button {
  min-width: 72px;
  background: rgb(232, 241, 236);
  color: rgb(62, 98, 78);
  border: 1px solid rgba(62, 98, 78, 0.22);
}

.save-button:hover:not(:disabled) {
  background: rgb(220, 233, 226);
  border-color: rgba(62, 98, 78, 0.32);
  color: rgb(52, 82, 66);
}

.save-button:active:not(:disabled) {
  background: rgb(210, 225, 216);
  border-color: rgba(62, 98, 78, 0.38);
}

.save-button:disabled {
  color: rgb(160, 175, 168);
  border-color: rgba(0, 0, 0, 0.06);
  cursor: not-allowed;
  background: rgb(238, 242, 240);
  opacity: 1;
}

.cancel-button {
  background: rgb(247, 237, 237);
  color: rgb(130, 82, 82);
  border: 1px solid rgba(130, 82, 82, 0.22);
}

.cancel-button:hover {
  background: rgb(241, 226, 226);
  border-color: rgba(130, 82, 82, 0.32);
  color: rgb(110, 68, 68);
}

.cancel-button:active {
  background: rgb(234, 216, 216);
  border-color: rgba(130, 82, 82, 0.38);
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

/* 编辑模式切换（segmented control） */
.edit-mode-switch {
  position: relative;
  display: inline-flex;
  flex-shrink: 0;
  padding: 3px;
  margin-right: 8px;
  background-color: rgba(0, 0, 0, 0.05);
  border: 1px solid rgba(0, 0, 0, 0.04);
  border-radius: 10px;
  box-sizing: border-box;
}

.edit-mode-thumb {
  position: absolute;
  top: 3px;
  left: 3px;
  width: calc((100% - 6px) / 2);
  height: calc(100% - 6px);
  background-color: rgb(33, 33, 33);
  border-radius: 7px;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.16);
  transition: transform 0.28s cubic-bezier(0.4, 0, 0.2, 1);
  pointer-events: none;
  z-index: 0;
}

.edit-mode-switch[data-active="source"] .edit-mode-thumb {
  transform: translateX(100%);
}

.edit-mode-option {
  position: relative;
  z-index: 1;
  flex: 1;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  height: 28px;
  min-width: 72px;
  padding: 0 14px;
  border: none;
  border-radius: 7px;
  background: transparent;
  color: rgb(110, 110, 110);
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.15px;
  cursor: pointer;
  outline: none;
  transition: color 0.22s ease;
  font-family: inherit;
  white-space: nowrap;
}

.edit-mode-option:hover:not(.edit-mode-option--active) {
  color: rgb(33, 33, 33);
}

.edit-mode-option--active,
.edit-mode-option--active:hover {
  color: #fff;
}

.edit-mode-option:focus-visible {
  outline: 2px solid rgba(0, 0, 0, 0.25);
  outline-offset: 2px;
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

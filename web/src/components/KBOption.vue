<!-- KBOption.vue -->
<template>
  <div class="kb-option-overlay" @click="handleOverlayClick">
    <div class="kb-option-container" @click.stop>
      <div class="kb-option-header">
        <div class="header-title-group">
          <p class="header-eyebrow">KNOWLEDGE</p>
          <h2>{{ t('kbOption.title') }}</h2>
        </div>

        <button class="close-btn" @click="$emit('close')" :aria-label="t('common.close')">
          <svg width="11" height="11" viewBox="0 0 10 10" fill="none">
            <path d="M9 1L1 9M1 1L9 9" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/>
          </svg>
        </button>
      </div>

      <!-- 知识库内容 -->
      <div class="kb-content">
        <div class="kb-sidebar">
          <div class="create-kb" @click="startCreate" :title="t('kbOption.createKB')">
            <div class="plus-box">
                <img src="@/assets/images/add_icon.svg" width="18" height="18" />
            </div>
          </div>
          <div v-if="loading" class="loading-state">
            <div class="loading-spinner"></div>
            <p>{{ t('kbOption.loadingList') }}</p>
          </div>

          <div v-else-if="error" class="error-state">
            <p>{{ error }}</p>
            <button @click="fetchKBList" class="retry-btn">{{ t('common.retry') }}</button>
          </div>

          <div v-else class="kb-list">
            <div
              v-for="kb in kbList"
              :key="kb.kb_id"
              :class="['kb-item', { selected: selectedKB && selectedKB.kb_id === kb.kb_id }]"
              @click="selectKB(kb)"
            >
              <h3 class="kb-name">{{ kb.name }}</h3>
            </div>

            <!-- 空状态 -->
            <div v-if="kbList.length === 0" class="empty-state">
              <p>{{ t('kbOption.noKB') }}</p>
            </div>
          </div>
        </div>

        <div class="kb-main">
          <div v-if="!selectedKB" class="no-selection">
            <p>{{ t('kbOption.selectKBHint') }}</p>
          </div>

          <div v-else>
            <div class="kb-info">
                <div class="kb-info-header">
                  <div class="name-wrapper">
                    <h3 v-if="!isEditing">{{ selectedKB.name }}<div v-if="isCreating && selectedKB.kb_id.startsWith('temp_') && !isEditing" class="loading-spinner small inline"></div></h3>
                    <input v-else v-model="editedName" class="edit-input" :placeholder="t('kbOption.kbNamePlaceholder')">
                    <button v-if="!isEditing" class="action-btn edit-kb" :data-tooltip="t('common.edit')" @click="startEdit">
                      <img src="@/assets/images/edit_icon.svg" width="18" height="18" />
                    </button>
                  </div>
                  <div class="kb-actions">
                    <button v-if="!isEditing" class="action-btn add-file" @click="addFilesToKB(selectedKB.kb_id)">{{ t('kbOption.addFile') }}</button>
                    <button v-if="!isEditing" class="action-btn delete-kb" :data-tooltip="t('common.delete')" @click="deleteKB(selectedKB.kb_id)">
                    <img src="@/assets/images/delete.svg" width="18" height="18" />
                    </button>
                    <template v-if="isEditing">
                      <button class="action-btn save-edit" @click="saveEdit">{{ t('common.save') }}</button>
                      <button class="action-btn cancel-edit" @click="cancelEdit">{{ t('common.cancel') }}</button>
                    </template>
                  </div>
                </div>
                <div class="kb-info-content">
                  <p v-if="!isEditing">{{ selectedKB.description }}<div v-if="isCreating && selectedKB.kb_id.startsWith('temp_') && !isEditing" class="loading-spinner small inline"></div></p>
                  <textarea v-else v-model="editedDescription" class="edit-textarea" :placeholder="t('kbOption.kbDescPlaceholder')"></textarea>
                </div>
            </div>
            <div v-if="selectedKB.loadingDocs" class="loading-docs">{{ t('kbOption.loadingDocs') }}</div>
            <div v-else-if="selectedKB.docsError" class="error-docs">{{ selectedKB.docsError }}</div>
            <div v-else class="docs-list">
              <div
                v-for="doc in selectedKB.docs"
                :key="doc.doc_id"
                class="doc-item"
                @click="fetchFileContent(doc.name)"
              >
                <span class="doc-name">{{ doc.name }}</span>
                <button class="delete-doc" :data-tooltip="t('common.delete')" @click="deleteDoc(selectedKB.kb_id, doc.doc_id)">
                  <img src="@/assets/images/delete.svg" width="18" height="18" />
                </button>
              </div>
              <div v-if="selectedKB.docs.length === 0" class="empty-docs">{{ t('kbOption.noDocs') }}</div>
            </div>
            <!-- 待上传文件区域 -->
            <div v-if="pendingFiles.length > 0" class="pending-area">
              <h4>{{ t('kbOption.pendingUpload') }}</h4>
              <div class="pending-list">
                <div v-for="(file, index) in pendingFiles" :key="index" class="pending-item">
                  {{ file.name }}
                  <button class="remove-btn" @click="removePending(index)">{{ t('kbOption.remove') }}</button>
                </div>
              </div>
              <div class="upload-buttons">
                <button class="upload-btn" @click="startUpload">{{ t('kbOption.upload') }}</button>
                <button class="cancel-btn" @click="clearPending">{{ t('common.cancel') }}</button>
              </div>
            </div>
            <!-- 新增进度显示区域 -->
            <div v-if="uploadProgress.length > 0" class="progress-area">
              <h4>{{ t('kbOption.uploadProgress') }}</h4>
              <div class="progress-list">
                <div v-for="(prog, index) in uploadProgress" :key="index" class="progress-item" :class="getStatusClass(prog)">
                  {{ prog }}<div v-if="isProgressProcessing(prog)" class="loading-spinner small inline"></div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 文件预览区域 -->
        <div class="file-preview-panel">
          <div class="preview-header">
            <h4>{{ selectedFile || t('kbOption.filePreview') }}</h4>
            <div class="header-actions" v-if="selectedFile">
              <img :src="DownloadIcon" :alt="t('kbOption.download')" class="icon-button" @click="downloadFile(selectedFile)" />
            </div>
          </div>
          <div class="preview-content">
            <div v-if="!selectedFile" class="no-selection">
              <p>{{ t('kbOption.selectFilePreview') }}</p>
            </div>
            <div v-else-if="previewError" class="error">{{ previewError }}</div>
            <img v-else-if="isImage" :src="fileUrl" alt="Image Preview" class="preview-image" />
            <iframe v-else-if="isHtml" :src="fileUrl" class="html-iframe" frameborder="0" sandbox="allow-scripts allow-same-origin allow-forms"></iframe>
            <VueOfficeExcel v-else-if="isExcel" :src="fileUrl" />
            <VueOfficePdf v-else-if="isPdf" :src="fileUrl" />
            <VueOfficePptx v-else-if="isPpt" :src="fileUrl" />
            <div v-else v-html="renderPreview"></div>
          </div>
        </div>
      </div>

      <!-- 隐藏的文件输入 -->
      <input type="file" multiple ref="fileInput" style="display: none" @change="handleFileSelect" />

      <!-- 删除确认模态保留，因为删除需要确认 -->
      <div v-if="showConfirmModal" class="confirm-modal">
        <div class="confirm-content">
          <h3>{{ t('kbOption.confirmDelete') }}</h3>
          <p>{{ confirmMessage }}</p>
          <div class="confirm-buttons">
            <button class="confirm-btn" @click="confirmDelete">{{ t('common.confirm') }}</button>
            <button class="cancel-btn" @click="cancelConfirm">{{ t('common.cancel') }}</button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed, watch, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'
import axios from 'axios'

const { t } = useI18n()

function isProgressProcessing(prog: string) {
  return prog.endsWith(t('kbOption.processingSuffix'))
}
import MarkdownIt from 'markdown-it'
import hljs from 'highlight.js'
import 'highlight.js/styles/github.css'
// @ts-ignore
import DownloadIcon from '@/assets/images/download_icon.svg?url'
// Import vue-office components
import VueOfficeDocx from '@vue-office/docx'
import '@vue-office/docx/lib/index.css'
import VueOfficeExcel from '@vue-office/excel'
import '@vue-office/excel/lib/index.css'
import VueOfficePdf from '@vue-office/pdf'
import VueOfficePptx from '@vue-office/pptx'
import mammoth from 'mammoth';

defineEmits<{ close: [] }>()
const { userId } = defineProps<{ userId: string }>()

// 接口定义
interface Doc {
  doc_id: string
  name: string
}

interface KB {
  kb_id: string
  name: string
  description: string
  fileCount: number
  docs: Doc[]
  loadingDocs: boolean
  docsError: string
}

const kbList = ref<KB[]>([])
const selectedKB = ref<KB | null>(null)
const loading = ref(false)
const error = ref('')
const fileInput = ref<HTMLInputElement | null>(null)
const currentFiles = ref<File[]>([])
const uploadProgress = ref<string[]>([])
const isCreating = ref(false)
const isEditing = ref(false)
const editedName = ref('')
const editedDescription = ref('')

const pendingFiles = ref<File[]>([])

// 文件预览相关状态
const selectedFile = ref<string | null>(null)
const fileContent = ref<string>('')
const previewError = ref<string>('')
const fileUrl = ref<string>('')
const fileBlob = ref<Blob | null>(null)

// Markdown配置
const md = new MarkdownIt({
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
  <img src="${DownloadIcon}" alt="copy" class="code-copy-btn" />
</div>
  `
  const codeBlock = `<pre class="hljs"><code>${highlighted}</code></pre>`
  return `<div class="code-wrapper">${titleBar}${codeBlock}</div>`
}

// 定义renderMarkdown
function renderMarkdown(content) {
  try {
    const parsed = JSON.parse(content);
    return renderStructured(parsed);
  } catch (e) {
    let html = md.render(content ?? '');
    html = html.replace(/<a /g, '<a target="_blank" rel="noopener noreferrer" ');
    return html;
  }
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

const showConfirmModal = ref(false)
const confirmType = ref<'kb' | 'doc'>('kb')
const confirmMessage = ref('')
const currentKBIdForDelete = ref('')
const currentDocIdForDelete = ref('')

// 新增清理函数
function cleanupTempKB() {
  if (isCreating.value && selectedKB.value?.kb_id.startsWith('temp_')) {
    kbList.value = kbList.value.filter(kb => kb.kb_id !== selectedKB.value?.kb_id)
    selectedKB.value = null
    isCreating.value = false
  }
}

async function fetchKBList() {
  loading.value = true
  error.value = ''
  try {
    const response = await axios.get(`/kb/kb/list/?user_id=${userId}`)
    if (response.data.success) {
      kbList.value = response.data.data.map((kb: any) => ({
        kb_id: kb.kb_id,
        name: kb.kb_name_zh,
        description: kb.kb_description,
        fileCount: kb.kb_file_count,
        docs: [],
        loadingDocs: false,
        docsError: ''
      }))
      // 如果有选中的KB，更新它
      if (selectedKB.value) {
        const updated = kbList.value.find(k => k.kb_id === selectedKB.value!.kb_id)
        if (updated) selectedKB.value = updated
      }
    } else {
      throw new Error('API returned success: false')
    }
  } catch (err) {
    error.value = 'Failed to load knowledge bases'
  } finally {
    loading.value = false
  }
}

function selectKB(kb: KB) {
  selectedKB.value = kb
  isEditing.value = false
  if (kb.docs.length === 0 && !kb.loadingDocs && !kb.docsError) {
    loadDocs(kb.kb_id)
  }
}

async function loadDocs(kbId: string) {
  const kb = kbList.value.find(k => k.kb_id === kbId)
  if (!kb) return

  kb.loadingDocs = true
  kb.docsError = ''
  try {
    const response = await axios.get(`/kb/kb/docs/?kb_id=${kbId}`)
    if (response.data.success) {
      kb.docs = response.data.data
    } else {
      throw new Error('API returned success: false')
    }
  } catch (err) {
    kb.docsError = 'Failed to load documents'
  } finally {
    kb.loadingDocs = false
  }
}

function startCreate() {
  // 创建临时KB
  const tempKB: KB = {
    kb_id: 'temp_' + Date.now(),
    name: t('kbOption.generating'),
    description: t('kbOption.generating'),
    fileCount: 0,
    docs: [],
    loadingDocs: false,
    docsError: ''
  }
  kbList.value.push(tempKB)
  selectedKB.value = tempKB
  isCreating.value = true
  triggerFileSelect()
}

function addFilesToKB(kbId: string) {
  const kb = kbList.value.find(k => k.kb_id === kbId)
  if (kb) {
    selectedKB.value = kb
  }
  triggerFileSelect()
}

function triggerFileSelect() {
  if (fileInput.value) {
    fileInput.value.value = '' // 重置以允许重新选择
    fileInput.value.click()
  }
}

function handleFileSelect(event: Event) {
  const input = event.target as HTMLInputElement
  if (input.files) {
    const newFiles = Array.from(input.files)
    if (newFiles.length > 0) {
      pendingFiles.value = [...pendingFiles.value, ...newFiles]
    } else if (isCreating.value && pendingFiles.value.length === 0) {
      cleanupTempKB()
    }
    input.value = ''
  }
}

function removePending(index: number) {
  pendingFiles.value.splice(index, 1)
}

function clearPending() {
  pendingFiles.value = []
  if (isCreating.value) {
    cleanupTempKB()
  }
}

function startUpload() {
  currentFiles.value = [...pendingFiles.value]
  pendingFiles.value = []
  uploadFiles()
}

async function uploadFiles() {
  uploadProgress.value = []
  currentFiles.value.forEach(file => {
    uploadProgress.value.push(`${file.name}${t('kbOption.processingSuffix')}`)
  })

  try {
    let response
    if (isCreating.value) {
      const formData = new FormData()
      currentFiles.value.forEach(file => formData.append('files', file))
      formData.append('user_id', userId)

      response = await fetch('/kb/kb/create/', {
        method: 'POST',
        body: formData
      })
    } else {
      const formData = new FormData()
      formData.append('kb_id', selectedKB.value!.kb_id)
      currentFiles.value.forEach(file => formData.append('files', file))

      response = await fetch('/kb/kb/add-file/', {
        method: 'POST',
        body: formData
      })
    }

    if (!response.body) throw new Error('No response body')

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) {
        if (buffer.trim()) {
          processLine(buffer.trim())
        }
        break
      }
      buffer += decoder.decode(value)
      const lines = buffer.split('\n')
      for (let i = 0; i < lines.length - 1; i++) {
        const line = lines[i].trim()
        if (line) {
          processLine(line)
        }
      }
      buffer = lines[lines.length - 1]
    }

    // 刷新列表
    await fetchKBList()
    // 如果是创建，移除临时KB并选中新的
    if (isCreating.value) {
      kbList.value = kbList.value.filter(kb => !kb.kb_id.startsWith('temp_'))
      // 假设新KB是列表中最后一个，或根据逻辑查找
      if (kbList.value.length > 0) {
        selectKB(kbList.value[kbList.value.length - 1])
      }
    } else if (selectedKB.value) {
      loadDocs(selectedKB.value.kb_id)
    }
    isCreating.value = false
    
    // Delay clear to show completion
    setTimeout(() => {
      uploadProgress.value = []
    }, 2000)
  } catch (err) {
    uploadProgress.value.push(t('kbOption.uploadFailedWith', { msg: (err as Error).message }))
  } finally {
    currentFiles.value = []
  }
}

function processLine(line: string) {
  try {
    const res = JSON.parse(line)
    if (res.success) {
      for (let i = 0; i < uploadProgress.value.length; i++) {
        if (isProgressProcessing(uploadProgress.value[i])) {
          uploadProgress.value[i] = uploadProgress.value[i].replace(
            t('kbOption.processingSuffix'),
            t('kbOption.parseCompleteSuffix'),
          )
          uploadProgress.value = [...uploadProgress.value] // trigger reactivity
          break
        }
      }
    } else {
      uploadProgress.value.push(t('kbOption.failedWith', { msg: res.message || t('kbOption.unknownError') }))
    }
  } catch (e) {
    uploadProgress.value.push(line)
  }
}

async function deleteKB(kbId: string) {
  confirmType.value = 'kb'
  confirmMessage.value = t('kbOption.confirmDeleteKB')
  currentKBIdForDelete.value = kbId
  showConfirmModal.value = true
}

async function deleteDoc(kbId: string, docId: string) {
  confirmType.value = 'doc'
  confirmMessage.value = t('kbOption.confirmDeleteDoc')
  currentKBIdForDelete.value = kbId
  currentDocIdForDelete.value = docId
  showConfirmModal.value = true
}

async function confirmDelete() {
  showConfirmModal.value = false
  try {
    if (confirmType.value === 'kb') {
      await axios.delete(`/kb/kb/delete/${currentKBIdForDelete.value}`)
      fetchKBList()
      if (selectedKB.value?.kb_id === currentKBIdForDelete.value) {
        selectedKB.value = null
      }
    } else {
      await axios.delete(`/kb/kb/delete-doc/${currentDocIdForDelete.value}`)
      if (selectedKB.value?.kb_id === currentKBIdForDelete.value) {
        loadDocs(currentKBIdForDelete.value)
      }
    }
  } catch (err) {
    alert(t('kbOption.deleteFailed'))
  }
}

function cancelConfirm() {
  showConfirmModal.value = false
}

function startEdit() {
  if (selectedKB.value) {
    editedName.value = selectedKB.value.name
    editedDescription.value = selectedKB.value.description
    isEditing.value = true
  }
}

async function saveEdit() {
  if (!selectedKB.value) return
  try {
    const formData = new FormData()
    formData.append('kb_id', selectedKB.value.kb_id)
    formData.append('kb_name_zh', editedName.value)
    formData.append('kb_description', editedDescription.value)
    
    const response = await axios.post('kb/kb/update/kb_info/', formData, {
      headers: {
        'Content-Type': 'multipart/form-data'
      }
    })
    
    if (response.data.success) {
      selectedKB.value.name = editedName.value
      selectedKB.value.description = editedDescription.value
      // 更新列表中的对应项
      const index = kbList.value.findIndex(k => k.kb_id === selectedKB.value!.kb_id)
      if (index !== -1) {
        kbList.value[index].name = editedName.value
        kbList.value[index].description = editedDescription.value
      }
      isEditing.value = false
    } else {
      alert(t('kbOption.updateFailed'))
    }
  } catch (err) {
    alert(t('kbOption.updateFailed') + ': ' + (err as Error).message)
  }
}

function cancelEdit() {
  isEditing.value = false
  editedName.value = ''
  editedDescription.value = ''
}

function handleOverlayClick() {
  // 点击遮罩关闭
}

function getStatusClass(prog: string) {
  if (prog.endsWith(t('kbOption.processingSuffix'))) return 'processing'
  if (prog.endsWith(t('kbOption.parseCompleteSuffix'))) return 'completed'
  if (prog.includes(t('kbOption.failed')) || prog.includes(t('kbOption.uploadFailed'))) return 'error'
  return ''
}

// 文件预览相关方法
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

// Update renderPreview for text/markdown
const renderPreview = computed(() => {
  if (isDocx.value) {
    return fileContent.value;
  }
  if (!fileContent.value || !isTextFile.value) return ''
  return md.render(fileContent.value)
})

// Add cleanup for URL
watch(selectedFile, () => {
  if (fileUrl.value) {
    URL.revokeObjectURL(fileUrl.value)
  }
  fileUrl.value = ''
  fileContent.value = ''
})

// Modify fetchFileContent to fetch blob
const fetchFileContent = async (filename: string) => {
  selectedFile.value = filename
  try {
    const response = await axios.get(`/kb/kb/file_content/${filename}?kb_id=${selectedKB.value!.kb_id}`, {
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
            previewError.value = t('kbOption.cannotConvertDocx');
            console.error('DOCX conversion error:', err);
          }
        } else {
          previewError.value = t('kbOption.cannotReadDocx');
        }
      };
      reader.onerror = () => {
        previewError.value = t('kbOption.readDocxFailed');
      };
      reader.readAsArrayBuffer(blob);
    } else if (isTextFile.value) {
      blob.text().then(text => {
        fileContent.value = text
      }).catch(err => {
        console.error('Failed to read text:', err)
        previewError.value = t('kbOption.cannotReadContent')
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
    console.error('获取文件内容失败:', error)
    previewError.value = t('kbOption.cannotPreviewType')
    fileUrl.value = ''
    fileContent.value = ''
  }
}

const downloadFile = async (filename: string) => {
  try {
    const response = await axios.get(`/kb/kb/download/${filename}?kb_id=${selectedKB.value!.kb_id}`, {
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
    console.error('下载文件失败:', error);
  }
};

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
      btn.src = DownloadIcon // 这里应该用一个success icon，但暂时用download icon代替
      setTimeout(() => {
        btn.src = originalSrc
      }, 2000)
    }).catch(err => {
      console.error('Failed to copy code:', err)
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
        btn.src = DownloadIcon
        setTimeout(() => {
          btn.src = originalSrc
        }, 2000)
      } else {
        console.error('Fallback: Failed to copy');
      }
    } catch (err) {
      console.error('Fallback: Failed to copy: ', err);
    }
    document.body.removeChild(textarea);
  }
}

onMounted(() => {
  if (userId) fetchKBList()
  attachCopyListeners()
})

onUnmounted(() => {
  if (isCreating.value) {
    cleanupTempKB()
  }
})
</script>

<style scoped>
.kb-option-overlay {
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

.kb-option-container {
  background: #ffffff;
  border-radius: 20px;
  width: 90%;
  width: 120vh;
  height: 80vh;
  overflow: hidden;
  box-shadow:
    0 0 0 0.5px rgba(0, 0, 0, 0.06),
    0 24px 60px -12px rgba(0, 0, 0, 0.18),
    0 12px 24px -8px rgba(0, 0, 0, 0.08);
  display: flex;
  flex-direction: column;
  font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Helvetica Neue', 'PingFang SC', sans-serif;
}

/* ── Header (Apple-style light) ── */
.kb-option-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  padding: 26px 32px 20px;
  background: #ffffff;
  box-shadow: 0 1px 0 rgba(0, 0, 0, 0.05);
  position: relative;
  z-index: 2;
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

.kb-option-header h2 {
  margin: 0;
  font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Display', 'Helvetica Neue', 'PingFang SC', sans-serif;
  font-size: 1.5rem;
  font-weight: 500;
  color: #1d1d1f;
  letter-spacing: -0.022em;
  line-height: 1.18;
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
  padding: 0;
}

.close-btn:hover {
  background: rgba(0, 0, 0, 0.08);
  color: #1d1d1f;
}

.close-btn:active {
  transform: scale(0.94);
}

.create-section {
  padding: 12px 24px;
  border-bottom: 1px solid rgba(0, 0, 0, 0.05);
  background: #f5f5f7;
}

.create-btn {
  background: #1d1d1f;
  color: #ffffff;
  padding: 8px 18px;
  border: none;
  border-radius: 980px;
  cursor: pointer;
  font-family: inherit;
  font-size: 0.8125rem;
  font-weight: 500;
  letter-spacing: -0.005em;
  transition: background 0.18s ease;
}

.create-btn:hover {
  background: #000;
}

.kb-content {
  flex: 1;
  display: flex;
  overflow: hidden;
  background: #f5f5f7;
}

.kb-sidebar {
  width: 250px;
  border-right: 1px solid rgba(0, 0, 0, 0.05);
  overflow-y: auto;
  padding: 16px;
  background: #fafafa;
  flex-shrink: 0;
}

.kb-main {
  width: 300px;
  padding: 24px;
  overflow-y: auto;
  border-right: 1px solid rgba(0, 0, 0, 0.05);
  flex-shrink: 0;
  background: #f5f5f7;
}

.no-selection {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #86868b;
  font-size: 0.875rem;
  letter-spacing: -0.005em;
}

.kb-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.kb-item {
  padding: 11px 14px;
  border: 1px solid transparent;
  border-radius: 10px;
  cursor: pointer;
  transition: background 0.18s ease, border-color 0.18s ease;
}

.kb-item:hover {
  background: rgba(0, 0, 0, 0.03);
}

.kb-item.selected {
  background: #ffffff;
  border-color: rgba(0, 0, 0, 0.06);
  box-shadow:
    0 1px 2px rgba(0, 0, 0, 0.04),
    0 0 0 0.5px rgba(0, 0, 0, 0.02);
}

.kb-name {
  margin: 0;
  font-size: 0.9375rem;
  font-weight: 500;
  color: #1d1d1f;
  letter-spacing: -0.012em;
  line-height: 1.35;
}

.kb-info {
  margin-bottom: 18px;
  padding: 16px;
  background: #ffffff;
  border: 1px solid rgba(0, 0, 0, 0.05);
  border-radius: 12px;
  box-shadow:
    0 1px 2px rgba(0, 0, 0, 0.03),
    0 0 0 0.5px rgba(0, 0, 0, 0.02);
}

.kb-info p {
  color: #6e6e73;
  margin: 8px 0 0;
  font-size: 0.8125rem;
  font-weight: 400;
  line-height: 1.5;
  letter-spacing: -0.005em;
}

.kb-info-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.kb-actions {
  display: flex;
  gap: 6px;
}

.action-btn {
  padding: 5px 12px;
  border-radius: 980px;
  border: none;
  cursor: pointer;
  font-family: inherit;
  font-size: 0.75rem;
  font-weight: 500;
  letter-spacing: -0.005em;
  transition: background 0.18s ease, opacity 0.18s ease;
}

.add-file {
  background: #1d1d1f;
  color: #ffffff;
}

.add-file:hover {
  background: #000;
}

.delete-kb,
.delete-doc {
  background: none;
  padding: 0;
  border: none;
  cursor: pointer;
  font-size: 0.875rem;
  transition: opacity 0.2s;
  position: relative;
}

.delete-kb:hover,
.delete-doc:hover {
  opacity: 0.7;
}

.delete-kb::after,
.delete-doc::after {
  content: attr(data-tooltip);
  position: absolute;
  bottom: 100%;
  left: 50%;
  transform: translateX(-50%);
  margin-bottom: 8px;
  padding: 4px 8px;
  background-color: #000;
  color: #fff;
  font-size: 12px;
  white-space: nowrap;
  border-radius: 4px;
  opacity: 0;
  visibility: hidden;
  transition: opacity 0.2s, visibility 0.2s;
  pointer-events: none;
  z-index: 1000;
}

.delete-kb:hover::after,
.delete-doc:hover::after {
  opacity: 1;
  visibility: visible;
}

.docs-list {
  display: flex;
  flex-direction: column;
  gap: 0;
  margin-top: 8px;
  background: #ffffff;
  border-radius: 12px;
  border: 1px solid rgba(0, 0, 0, 0.05);
  box-shadow:
    0 1px 2px rgba(0, 0, 0, 0.03),
    0 0 0 0.5px rgba(0, 0, 0, 0.02);
  overflow: hidden;
}

.doc-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 11px 14px;
  background: transparent;
  border-radius: 0;
  border: none;
  border-top: 1px solid rgba(0, 0, 0, 0.05);
  cursor: pointer;
  transition: all 0.2s;
}

.doc-item:first-child {
  border-top: none;
}

.doc-item:hover {
  background: rgba(0, 0, 0, 0.02);
}

.doc-name {
  font-size: 0.8125rem;
  font-weight: 400;
  color: #1d1d1f;
  letter-spacing: -0.005em;
}

.loading-state,
.error-state,
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 36px 20px;
  text-align: center;
  color: #86868b;
  font-size: 0.8125rem;
  letter-spacing: -0.005em;
}

.empty-docs {
  padding: 16px;
  text-align: center;
  color: #86868b;
  font-size: 0.8125rem;
  letter-spacing: -0.005em;
}

.loading-spinner {
  width: 28px;
  height: 28px;
  border: 2px solid rgba(0, 0, 0, 0.06);
  border-top-color: #1d1d1f;
  border-radius: 50%;
  animation: spin 0.9s linear infinite;
  margin-bottom: 12px;
}

.loading-spinner.small {
  width: 16px;
  height: 16px;
  border-width: 2px;
  margin-bottom: 0;
}

.loading-spinner.inline {
  display: inline-block;
  vertical-align: middle;
  margin-left: 8px;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.retry-btn {
  margin-top: 12px;
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
  transition: background 0.18s ease, transform 0.2s ease;
}

.retry-btn:hover {
  background: #000;
}

.retry-btn:active {
  transform: scale(0.97);
}

.upload-modal {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0,0,0,0.5);
  display: flex;
  justify-content: center;
  align-items: center;
}

.upload-content {
  background: white;
  padding: 20px;
  border-radius: 8px;
  width: 400px;
}

.progress {
  margin-top: 10px;
  white-space: pre-wrap;
}

.create-kb {
  display: flex;
  justify-content: center;
  align-items: center;
  background: transparent;
  margin-bottom: 12px;
}

.plus-box {
  width: 100%;
  height: 38px;
  border: 1px solid rgba(0, 0, 0, 0.06);
  border-radius: 10px;
  display: flex;
  justify-content: center;
  align-items: center;
  cursor: pointer;
  background: #ffffff;
  box-shadow:
    0 1px 2px rgba(0, 0, 0, 0.03),
    0 0 0 0.5px rgba(0, 0, 0, 0.02);
  transition: background 0.18s ease, border-color 0.18s ease;
}

.plus-box:hover {
  background: #1d1d1f;
  border-color: #1d1d1f;
}

.plus-box:hover img {
  filter: brightness(0) invert(1);
}

.confirm-modal {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0,0,0,0.5);
  display: flex;
  justify-content: center;
  align-items: center;
}

.confirm-content {
  background: #ffffff;
  padding: 24px;
  border-radius: 16px;
  width: 320px;
  text-align: center;
  box-shadow:
    0 0 0 0.5px rgba(0, 0, 0, 0.06),
    0 24px 60px -12px rgba(0, 0, 0, 0.18);
  font-family: inherit;
}

.confirm-content h3 {
  margin: 0 0 6px;
  font-size: 1rem;
  font-weight: 500;
  color: #1d1d1f;
  letter-spacing: -0.012em;
}

.confirm-content p {
  margin: 0;
  font-size: 0.8125rem;
  color: #6e6e73;
  letter-spacing: -0.005em;
}

.confirm-buttons {
  display: flex;
  justify-content: center;
  gap: 10px;
  margin-top: 18px;
}

.confirm-btn {
  background: #d70015;
  color: #ffffff;
  padding: 7px 18px;
  border: none;
  border-radius: 980px;
  cursor: pointer;
  font-family: inherit;
  font-size: 0.8125rem;
  font-weight: 500;
  letter-spacing: -0.005em;
  transition: background 0.18s ease;
}

.confirm-btn:hover {
  background: #b8000f;
}

.cancel-btn {
  background: rgba(0, 0, 0, 0.06);
  color: #1d1d1f;
  padding: 7px 18px;
  border: none;
  border-radius: 980px;
  cursor: pointer;
  font-family: inherit;
  font-size: 0.8125rem;
  font-weight: 500;
  letter-spacing: -0.005em;
  transition: background 0.18s ease;
}

.cancel-btn:hover {
  background: rgba(0, 0, 0, 0.1);
}

/* 响应式 */
@media (max-width: 768px) {
  .kb-content {
    flex-direction: column;
  }
  
  .kb-sidebar {
    width: auto;
    border-right: none;
    border-bottom: 1px solid #e5e7eb;
  }
  
  .kb-main {
    padding: 16px;
  }
}

@media (max-width: 640px) {
  .kb-option-container {
    width: 95%;
    max-height: 90vh;
  }
}

.progress-area {
  margin-top: 18px;
  padding: 14px;
  background: #ffffff;
  border-radius: 12px;
  border: 1px solid rgba(0, 0, 0, 0.05);
  box-shadow:
    0 1px 2px rgba(0, 0, 0, 0.03),
    0 0 0 0.5px rgba(0, 0, 0, 0.02);
}

.progress-area h4,
.pending-area h4 {
  margin: 0 0 8px;
  font-size: 0.6875rem;
  font-weight: 600;
  color: #86868b;
  letter-spacing: 0.1em;
  text-transform: uppercase;
}

.progress-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.progress-item {
  padding: 8px 12px;
  border-radius: 8px;
  background: #f5f5f7;
  font-family: inherit;
  font-size: 0.8125rem;
  font-weight: 400;
  color: #1d1d1f;
  letter-spacing: -0.005em;
}

.processing {
  color: #b25000;
}

.completed {
  color: #1d8348;
}

.error {
  color: #d70015;
}

.pending-area {
  margin-top: 18px;
  padding: 14px;
  background: #ffffff;
  border-radius: 12px;
  border: 1px solid rgba(0, 0, 0, 0.05);
  box-shadow:
    0 1px 2px rgba(0, 0, 0, 0.03),
    0 0 0 0.5px rgba(0, 0, 0, 0.02);
}

.pending-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.pending-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  background: #f5f5f7;
  border-radius: 8px;
  font-size: 0.8125rem;
  color: #1d1d1f;
  letter-spacing: -0.005em;
}

.remove-btn {
  background: transparent;
  color: #d70015;
  padding: 4px 10px;
  border: 1px solid rgba(215, 0, 21, 0.2);
  border-radius: 980px;
  cursor: pointer;
  font-family: inherit;
  font-size: 0.6875rem;
  font-weight: 500;
  letter-spacing: -0.005em;
  transition: background 0.18s ease;
}

.remove-btn:hover {
  background: rgba(215, 0, 21, 0.06);
}

.upload-buttons {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 12px;
}

.upload-btn {
  background: #1d1d1f;
  color: #ffffff;
  padding: 7px 16px;
  border: none;
  border-radius: 980px;
  cursor: pointer;
  font-family: inherit;
  font-size: 0.8125rem;
  font-weight: 500;
  letter-spacing: -0.005em;
  transition: background 0.18s ease;
}

.upload-btn:hover {
  background: #000;
}

.edit-kb {
  background: none;
  padding: 0;
  border: none;
  cursor: pointer;
  position: relative;
}

.edit-kb:hover {
  opacity: 0.7;
}

.edit-kb::after {
  content: attr(data-tooltip);
  position: absolute;
  bottom: 100%;
  left: 50%;
  transform: translateX(-50%);
  margin-bottom: 8px;
  padding: 4px 8px;
  background-color: #000;
  color: #fff;
  font-size: 12px;
  white-space: nowrap;
  border-radius: 4px;
  opacity: 0;
  visibility: hidden;
  transition: opacity 0.2s, visibility 0.2s;
  pointer-events: none;
  z-index: 1000;
}

.edit-kb:hover::after {
  opacity: 1;
  visibility: visible;
}

.edit-input {
  font-family: inherit;
  font-size: 1rem;
  font-weight: 500;
  width: 100%;
  padding: 6px 10px;
  border: 1px solid rgba(0, 0, 0, 0.1);
  border-radius: 8px;
  background: #ffffff;
  color: #1d1d1f;
  letter-spacing: -0.012em;
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}

.edit-input:focus {
  outline: none;
  border-color: #1d1d1f;
  box-shadow: 0 0 0 3px rgba(0, 0, 0, 0.06);
}

.edit-textarea {
  width: 100%;
  min-height: 80px;
  padding: 10px 12px;
  border: 1px solid rgba(0, 0, 0, 0.1);
  border-radius: 10px;
  resize: vertical;
  font-family: inherit;
  font-size: 0.875rem;
  line-height: 1.5;
  letter-spacing: -0.005em;
  color: #1d1d1f;
  background: #ffffff;
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}

.edit-textarea:focus {
  outline: none;
  border-color: #1d1d1f;
  box-shadow: 0 0 0 3px rgba(0, 0, 0, 0.06);
}

.save-edit {
  background: #1d1d1f;
  color: #ffffff;
}

.save-edit:hover {
  background: #000;
}

.cancel-edit {
  background: rgba(0, 0, 0, 0.06);
  color: #1d1d1f;
}

.cancel-edit:hover {
  background: rgba(0, 0, 0, 0.1);
}

.name-wrapper {
  display: flex;
  align-items: center;
  gap: 8px;
  max-width: 65%;
  min-width: 0;
}

.name-wrapper h3 {
  margin: 0;
  font-size: 1.0625rem;
  font-weight: 500;
  color: #1d1d1f;
  letter-spacing: -0.012em;
  line-height: 1.3;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.name-wrapper .edit-input {
  flex: 1;
}

.kb-info-content {
  margin-top: 6px;
  padding-right: 0;
}

/* 文件预览相关样式 */
.file-preview-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  background-color: #f5f5f7;
  overflow: hidden;
}

.preview-header {
  position: sticky;
  top: 0;
  background: #ffffff;
  padding: 12px 20px;
  border-bottom: 1px solid rgba(0, 0, 0, 0.05);
  z-index: 1;
  box-shadow: 0 1px 0 rgba(0, 0, 0, 0.04);
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.preview-header h4 {
  margin: 0;
  font-size: 0.875rem;
  font-weight: 500;
  color: #1d1d1f;
  letter-spacing: -0.005em;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
}

.preview-content {
  padding: 20px;
  height: auto;
  background-color: #ffffff;
  box-shadow: inset 0 1px 3px rgba(0,0,0,0.05);
  max-width: 100%;
  overflow-y: auto;
  word-break: break-word;
  font-size: 16px !important;
  line-height: 1.6;
}

/* Custom scrollbar for preview content */
.preview-content::-webkit-scrollbar {
  width: 6px;
}

.preview-content::-webkit-scrollbar-track {
  background: #f1f1f1;
  border-radius: 10px;
  box-shadow: inset 0 0 5px rgba(0,0,0,0.05);
}

.preview-content::-webkit-scrollbar-thumb {
  background: #ddd;
  border-radius: 10px;
  transition: background 0.3s ease;
}

.preview-content::-webkit-scrollbar-thumb:hover {
  background: #ccc;
}

.no-selection {
  color: #666;
  text-align: center;
  flex: 1;
  display: flex;
  justify-content: center;
  align-items: center;
}

.error {
  color: red;
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
}

.preview-image {
  max-width: 100%;
  height: auto;
  display: block;
  margin: 0 auto;
}

.unsupported {
  color: #666;
  text-align: center;
  padding: 20px;
}

:deep(.pptx-preview-wrapper) {
  height: auto !important;
  overflow-y: visible !important;
  background: transparent !important;
  width: 100% !important;
  margin: 0 !important;
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
  font-size: 16px !important;
  color: #4d4d4d;
  line-height: 1.6;
}

.icon-button {
  cursor: pointer;
  width: 20px;
  height: 20px;
}

.download-doc {
  background: none;
  padding: 0;
  border: none;
  cursor: pointer;
  font-size: 0.875rem;
  transition: opacity 0.2s;
  margin-left: 8px;
}

.download-doc:hover {
  opacity: 0.7;
}

.doc-item.selected {
  background: rgba(0, 0, 0, 0.04);
}
</style> 
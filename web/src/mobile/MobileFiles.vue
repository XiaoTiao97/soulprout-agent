<template>
  <div v-if="open" class="file-screen">
    <header class="file-bar">
      <button type="button" class="bar-btn" @click="onBack">
        <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M15 6l-6 6 6 6" />
        </svg>
        <span>{{ t('mobile.back') }}</span>
      </button>
      <h1 class="bar-title">{{ screen === 'list' ? t('mobile.allFiles') : fileTitle }}</h1>
      <button v-if="screen === 'preview'" type="button" class="bar-btn bar-btn--icon" :aria-label="t('mobile.download')" @click="downloadCurrent">
        <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M12 4v11M7 11l5 5 5-5M5 20h14" />
        </svg>
      </button>
      <span v-else class="bar-spacer"></span>
    </header>

    <div v-if="screen === 'list'" class="file-body">
      <p v-if="!conversationId" class="file-empty">{{ t('mobile.noConversation') }}</p>
      <p v-else-if="loadingList" class="file-empty">{{ t('mobile.loading') }}</p>
      <p v-else-if="!files.length" class="file-empty">{{ t('mobile.noFiles') }}</p>
      <ul v-else class="file-list">
        <li v-for="path in files" :key="path">
          <button type="button" class="file-row" @click="openPreview(path)">
            <img class="file-icon" :src="getFileIconUrlForName(baseName(path))" alt="" />
            <span class="file-meta">
              <span class="file-name">{{ baseName(path) }}</span>
              <span v-if="baseName(path) !== path" class="file-path">{{ path }}</span>
            </span>
          </button>
        </li>
      </ul>
    </div>

    <div v-else class="file-body file-body--preview">
      <p v-if="loadingPreview" class="file-empty">{{ t('mobile.loading') }}</p>
      <p v-else-if="previewError" class="file-empty">{{ previewError }}</p>
      <img v-else-if="isImage" :src="fileUrl" alt="" class="preview-image" />
      <iframe v-else-if="isHtml" :src="fileUrl" class="preview-frame" title="html"></iframe>
      <VueOfficeExcel v-else-if="isExcel" :src="fileUrl" class="preview-office" />
      <VueOfficePdf v-else-if="isPdf" :src="fileUrl" class="preview-office" />
      <VueOfficePptx v-else-if="isPpt" :src="fileUrl" class="preview-office" />
      <div v-else-if="isDocx" class="preview-html" v-html="textHtml"></div>
      <div v-else-if="isMarkdown" class="preview-html" v-html="textHtml"></div>
      <pre v-else-if="isText" class="preview-text">{{ textContent }}</pre>
      <p v-else class="file-empty">{{ t('extraInfo.cannotPreviewType') }}</p>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import axios from 'axios'
import MarkdownIt from 'markdown-it'
import mammoth from 'mammoth'
import VueOfficeExcel from '@vue-office/excel'
import '@vue-office/excel/lib/index.css'
import VueOfficePdf from '@vue-office/pdf'
import VueOfficePptx from '@vue-office/pptx'
import { getFileIconUrlForName } from '@/utils/userFileDisplay'
import { resolveApi } from './api'

const props = defineProps({
  open: { type: Boolean, default: false },
  conversationId: { type: String, default: '' },
  openPath: { type: String, default: '' },
  refreshToken: { type: Number, default: 0 },
})

const emit = defineEmits(['close'])
const { t } = useI18n()
const md = new MarkdownIt({ html: false, breaks: true, linkify: true })

const screen = ref('list')
const files = ref([])
const loadingList = ref(false)
const loadingPreview = ref(false)
const previewError = ref('')
const selectedFile = ref('')
const fileUrl = ref('')
const textContent = ref('')
const docxHtml = ref('')

const extension = computed(() => selectedFile.value.split('.').pop()?.toLowerCase() || '')
const isImage = computed(() => ['jpg', 'jpeg', 'png', 'gif', 'webp', 'svg', 'bmp'].includes(extension.value))
const isHtml = computed(() => extension.value === 'html' || extension.value === 'htm')
const isDocx = computed(() => extension.value === 'doc' || extension.value === 'docx')
const isExcel = computed(() => ['xls', 'xlsx'].includes(extension.value))
const isPdf = computed(() => extension.value === 'pdf')
const isPpt = computed(() => extension.value === 'ppt' || extension.value === 'pptx')
const isMarkdown = computed(() => extension.value === 'md')
const isText = computed(() =>
  ['txt', 'json', 'csv', 'js', 'ts', 'py', 'css', 'xml', 'yml', 'yaml', 'ini', 'conf', 'log', 'vue', 'sh'].includes(extension.value),
)
const textHtml = computed(() => {
  if (isDocx.value) return docxHtml.value
  if (isMarkdown.value) return md.render(textContent.value || '')
  return ''
})
const fileTitle = computed(() => baseName(selectedFile.value) || t('mobile.files'))

function baseName(path) {
  const parts = String(path || '').split('/')
  return parts[parts.length - 1] || path
}

function revokeUrl() {
  if (fileUrl.value) {
    URL.revokeObjectURL(fileUrl.value)
    fileUrl.value = ''
  }
}

async function fetchFiles() {
  if (!props.conversationId) {
    files.value = []
    return
  }
  loadingList.value = true
  try {
    const response = await axios.get(resolveApi(`/api/files?conversation_id=${encodeURIComponent(props.conversationId)}`))
    const data = response.data
    if (Array.isArray(data)) files.value = data
    else if (Array.isArray(data?.files)) files.value = data.files
    else if (Array.isArray(data?.data)) files.value = data.data
    else files.value = []
  } catch {
    files.value = []
  } finally {
    loadingList.value = false
  }
}

function resolvePath(filePath) {
  const normalized = String(filePath || '').replace(/\\/g, '/').replace(/^\/+/, '')
  if (!normalized) return ''
  const exact = files.value.find((item) => item === normalized || item.replace(/\\/g, '/') === normalized)
  if (exact) return exact
  const name = normalized.split('/').pop()
  const byName = files.value.find((item) => item.split('/').pop() === name)
  return byName || normalized
}

async function openPreview(filePath) {
  const resolved = resolvePath(filePath)
  if (!resolved || !props.conversationId) return
  if (!files.value.includes(resolved)) files.value = [...files.value, resolved]
  selectedFile.value = resolved
  screen.value = 'preview'
  previewError.value = ''
  textContent.value = ''
  docxHtml.value = ''
  revokeUrl()
  loadingPreview.value = true
  try {
    const response = await axios.get(
      resolveApi(`/api/file_content/${resolved}?conversation_id=${encodeURIComponent(props.conversationId)}`),
      { responseType: 'blob' },
    )
    const blob = response.data
    fileUrl.value = URL.createObjectURL(blob)
    if (isDocx.value) {
      const buffer = await blob.arrayBuffer()
      const result = await mammoth.convertToHtml({ arrayBuffer: buffer })
      docxHtml.value = result.value
    } else if (isMarkdown.value || isText.value) {
      textContent.value = await blob.text()
    }
  } catch {
    previewError.value = t('extraInfo.cannotPreviewType')
    revokeUrl()
  } finally {
    loadingPreview.value = false
  }
}

async function downloadCurrent() {
  if (!selectedFile.value || !props.conversationId) return
  const response = await axios.get(
    resolveApi(`/api/download/${selectedFile.value}?conversation_id=${encodeURIComponent(props.conversationId)}`),
    { responseType: 'blob' },
  )
  const url = URL.createObjectURL(response.data)
  const link = document.createElement('a')
  link.href = url
  link.download = baseName(selectedFile.value)
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

function onBack() {
  if (screen.value === 'preview') {
    screen.value = 'list'
    revokeUrl()
    return
  }
  emit('close')
}

watch(
  () => props.open,
  async (open) => {
    if (!open) {
      screen.value = 'list'
      revokeUrl()
      return
    }
    await fetchFiles()
    if (props.openPath) await openPreview(props.openPath)
    else screen.value = 'list'
  },
  { immediate: true },
)

watch(
  () => props.openPath,
  (path) => {
    if (props.open && path) openPreview(path)
  },
)

watch(
  () => props.refreshToken,
  () => {
    if (props.open && screen.value === 'list') fetchFiles()
  },
)
</script>

<style scoped>
.file-screen {
  position: fixed;
  inset: 0;
  z-index: 40;
  display: flex;
  flex-direction: column;
  background: #f2f2f2;
  padding-top: env(safe-area-inset-top);
  padding-bottom: env(safe-area-inset-bottom);
}

.file-bar {
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: center;
  gap: 8px;
  min-height: 52px;
  padding: 0 8px;
  background: #fff;
  border-bottom: 1px solid rgba(0, 0, 0, 0.06);
}

.bar-btn {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  border: none;
  background: transparent;
  color: #111;
  font-size: 15px;
  padding: 8px;
}

.bar-btn--icon {
  width: 40px;
  justify-content: center;
}

.bar-spacer {
  width: 40px;
}

.bar-title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  text-align: center;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.file-body {
  flex: 1;
  min-height: 0;
  overflow: auto;
}

.file-empty {
  margin: 48px 24px;
  text-align: center;
  color: #6b7280;
  font-size: 14px;
  line-height: 1.6;
}

.file-list {
  list-style: none;
  margin: 12px;
  padding: 0;
  background: #fff;
  border-radius: 16px;
  overflow: hidden;
}

.file-row {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 16px;
  border: none;
  border-bottom: 1px solid rgba(0, 0, 0, 0.05);
  background: #fff;
  text-align: left;
}

.file-list li:last-child .file-row {
  border-bottom: none;
}

.file-icon {
  width: 36px;
  height: 36px;
  flex-shrink: 0;
}

.file-meta {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.file-name {
  font-size: 15px;
  color: #111827;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.file-path {
  font-size: 12px;
  color: #9ca3af;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.file-body--preview {
  background: #fff;
}

.preview-image {
  display: block;
  max-width: 100%;
  margin: 0 auto;
}

.preview-frame,
.preview-office {
  width: 100%;
  height: 100%;
  border: none;
}

.preview-html,
.preview-text {
  margin: 0;
  padding: 16px;
  word-break: break-word;
  font-size: 14px;
  line-height: 1.6;
}

.preview-text {
  white-space: pre-wrap;
}

.preview-html :deep(img) {
  max-width: 100%;
}
</style>

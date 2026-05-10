<template>
  <div class="skills-option-overlay" @click="handleOverlayClick">
    <div class="skills-option-container" @click.stop>
      <div class="skills-option-header">
        <div class="header-title-group">
          <p class="header-eyebrow">SKILLS</p>
          <h2>技能库</h2>
        </div>

        <button class="close-btn" @click="$emit('close')" aria-label="关闭">
          <svg width="11" height="11" viewBox="0 0 10 10" fill="none">
            <path d="M9 1L1 9M1 1L9 9" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/>
          </svg>
        </button>
      </div>

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
            <span class="tab-count">{{ getSkillsCountByType(tab.type) }}</span>
          </button>
        </div>
      </div>

      <div class="skills-content">
        <div v-if="activeTab === 'personal'" class="personal-toolbar">
          <input
            ref="folderInputRef"
            type="file"
            class="folder-input-hidden"
            webkitdirectory
            multiple
            @change="onFolderFilesChange"
          />
          <div class="personal-toolbar-inner">
            <p class="toolbar-upload-label">从本地上传 skill 文件夹到个人技能库</p>
            <button
              type="button"
              class="upload-folder-btn"
              :disabled="uploading || !userId"
              @click="triggerFolderUpload"
            >
              <span v-if="uploading" class="upload-folder-btn-spinner" aria-hidden="true" />
              <svg
                v-else
                class="upload-folder-btn-icon"
                width="18"
                height="18"
                viewBox="0 0 24 24"
                fill="none"
                aria-hidden="true"
              >
                <!-- 向上箭头 + 底部横线，语义为「上传到本地/云端」 -->
                <path
                  d="M12 16V6m0 0l-4 4m4-4l4 4M5 20h14"
                  stroke="currentColor"
                  stroke-width="2"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                />
              </svg>
              <span>{{ uploading ? '上传中…' : '上传 skill' }}</span>
            </button>
          </div>
          <p v-if="uploadHint" class="upload-hint" :data-tone="uploadHintTone">{{ uploadHint }}</p>
        </div>

        <div v-if="loading" class="loading-state">
          <div class="loading-spinner"></div>
          <p>Loading skills...</p>
        </div>

        <div v-else-if="error" class="error-state">
          <p>{{ error }}</p>
          <button @click="fetchSkillsInfo" class="retry-btn">Retry</button>
        </div>

        <div v-else class="skills-list">
          <div
            v-for="skill in filteredSkills"
            :key="`${skill.type}-${skill.folder ?? skill.name}`"
            class="skill-item"
          >
            <div class="skill-shell">
              <div class="skill-header">
                <div class="skill-header-main" @click="toggleSkill(skillKey(skill))">
                  <div class="skill-header-text">
                    <h3 class="skill-name">{{ skill.name }}</h3>
                    <p
                      :class="[
                        'skill-description',
                        { expanded: expandedSkills.includes(skillKey(skill)) }
                      ]"
                    >
                      {{ skill.description }}
                    </p>
                  </div>
                  <div class="skill-toggle">
                    <svg
                      :class="[
                        'toggle-icon',
                        { expanded: expandedSkills.includes(skillKey(skill)) }
                      ]"
                      width="16"
                      height="16"
                      viewBox="0 0 16 16"
                      fill="none"
                    >
                      <path d="M4 6L8 10L12 6" stroke="currentColor" stroke-width="2" stroke-linecap="round" />
                    </svg>
                  </div>
                </div>
                <button
                  v-if="activeTab === 'personal' && skill.type === 'personal'"
                  type="button"
                  class="skill-delete-btn"
                  :disabled="deletingFolder === skillFolderForDelete(skill) || !userId"
                  @click.stop="deletePersonalSkill(skill)"
                >
                  {{ deletingFolder === skillFolderForDelete(skill) ? '删除中…' : '删除' }}
                </button>
              </div>
            </div>
          </div>

          <div v-if="filteredSkills.length === 0" class="empty-state">
            <p>暂未找到{{ activeTab === 'system' ? '系统' : '个人' }}技能</p>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import axios from 'axios'

interface SkillInfo {
  name: string
  description: string
  type: 'system' | 'personal'
  /** 个人技能在磁盘上的子目录名，删除时传给后端 */
  folder?: string
}

interface SkillApiResponse {
  name: string
  description: string
  type?: string
  folder?: string
}

const props = withDefaults(defineProps<{ userId?: string }>(), { userId: '' })

defineEmits<{ close: [] }>()

const folderInputRef = ref<HTMLInputElement | null>(null)
const uploading = ref(false)
const uploadHint = ref('')
const deletingFolder = ref<string | null>(null)

const skillsInfoList = ref<SkillInfo[]>([])
const loading = ref(false)
const error = ref('')
const activeTab = ref<'system' | 'personal'>('system')
const expandedSkills = ref<string[]>([])

const tabs = [
  { type: 'system' as const, label: '系统技能' },
  { type: 'personal' as const, label: '个人技能' }
]

const filteredSkills = computed(() => skillsInfoList.value.filter(skill => skill.type === activeTab.value))

const activeTabIndex = computed(() =>
  Math.max(0, tabs.findIndex(t => t.type === activeTab.value))
)

const uploadHintTone = computed<'success' | 'error' | 'neutral'>(() => {
  const t = uploadHint.value
  if (!t) return 'neutral'
  if (t.includes('成功')) return 'success'
  if (t.includes('失败') || t.includes('不是标准的skill')) return 'error'
  return 'neutral'
})

const SKILL_MD = 'SKILL.md'

/** 每个顶层文件夹根下必须有 SKILL.md（与后端一致） */
function validateSkillFolderUpload(files: FileList): { ok: true } | { ok: false; message: string } {
  const pathsByRoot = new Map<string, Set<string>>()
  for (let i = 0; i < files.length; i++) {
    const file = files[i] as File & { webkitRelativePath?: string }
    let rel = file.webkitRelativePath || file.name
    rel = rel.replace(/\\/g, '/').replace(/^\/+|\/+$/g, '')
    if (!rel || rel.split('/').includes('..')) continue
    const parts = rel.split('/').filter(Boolean)
    if (parts.length === 0) continue
    const root = parts[0]
    if (!pathsByRoot.has(root)) pathsByRoot.set(root, new Set())
    pathsByRoot.get(root)!.add(rel)
  }
  if (pathsByRoot.size === 0) {
    return { ok: false, message: '不是标准的skill文件：未检测到有效文件路径' }
  }
  for (const [root, paths] of pathsByRoot) {
    const required = `${root}/${SKILL_MD}`
    if (!paths.has(required)) {
      return {
        ok: false,
        message: `不是标准的skill文件：「${root}」根目录下必须包含 ${SKILL_MD}`
      }
    }
  }
  return { ok: true }
}

function getSkillsCountByType(type: 'system' | 'personal'): number {
  return skillsInfoList.value.filter(skill => skill.type === type).length
}

/** 个人技能在磁盘上的子目录名：接口未带 folder 时，用 name 兜底（仅当与实际上传目录名一致时删除才正确） */
function skillFolderForDelete(skill: SkillInfo): string {
  const f = skill.folder?.trim()
  if (f) return f
  return skill.name?.trim() || ''
}

function skillKey(skill: SkillInfo): string {
  if (skill.type === 'personal') {
    const dir = skill.folder?.trim() || skill.name
    return `${dir}:${skill.name}`
  }
  return skill.name
}

function toggleSkill(key: string) {
  const index = expandedSkills.value.indexOf(key)
  if (index > -1) {
    expandedSkills.value.splice(index, 1)
  } else {
    expandedSkills.value.push(key)
  }
}

async function deletePersonalSkill(skill: SkillInfo) {
  if (!props.userId) return
  const folder = skillFolderForDelete(skill)
  if (!folder) return
  if (!confirm(`确定删除个人技能「${skill.name}」？此操作不可恢复。`)) return
  deletingFolder.value = folder
  uploadHint.value = ''
  try {
    await axios.delete('/api/user_skills', {
      params: { user_id: props.userId, folder }
    })
    uploadHint.value = '删除成功'
    await fetchSkillsInfo()
  } catch (err) {
    console.error('删除个人技能失败:', err)
    uploadHint.value = '删除失败，请稍后重试'
  } finally {
    deletingFolder.value = null
  }
}

function triggerFolderUpload() {
  uploadHint.value = ''
  if (!props.userId) {
    uploadHint.value = '请先登录后再上传个人技能'
    return
  }
  folderInputRef.value?.click()
}

async function onFolderFilesChange(ev: Event) {
  const input = ev.target as HTMLInputElement
  const files = input.files
  if (!files?.length || !props.userId) {
    input.value = ''
    return
  }

  const localCheck = validateSkillFolderUpload(files)
  if (!localCheck.ok) {
    uploadHint.value = localCheck.message
    input.value = ''
    return
  }

  uploading.value = true
  uploadHint.value = ''
  try {
    const formData = new FormData()
    formData.append('user_id', props.userId)
    for (let i = 0; i < files.length; i++) {
      const file = files[i] as File & { webkitRelativePath?: string }
      const relPath = file.webkitRelativePath || file.name
      formData.append('files', file, relPath)
    }
    await axios.post('/api/user_skills/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 120000
    })
    uploadHint.value = '上传成功'
    await fetchSkillsInfo()
  } catch (err: unknown) {
    console.error('上传个人技能失败:', err)
    let msg = '上传失败，请稍后重试'
    if (axios.isAxiosError(err) && err.response?.status === 400) {
      const d = err.response.data as { detail?: unknown }
      if (typeof d?.detail === 'string') msg = d.detail
    }
    uploadHint.value = msg
  } finally {
    uploading.value = false
    input.value = ''
  }
}

async function fetchSkillsInfo() {
  loading.value = true
  error.value = ''
  try {
    const params: Record<string, string> = {}
    if (props.userId) {
      params.user_id = props.userId
    }
    const response = await axios.get<SkillApiResponse[]>('/api/skills_info', { params })
    const apiList = Array.isArray(response.data) ? response.data : []
    skillsInfoList.value = apiList.map((skill: any) => ({
      name: skill.name,
      description: skill.description || '',
      // 后端多为 type: user；统一成前端的 personal
      type:
        skill.type === 'user' || skill.type === 'personal' ? 'personal' : 'system',
      folder:
        skill.type === 'user' || skill.type === 'personal'
          ? skill.folder
          : undefined
    }))
  } catch (err) {
    console.error('获取技能信息失败:', err)
    error.value = 'Failed to load skills information'
  } finally {
    loading.value = false
  }
}

function handleOverlayClick() {
  // 点击遮罩层时不关闭，保持和现有弹窗一致
}

onMounted(() => {
  fetchSkillsInfo()
})
</script>

<style scoped>
.skills-option-overlay {
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

.skills-option-container {
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
.skills-option-header {
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

.skills-option-header h2 {
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

/* ── Content ── */
.skills-content {
  flex: 1;
  overflow-y: auto;
  padding: 24px 32px 28px;
  background: #f5f5f7;
  font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Helvetica Neue', 'PingFang SC', sans-serif;
}

.personal-toolbar {
  margin-bottom: 18px;
}

.personal-toolbar-inner {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 14px 16px;
  padding: 14px 16px;
  background: #ffffff;
  border: 1px solid rgba(0, 0, 0, 0.05);
  border-radius: 12px;
  box-shadow:
    0 1px 2px rgba(0, 0, 0, 0.03),
    0 0 0 0.5px rgba(0, 0, 0, 0.02);
}

.toolbar-upload-label {
  margin: 0;
  flex: 1;
  min-width: 180px;
  font-size: 0.8125rem;
  line-height: 1.45;
  color: #6e6e73;
  font-weight: 400;
  letter-spacing: -0.005em;
}

.folder-input-hidden {
  position: absolute;
  width: 0;
  height: 0;
  opacity: 0;
  pointer-events: none;
}

.upload-folder-btn {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  padding: 8px 18px;
  min-height: 34px;
  background: #1d1d1f;
  color: #ffffff;
  border: none;
  border-radius: 980px;
  cursor: pointer;
  font-family: inherit;
  font-weight: 500;
  font-size: 0.8125rem;
  letter-spacing: -0.005em;
  transition: background 0.18s ease, opacity 0.18s ease, transform 0.2s ease;
}

.upload-folder-btn-icon {
  flex-shrink: 0;
  opacity: 0.95;
}

.upload-folder-btn-spinner {
  width: 14px;
  height: 14px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin 0.75s linear infinite;
}

.upload-folder-btn:hover:not(:disabled) {
  background: #000000;
}

.upload-folder-btn:active:not(:disabled) {
  transform: scale(0.97);
}

.upload-folder-btn:focus-visible {
  outline: none;
  box-shadow: 0 0 0 3px rgba(0, 0, 0, 0.12);
}

.upload-folder-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.upload-hint {
  margin: 10px 4px 0;
  font-size: 0.75rem;
  font-weight: 400;
  letter-spacing: -0.005em;
}

.upload-hint[data-tone='success'] {
  color: #1d8348;
}

.upload-hint[data-tone='error'] {
  color: #d70015;
}

.upload-hint[data-tone='neutral'] {
  color: #86868b;
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

/* ── Skills Grouped List ── */
.skills-list {
  display: flex;
  flex-direction: column;
  gap: 0;
  background: #ffffff;
  border-radius: 14px;
  border: 1px solid rgba(0, 0, 0, 0.05);
  box-shadow:
    0 1px 2px rgba(0, 0, 0, 0.03),
    0 0 0 0.5px rgba(0, 0, 0, 0.02);
  overflow: hidden;
}

.skill-item + .skill-item {
  border-top: 1px solid rgba(0, 0, 0, 0.05);
}

.skill-shell {
  border: none;
  border-radius: 0;
  background: transparent;
  box-shadow: none;
  overflow: hidden;
  transition: background 0.18s ease;
}

.skill-shell:hover {
  background: rgba(0, 0, 0, 0.02);
}

.skill-header {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: stretch;
  padding: 12px 14px 12px 18px;
  background: transparent;
}

.skill-header-main {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
  flex: 1;
  min-width: 0;
  cursor: pointer;
  padding: 4px 0;
}

.skill-delete-btn {
  flex-shrink: 0;
  align-self: center;
  padding: 6px 14px;
  font-family: inherit;
  font-size: 0.75rem;
  font-weight: 500;
  letter-spacing: -0.005em;
  color: #d70015;
  background: transparent;
  border: 1px solid rgba(215, 0, 21, 0.18);
  border-radius: 980px;
  cursor: pointer;
  transition: background 0.18s ease, border-color 0.18s ease, transform 0.2s ease;
}

.skill-delete-btn:hover:not(:disabled) {
  background: rgba(215, 0, 21, 0.06);
  border-color: rgba(215, 0, 21, 0.32);
}

.skill-delete-btn:active:not(:disabled) {
  transform: scale(0.97);
}

.skill-delete-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.skill-header-text {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.skill-name {
  margin: 0;
  font-size: 0.9375rem;
  font-weight: 500;
  color: #1d1d1f;
  letter-spacing: -0.012em;
  line-height: 1.35;
}

.skill-description {
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

.skill-description.expanded {
  overflow: visible;
  text-overflow: unset;
  display: block;
  -webkit-line-clamp: unset;
  line-clamp: unset;
}

.skill-toggle {
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

.skill-shell:hover .skill-toggle {
  background: rgba(0, 0, 0, 0.05);
  color: #1d1d1f;
}

.toggle-icon {
  transition: transform 0.25s cubic-bezier(0.32, 0.72, 0, 1);
}

.toggle-icon.expanded {
  transform: rotate(180deg);
}

/* 响应式设计 */
@media (max-width: 640px) {
  .skills-option-container {
    width: 95%;
    max-height: 90vh;
    border-radius: 16px;
  }

  .skills-option-header {
    padding: 22px 20px 16px;
  }

  .skills-option-header h2 {
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

  .skills-content {
    padding: 20px 20px 24px;
  }
}
</style>

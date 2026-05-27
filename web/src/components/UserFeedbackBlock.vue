<template>
  <div class="ufb-card" :class="{ 'ufb-card--disabled': disabled }">
    <div class="ufb-header">
      <span class="ufb-badge">待你确认</span>
      <p class="ufb-desc">{{ payload.description || '请完成以下问题' }}</p>
      <p v-if="normalizedQuestions.length > 1" class="ufb-meta">
        共 {{ normalizedQuestions.length }} 项，填写完成后统一提交
      </p>
    </div>

    <div class="ufb-questions">
      <section
        v-for="(question, qIndex) in normalizedQuestions"
        :key="question.id"
        class="ufb-question"
      >
        <div class="ufb-question-head">
          <span class="ufb-question-index">{{ qIndex + 1 }}</span>
          <h3 class="ufb-question-prompt">{{ question.prompt }}</h3>
        </div>

        <div v-if="question.interaction_type === 'choice'" class="ufb-question-body">
          <p class="ufb-hint">
            {{ question.choice_mode === 'multiple' ? '可多选' : '单选' }}
          </p>

          <div class="ufb-options">
            <button
              v-for="opt in question.options || []"
              :key="`${question.id}-${opt.key}`"
              type="button"
              class="ufb-option"
              :class="{ 'ufb-option--active': isOptionSelected(question.id, opt.key) }"
              :disabled="disabled"
              @click="toggleOption(question, opt.key)"
            >
              <span class="ufb-option-key">{{ opt.key }}</span>
              <span class="ufb-option-label">{{ opt.label }}</span>
            </button>
          </div>

          <div v-if="question.allow_custom_input" class="ufb-custom">
            <label class="ufb-custom-label">或自行填写</label>
            <textarea
              :value="getCustomInput(question.id)"
              class="ufb-input"
              :placeholder="question.custom_input_placeholder || '其他（请说明）'"
              :disabled="disabled"
              rows="2"
              @input="setCustomInput(question.id, ($event.target as HTMLTextAreaElement).value)"
            />
          </div>
        </div>

        <div v-else class="ufb-question-body">
          <textarea
            :value="getTextInput(question.id)"
            class="ufb-input ufb-input--main"
            :placeholder="question.placeholder || '请输入…'"
            :disabled="disabled"
            rows="3"
            @input="setTextInput(question.id, ($event.target as HTMLTextAreaElement).value)"
          />
        </div>
      </section>
    </div>

    <div class="ufb-footer">
      <span v-if="disabled && submittedAnswer" class="ufb-submitted">
        已提交
      </span>
      <button
        type="button"
        class="ufb-submit"
        :disabled="disabled || !canSubmit"
        @click="handleSubmit"
      >
        {{ disabled ? '已确认' : '确认提交' }}
      </button>
    </div>
  </div>
</template>

<script lang="ts" setup>
import { computed, reactive, watch } from 'vue'

export interface FeedbackQuestion {
  id: string
  interaction_type: 'choice' | 'input'
  prompt: string
  choice_mode?: 'single' | 'multiple'
  options?: Array<{ key: string; label: string; value: string }>
  allow_custom_input?: boolean
  custom_input_placeholder?: string
  placeholder?: string
}

export interface UserFeedbackPayload {
  description?: string
  questions?: FeedbackQuestion[]
  submitted?: boolean
  /** 兼容旧版单题结构 */
  interaction_type?: 'choice' | 'input'
  prompt?: string
  choice_mode?: 'single' | 'multiple'
  options?: Array<{ key: string; label: string; value: string }>
  allow_custom_input?: boolean
  custom_input_placeholder?: string
  placeholder?: string
}

interface QuestionState {
  selectedKeys: string[]
  customInput: string
  textInput: string
}

const props = defineProps<{
  payload: UserFeedbackPayload
  disabled?: boolean
  submittedAnswer?: string
}>()

const emit = defineEmits<{
  submit: [answer: string]
}>()

const questionStates = reactive<Record<string, QuestionState>>({})

function createEmptyState(): QuestionState {
  return { selectedKeys: [], customInput: '', textInput: '' }
}

function normalizePayload(payload: UserFeedbackPayload): FeedbackQuestion[] {
  if (payload.questions?.length) {
    return payload.questions.map((q, index) => ({
      ...q,
      id: q.id || String(index + 1),
    }))
  }
  if (payload.prompt && payload.interaction_type) {
    return [
      {
        id: '1',
        interaction_type: payload.interaction_type,
        prompt: payload.prompt,
        choice_mode: payload.choice_mode,
        options: payload.options,
        allow_custom_input: payload.allow_custom_input,
        custom_input_placeholder: payload.custom_input_placeholder,
        placeholder: payload.placeholder,
      },
    ]
  }
  return []
}

const normalizedQuestions = computed(() => normalizePayload(props.payload))

function resetStates() {
  Object.keys(questionStates).forEach((key) => delete questionStates[key])
  normalizedQuestions.value.forEach((question) => {
    questionStates[question.id] = createEmptyState()
  })
}

watch(
  () => props.payload,
  () => resetStates(),
  { immediate: true, deep: true },
)

function getState(questionId: string): QuestionState {
  if (!questionStates[questionId]) {
    questionStates[questionId] = createEmptyState()
  }
  return questionStates[questionId]
}

function isOptionSelected(questionId: string, key: string): boolean {
  return getState(questionId).selectedKeys.includes(key)
}

function toggleOption(question: FeedbackQuestion, key: string) {
  if (props.disabled) return
  const state = getState(question.id)
  if (question.choice_mode === 'multiple') {
    if (state.selectedKeys.includes(key)) {
      state.selectedKeys = state.selectedKeys.filter((item) => item !== key)
    } else {
      state.selectedKeys = [...state.selectedKeys, key]
    }
    return
  }
  state.selectedKeys = [key]
}

function getCustomInput(questionId: string): string {
  return getState(questionId).customInput
}

function setCustomInput(questionId: string, value: string) {
  getState(questionId).customInput = value
}

function getTextInput(questionId: string): string {
  return getState(questionId).textInput
}

function setTextInput(questionId: string, value: string) {
  getState(questionId).textInput = value
}

function isQuestionValid(question: FeedbackQuestion): boolean {
  const state = getState(question.id)
  if (question.interaction_type === 'input') {
    return state.textInput.trim().length > 0
  }

  const hasSelection = state.selectedKeys.length > 0
  const hasCustom = question.allow_custom_input && state.customInput.trim().length > 0
  if (question.choice_mode === 'multiple') {
    return hasSelection || hasCustom
  }
  return hasSelection || hasCustom
}

const canSubmit = computed(() => {
  if (!normalizedQuestions.value.length) return false
  return normalizedQuestions.value.every((question) => isQuestionValid(question))
})

function buildQuestionAnswer(question: FeedbackQuestion): string {
  const state = getState(question.id)
  if (question.interaction_type === 'input') {
    return state.textInput.trim()
  }

  const parts: string[] = []
  for (const key of state.selectedKeys) {
    const opt = (question.options || []).find((item) => item.key === key)
    if (opt?.value) parts.push(opt.value)
  }
  const custom = state.customInput.trim()
  if (custom) parts.push(custom)

  if (question.choice_mode === 'multiple') {
    return parts.join('；')
  }
  return parts[0] || ''
}

function buildAnswer(): string {
  return normalizedQuestions.value
    .map((question, index) => {
      const answer = buildQuestionAnswer(question)
      return `【${index + 1}】${question.prompt}\n${answer}`
    })
    .join('\n\n')
}

function handleSubmit() {
  if (!canSubmit.value || props.disabled) return
  emit('submit', buildAnswer())
}
</script>

<style scoped>
.ufb-card {
  width: 100%;
  max-width: 680px;
  box-sizing: border-box;
  margin: 6px 0 10px;
  padding: 10px 12px 10px;
  border-radius: 10px;
  border: 1px solid rgba(0, 0, 0, 0.08);
  background: rgba(255, 255, 255, 0.98);
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.03);
}

.ufb-card--disabled {
  opacity: 0.78;
}

.ufb-header {
  margin-bottom: 8px;
  padding-bottom: 8px;
  border-bottom: 1px solid rgba(0, 0, 0, 0.06);
}

.ufb-badge {
  display: inline-flex;
  align-items: center;
  padding: 1px 8px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 500;
  color: rgb(82, 82, 82);
  background: #fafafa;
  border: 1px solid rgba(0, 0, 0, 0.08);
}

.ufb-desc {
  margin: 6px 0 0;
  font-size: 12.5px;
  color: rgb(110, 110, 110);
  line-height: 1.45;
}

.ufb-meta {
  margin: 4px 0 0;
  font-size: 11px;
  color: rgb(140, 140, 140);
}

.ufb-questions {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.ufb-question {
  padding: 8px 10px;
  border-radius: 8px;
  background: rgb(250, 250, 250);
  border: 1px solid rgba(0, 0, 0, 0.05);
}

.ufb-question-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.ufb-question-index {
  flex-shrink: 0;
  width: 18px;
  height: 18px;
  border-radius: 5px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 600;
  color: rgb(110, 110, 110);
  background: rgba(0, 0, 0, 0.05);
}

.ufb-question-prompt {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
  color: rgb(33, 33, 33);
  line-height: 1.35;
}

.ufb-hint {
  margin: 0 0 5px;
  font-size: 11px;
  color: rgb(140, 140, 140);
}

.ufb-options {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.ufb-option {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  max-width: 100%;
  padding: 4px 8px 4px 4px;
  border-radius: 6px;
  border: 1px solid rgba(0, 0, 0, 0.07);
  background: #fff;
  cursor: pointer;
  text-align: left;
  transition: background 0.14s ease, border-color 0.14s ease;
}

.ufb-option:hover:not(:disabled) {
  background: rgba(0, 0, 0, 0.03);
  border-color: rgba(0, 0, 0, 0.1);
}

.ufb-option--active {
  background: rgba(0, 0, 0, 0.06);
  border-color: rgba(0, 0, 0, 0.14);
}

.ufb-option:disabled {
  cursor: not-allowed;
}

.ufb-option-key {
  flex-shrink: 0;
  min-width: 18px;
  height: 18px;
  padding: 0 4px;
  border-radius: 4px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 600;
  color: rgb(110, 110, 110);
  background: rgba(0, 0, 0, 0.05);
}

.ufb-option--active .ufb-option-key {
  color: rgb(33, 33, 33);
  background: rgba(0, 0, 0, 0.1);
}

.ufb-option-label {
  font-size: 12px;
  color: rgb(61, 61, 61);
  line-height: 1.3;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.ufb-option--active .ufb-option-label {
  color: rgb(33, 33, 33);
  font-weight: 500;
}

.ufb-custom {
  margin-top: 6px;
}

.ufb-custom-label {
  display: block;
  margin-bottom: 4px;
  font-size: 11px;
  color: rgb(110, 110, 110);
}

.ufb-input {
  width: 100%;
  box-sizing: border-box;
  padding: 6px 9px;
  border-radius: 6px;
  border: 1px solid rgba(0, 0, 0, 0.08);
  background: #fff;
  font-size: 12.5px;
  color: rgb(33, 33, 33);
  line-height: 1.4;
  resize: vertical;
  min-height: 32px;
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
  font-family: inherit;
}

.ufb-input:focus {
  outline: none;
  border-color: rgba(0, 0, 0, 0.18);
  box-shadow: 0 0 0 2px rgba(0, 0, 0, 0.04);
}

.ufb-input:disabled {
  background: rgb(245, 245, 245);
  cursor: not-allowed;
}

.ufb-input--main {
  min-height: 56px;
}

.ufb-footer {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid rgba(0, 0, 0, 0.06);
}

.ufb-submitted {
  flex: 1;
  min-width: 0;
  font-size: 11px;
  color: rgb(140, 140, 140);
}

.ufb-submit {
  padding: 5px 14px;
  border-radius: 7px;
  border: 1px solid rgba(0, 0, 0, 0.08);
  background: rgb(33, 33, 33);
  color: #fff;
  font-size: 12.5px;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.16s ease, opacity 0.16s ease;
  font-family: inherit;
}

.ufb-submit:hover:not(:disabled) {
  background: rgb(61, 61, 61);
}

.ufb-submit:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}
</style>

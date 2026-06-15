<template>
  <div class="conversation-container">
    <div class="conversation-answer">
      <div class="answer-container" :class="{'no-history': !groupedMessages.length && !streamingBlocks.length && !showPlanInStreamingRow}" ref="answerContainer" @scroll="handleScroll">
        <!-- 有对话消息时显示消息列表 -->
        <template v-if="groupedMessages.length || streamingBlocks.length || showPlanInStreamingRow">
          <template v-for="(group, index) in groupedMessages" :key="index">
            <!-- 用户消息 -->
            <div v-if="group.role === 'user'" class="answer-single-me-agent">
              <div class="user-message-column">
                <template v-for="(message, uMsgIndex) in group.messages" :key="uMsgIndex">
                  <div
                    v-if="isUserTextMessage(message)"
                    class="text-message-wrapper text-message-wrapper--user"
                    :class="{
                      'text-message-wrapper--user-editing':
                        editingUserMessageId === message.id,
                    }"
                  >
                    <div
                      class="answer-me-content"
                      :class="{ 'answer-me-content--editing': editingUserMessageId === message.id }"
                    >
                      <template v-if="editingUserMessageId === message.id">
                        <div class="user-edit-box">
                          <div class="input-total">
                            <textarea
                              :ref="setUserEditTextareaRef"
                              v-model="editingUserDraft"
                              class="input_field"
                              rows="1"
                              @input="adjustUserEditTextareaHeight"
                              @keydown.enter.exact.prevent="confirmEditUser"
                            />
                          </div>
                          <div class="user-edit-actions">
                            <button type="button" class="user-edit-btn-cancel" @click="cancelEditUser">取消</button>
                            <button
                              type="button"
                              class="user-edit-btn-send"
                              :disabled="isConfirmEditPending"
                              @click="confirmEditUser"
                            >
                              发送
                            </button>
                          </div>
                        </div>
                      </template>
                      <template v-else>
                        <div
                          class="p-content-markdown"
                          v-html="renderMarkdown(message.content)"
                        ></div>
                      </template>
                    </div>
                    <div class="message-actions message-actions--user">
                      <button
                        v-if="message.id && editingUserMessageId !== message.id"
                        type="button"
                        class="message-action-btn"
                        title="编辑"
                        @click="startEditUserMessage(message)"
                      >
                        <img :src="EditIcon" alt="" class="message-action-btn-icon" />
                      </button>
                      <button
                        type="button"
                        class="message-action-btn"
                        :title="copiedStates.has(message.created_at) ? '已复制' : '复制'"
                        @click="copyToClipboard(message.content, message.created_at)"
                      >
                        <img
                          :src="copiedStates.has(message.created_at) ? DoneIcon : ContentCopyIcon"
                          alt=""
                          class="message-action-btn-icon"
                        />
                      </button>
                    </div>
                  </div>
                  <div v-else-if="message.type === 'file'" class="user-uploaded-files">
                    <div class="selected-files selected-files--history">
                      <div
                        v-for="(fileName, fIdx) in parseUserFileNames(message)"
                        :key="`${message.created_at}-${fIdx}-${fileName}`"
                        class="selected-file-item"
                      >
                        <img
                          class="selected-file-icon"
                          :src="getFileIconUrlForName(fileName)"
                          :alt="fileName"
                        />
                        <div class="selected-file-name" :title="fileName">{{ fileName }}</div>
                      </div>
                    </div>
                  </div>
                </template>
              </div>
            </div>
            
            <!-- AI消息 -->
            <div v-else-if="['assistant', 'event'].includes(group.role)" class="answer-single-robot">
              <!-- <template v-if="index === 0 || groupedMessages[index - 1].role === 'user'">
                <div class="answer-robot-icon">
                  <img class="icon-robot" src="@/assets/images/mengya_chat.svg" alt="robot-logo" />
                </div>
              </template> -->
              <div class="answer-robot-container">
                <template v-for="(message, msgIndex) in group.messages" :key="msgIndex">
                  <div v-if="message.type === 'event'" class="answer-robot-event">
                    {{ message.content }}
                  </div>

                  <div v-else-if="message.type === 'reasoner_content'" class="answer-robot-reasoner">
                    <div class="p-content-markdown" v-html="renderMarkdown(message.content ?? '')"></div>
                  </div>

                  <div v-else-if="(message.type === 'get_tools' || message.type === 'get_agents') && message.tool_calls" class="answer-robot-tool-wrapper">
                    <!-- 历史消息的 tool_calls 显示 content；流式输出的 tool_calls 不显示 content -->
                    <div v-if="!message.from_streaming && message.content && message.content.trim()" class="text-message-wrapper">
                      <div class="answer-robot-content">
                        <div class="p-content-markdown" v-html="renderMarkdown(message.content)"></div>
                      </div>
                    </div>
                    <div class="answer-robot-tool answer-robot-tool--with-ws">
                      <WebSearchBlock
                        v-if="getWebSearchCalls(message.tool_calls, message.tool_call_id).length"
                        :calls="getWebSearchCalls(message.tool_calls, message.tool_call_id)"
                        :tool-messages="toolMessages"
                        :agent-message-list="agent_message_list"
                        @open-web-preview="handleOpenWebPreview"
                      />
                      <ToolCallsBlock
                        v-if="getGenericToolCallItems(message.tool_calls, message.tool_call_id, message.type).length"
                        :calls="getGenericToolCallItems(message.tool_calls, message.tool_call_id, message.type)"
                        :tool-messages="toolMessages"
                        :agent-message-list="agent_message_list"
                        @highlight="handleHighlight"
                        @unhighlight="handleUnhighlight"
                        @scroll-to="handleScrollTo"
                        @open-file-preview="handleOpenFilePreview"
                      />
                    </div>
                  </div>

                  <div v-else-if="message.type === 'user_feedback' && message.table" class="user-feedback-wrapper">
                    <UserFeedbackBlock
                      :payload="(message.table as unknown as UserFeedbackPayload)"
                      :disabled="isFeedbackDisabled(message)"
                      :submitted-answer="getFeedbackSubmittedAnswer(message)"
                      @submit="(answer) => handleFeedbackSubmit(message, answer)"
                    />
                  </div>

                  <div v-else-if="message.type === 'text'" class="text-message-wrapper">
                    <div class="answer-robot-content">
                      <div class="p-content-markdown" v-html="renderMarkdown(message.content ?? '')">
                      </div>
                    </div>
                    <div class="message-actions">
                      <button
                        type="button"
                        class="message-action-btn"
                        :title="copiedStates.has(message.created_at) ? '已复制' : '复制'"
                        @click="copyToClipboard(message.content, message.created_at)"
                      >
                        <img
                          :src="copiedStates.has(message.created_at) ? DoneIcon : ContentCopyIcon"
                          alt=""
                          class="message-action-btn-icon"
                        />
                      </button>
                    </div>
                  </div>
  
                    <div v-else-if="message.type === 'error'" class="answer-robot-error">
                      <img src="@/assets/images/error_icon.svg" alt="Error Icon" class="error-icon" />
                      {{ message.content }}
                    </div>
                </template>
              </div>
            </div>
          </template>
          
          <!-- 流式消息显示区域 - 按顺序显示每个消息块 -->
          <div v-if="streamingBlocks.length || showPlanInStreamingRow" class="answer-single-robot">
            <!-- <div class="answer-robot-icon">
              <img class="icon-robot" src="@/assets/images/mengya_chat.svg" alt="robot-logo" />
            </div> -->
            <div class="answer-robot-container">
              <BlueprintBlock
                v-if="showPlanInStreamingRow"
                :content="planStreamContent"
                pending
              />
              <!-- Loading状态显示 -->
              <div v-if="isLoading" class="answer-robot-loading">
                <div class="loading-spinner"></div>
              </div>
              
              <!-- 超时错误显示 -->
              <div v-if="timeoutError" class="answer-robot-error">
                {{ timeoutError }}
              </div>
              <template v-for="(block, index) in streamingBlocks" :key="index">
                <div v-if="block.type === 'event'" class="answer-robot-event">
                  {{ block.content }}
                </div>
                <div v-else-if="block.type === 'reasoner_content'" class="answer-robot-reasoner">
                  <div class="p-content-markdown" v-html="renderMarkdown(block.content ?? '')"></div>
                </div>
                <div v-else-if="(block.type === 'get_tools' || block.type === 'get_agents') && block.tool_calls" class="answer-robot-tool answer-robot-tool--with-ws">
                    <WebSearchBlock
                      v-if="getWebSearchCalls(block.tool_calls, block.tool_call_id).length"
                      :calls="getWebSearchCalls(block.tool_calls, block.tool_call_id)"
                      :tool-messages="toolMessages"
                      :agent-message-list="agent_message_list"
                      :pending="isStreamingToolBlockPending(block, index)"
                      @open-web-preview="handleOpenWebPreview"
                    />
                    <ToolCallsBlock
                      v-if="getGenericToolCallItems(block.tool_calls, block.tool_call_id, block.type).length"
                      :calls="getGenericToolCallItems(block.tool_calls, block.tool_call_id, block.type)"
                      :tool-messages="toolMessages"
                      :agent-message-list="agent_message_list"
                      :pending="isStreamingToolBlockPending(block, index)"
                      @highlight="handleHighlight"
                      @unhighlight="handleUnhighlight"
                      @scroll-to="handleScrollTo"
                      @open-file-preview="handleOpenFilePreview"
                    />
                </div>
                <div v-else-if="block.type === 'user_feedback' && block.table" class="user-feedback-wrapper">
                  <UserFeedbackBlock
                    :payload="(block.table as unknown as UserFeedbackPayload)"
                    :disabled="isFeedbackDisabledFromBlock(block)"
                    :submitted-answer="getFeedbackSubmittedAnswerFromBlock(block)"
                    @submit="(answer) => handleFeedbackSubmitFromBlock(block, answer)"
                  />
                </div>
                <div v-else-if="block.type === 'text'" class="text-message-wrapper">
                  <div class="answer-robot-content">
                    <div class="p-content-markdown" v-html="renderMarkdown(block.content ?? '')">
                    </div>
                  </div>
                  <div class="message-actions">
                    <button
                      type="button"
                      class="message-action-btn"
                      :title="copiedStates.has(block.created_at) ? '已复制' : '复制'"
                      @click="copyToClipboard(block.content, block.created_at)"
                    >
                      <img
                        :src="copiedStates.has(block.created_at) ? DoneIcon : ContentCopyIcon"
                        alt=""
                        class="message-action-btn-icon"
                      />
                    </button>
                  </div>
                </div>
  
                  <div v-else-if="block.type === 'error'" class="answer-robot-error">
                    <img src="@/assets/images/error_icon.svg" alt="Error Icon" class="error-icon" />
                    {{ block.content }}
                  </div>
              </template>
            </div>
          </div>
        </template>

        <!-- 无对话历史时显示欢迎界面 -->
        <template v-else>
          <!-- Soul 模式欢迎页 -->
          <div
            v-if="chatMode === 'soulprout'"
            :style="{ display: isVisible ? 'flex' : 'none' }"
            class="no-history-container no-history-container--soul"
          >
            <div class="no-history-title-row">
              <p :class="['no-history-content1', { active: showContent1 }]">越用越懂你的AI伙伴</p>
            </div>
            <div :class="['soul-channel-desc', { active: showContent2 }]">
              <div class="soul-channel-line">
                <span class="soul-channel-desc-label">下载应用，体验多渠道接入：</span>
                <div class="soul-channel-list">
                  <div
                    v-for="channel in soulChannels"
                    :key="channel.name"
                    class="soul-channel-item"
                    :class="{ 'soul-channel-item--unsupported': !channel.supported }"
                  >
                    <span
                      class="soul-channel-box"
                      :class="{ 'soul-channel-box--checked': channel.supported }"
                      aria-hidden="true"
                    >
                      <svg
                        v-if="channel.supported"
                        class="soul-channel-box-icon"
                        viewBox="0 0 12 12"
                        fill="none"
                        xmlns="http://www.w3.org/2000/svg"
                      >
                        <path
                          d="M2.5 6L5 8.5L9.5 3.5"
                          stroke="currentColor"
                          stroke-width="2"
                          stroke-linecap="round"
                          stroke-linejoin="round"
                        />
                      </svg>
                    </span>
                    <span class="soul-channel-name">{{ channel.name }}</span>
                  </div>
                  <span class="soul-channel-ellipsis" aria-hidden="true">…</span>
                </div>
              </div>
            </div>
          </div>
          <!-- Task 模式欢迎页 -->
          <div
            v-else
            :style="{ display: isVisible ? 'flex' : 'none' }"
            class="no-history-container"
            @mouseenter="showSuggestions = true"
          >
            <div class="no-history-title-row" @mouseenter="showViewHint = false">
              <p :class="['no-history-content1', { active: showContent1 }]">你好{{ username }}，需要我做些什么？🌱</p>
              <span v-if="showViewHint" :class="['view-hint', { active: showHintActive }]">👈 查看这里</span>
            </div>
            <div class="suggestion-buttons" v-if="showSuggestions">
              <div class="suggestion-cards suggestion-cards-two">
                <div class="suggestion-card suggestion-card-general">
                  <h3 class="card-title">通用模式</h3>
                  <ul class="example-list">
                    <li @click="prefillInput('对AI行业进行深度市场调研，包括最新趋势和竞争分析，整合成一份详细的调研报告')">深度调研：对AI行业进行深度市场调研</li>
                    <li @click="prefillInput('本周我的工作内容有：xxx，帮我写一份x页的周报PPT，风格为简洁商务风')">生成PPT：帮我写一份周报PPT</li>
                    <li @click="prefillInput('比较最新款iPhone17和小米17手机的性能、价格和用户评价')">商品对比：iPhone17和小米17对比</li>
                    <li @click="prefillInput('帮我规划一次为期7天的新疆旅行，包括景点、住宿、交通等')">旅游规划：规划一次7天的新疆旅行</li>
                  </ul>
                </div>
                <div class="suggestion-card suggestion-card-agent" @click="handleCreateAgentClick">
                  <h3 class="card-title">专家模式</h3>
                  <p class="card-desc"><span class="card-desc-main"><span class="card-desc-highlight">5分钟</span><span class="card-desc-sub">定制你的Agent专家/团队</span></span><span class="card-desc-slogan">完成后自动保存至&nbsp&nbsp&nbsp<strong>"专家库 "</strong></span></p>
                </div>
              </div>
            </div>
          </div>
        </template>
      </div>
      
      <MessageInput 
        ref="messageInput"
        :chat_request="chat_request"
        :model_list="model_list"
        :isGenerating="isStreaming"
        :agent_card_list="agent_card_list"
        :userId="userId"
        :kb_list="kb_list"
        :chatMode="chatMode"
        @sendMessage="handleSendMessage" 
        @changeToolsUse="handleToolsUseChange"
        @changeSkillsUse="handleSkillsUseChange"
        @selectModel="handleSelectModel"
        @selectAgent="handleSelectAgent"
        @stopGeneration="handleStopGeneration"
        @loadAgents="getAgentCardList"
        @loadKBs="getKBList"
        @selectKB="handleSelectKB"
      />
    </div>
    <div class="conversation-view">
      <div class="conversation-view-block">
      </div>
    </div>
  </div>
</template>

<script lang="ts" setup>
import { ref, nextTick, computed, watch, onMounted, onUnmounted, onUpdated } from 'vue'
import MessageInput from '../components/MessageInput.vue'
import ToolCallsBlock from './ToolCallsBlock.vue'
import BlueprintBlock from './BlueprintBlock.vue'
import WebSearchBlock from './WebSearchBlock.vue'
import UserFeedbackBlock from './UserFeedbackBlock.vue'
import type { UserFeedbackPayload } from './UserFeedbackBlock.vue'
import type { WebSearchCallItem } from './WebSearchBlock.vue'
import { buildGenericToolCallItems, buildWebSearchCallItems } from '../utils/toolCallDisplay'
import {
  getFileIconUrlForName,
  isUserTextMessageType,
  parseUserFileNames,
} from '../utils/userFileDisplay'
import type { ConversationBase, ChatRequest, AgentMessage, ToolCalls } from '../types/interface.ts'
import { AgentCard } from '../types/interface.ts'
import axios from 'axios'

import MarkdownIt from 'markdown-it'
import hljs from 'highlight.js'
import 'highlight.js/styles/github.css' // 选择你喜欢的代码高亮主题
// @ts-ignore
import EditIcon from '@/assets/images/edit.svg?url'
// @ts-ignore
import ContentCopyIcon from '@/assets/images/content_copy.svg?url'
// @ts-ignore
import DoneIcon from '@/assets/images/done.svg?url'
// @ts-ignore
import TravelImg from '@/assets/images/travel.png'
// @ts-ignore
import SearchImg from '@/assets/images/deep_search_show.png'
// @ts-ignore
import ToolsImg from '@/assets/images/ppt_show.png'
// @ts-ignore
import BuyImg from '@/assets/images/buy.png'

interface Props {
  agent_message_list: AgentMessage[];
  chat_request: any;
  currentStreamingMessage: AgentMessage | null;
  isGenerating?: boolean;
  planStreamContent?: string;
  isLoading: boolean;           // 新增
  timeoutError: string;         // 新增
  model_list: Record<string, string[]>;
  userId: string;
  username: string;
  /** 父组件在 reload_history 时递增，用于清空流式块 UI */
  reloadStreamingUiToken?: number;
  /** 切换模式且无历史消息时递增，用于重播欢迎页动画 */
  welcomeAnimationToken?: number;
  /** 当前聊天模式：'soulprout' | 'task'；Soulprout 模式下隐藏高级设置入口 */
  chatMode?: 'soulprout' | 'task';
  /** 工具消息（含工具调用结果），用于 web_search 展示 */
  toolMessages?: AgentMessage[];
}

interface StreamBlock {
  type: string;
  role: string;
  content?: string;
  tool_calls?: [ToolCalls];
  tool_call_id?: string;
  created_at: number;
  table?: Record<string, unknown>;
}

interface MessageGroup {
  role: string;
  messages: AgentMessage[];
}

const props = withDefaults(defineProps<Props>(), {
  isGenerating: false,
  planStreamContent: '',
  reloadStreamingUiToken: 0,
  welcomeAnimationToken: 0,
  chatMode: 'soulprout',
  toolMessages: () => [],
})

// ─── web_search 独立展示；其余工具由 ToolCallsBlock 负责 ─────────────────

function getWebSearchCalls(
  toolCalls: { function?: { name?: string; arguments?: string }; id?: string }[] | undefined,
  fallbackId?: string,
): WebSearchCallItem[] {
  return buildWebSearchCallItems(toolCalls, fallbackId)
}

function getGenericToolCallItems(
  toolCalls: { function?: { name?: string; arguments?: string }; id?: string }[] | undefined,
  fallbackId?: string,
  messageType?: string,
) {
  return buildGenericToolCallItems(toolCalls, fallbackId, messageType)
}
const emit = defineEmits<{
  sendMessage: [message: string, files: File[], options?: { input_message_id?: string; user_feedback?: boolean }]
  changeToolsUse: []
  selectModel: [model_source: string, model: string]
  selectAgent: [agent_use: string | null, agent_id: string[] | string | null]
  stopGeneration: []
  loadAgents: []
  highlight: [id: string]
  unhighlight: []
  scrollTo: [id: string]
  openWebPreview: [url: string]
  openFilePreview: [filePath: string]
}>()

// 从消息中获取 tool_call_id（优先使用 tool_calls[0].id，否则使用 tool_call_id，最后使用 created_at）
const getToolCallId = (message: AgentMessage): string => {
  if (message.tool_calls && message.tool_calls.length > 0 && message.tool_calls[0].id) {
    return message.tool_calls[0].id
  }
  return message.tool_call_id || String(message.created_at)
}

// 从流式块中获取 tool_call_id
const getToolCallIdFromBlock = (block: StreamBlock): string => {
  if (block.tool_calls && block.tool_calls.length > 0 && block.tool_calls[0].id) {
    return block.tool_calls[0].id
  }
  return block.tool_call_id || String(block.created_at)
}

const handleHighlight = (id?: string) => {
  if (id) emit('highlight', id)
}

const handleUnhighlight = () => emit('unhighlight')

const handleScrollTo = (toolCallId?: string) => {
  if (toolCallId) emit('scrollTo', toolCallId)
}

const handleOpenWebPreview = (url: string) => {
  if (url) emit('openWebPreview', url)
}

const handleOpenFilePreview = (filePath: string) => {
  if (filePath) emit('openFilePreview', filePath)
}

const submittedFeedbackAnswers = ref<Record<string, string>>({})

function getFeedbackKey(message: Pick<AgentMessage, 'tool_call_id' | 'created_at'>): string {
  return message.tool_call_id || String(message.created_at)
}

function hasUserAnswerAfterFeedback(message: AgentMessage): boolean {
  const key = getFeedbackKey(message)
  const idx = props.agent_message_list.findIndex(
    (m) => m.type === 'user_feedback' && m.table && getFeedbackKey(m) === key,
  )
  if (idx < 0) return false
  for (let i = idx + 1; i < props.agent_message_list.length; i++) {
    const next = props.agent_message_list[i]
    if (next.role === 'user' && next.type === 'user_feedback') {
      return true
    }
    if (next.role === 'user' && next.type === 'text' && (next.content || '').trim()) {
      return true
    }
    if (next.role === 'assistant' && next.type === 'get_tools') {
      break
    }
  }
  return false
}

function getFeedbackSubmittedAnswer(_message: AgentMessage): string {
  return ''
}

function isFeedbackDisabled(message: AgentMessage): boolean {
  const key = getFeedbackKey(message)
  if (submittedFeedbackAnswers.value[key]) return true
  return hasUserAnswerAfterFeedback(message)
}

function isFeedbackDisabledFromBlock(block: StreamBlock): boolean {
  const key = block.tool_call_id || String(block.created_at)
  return !!submittedFeedbackAnswers.value[key]
}

function getFeedbackSubmittedAnswerFromBlock(_block: StreamBlock): string {
  return ''
}

function handleFeedbackSubmit(message: AgentMessage, answer: string) {
  const key = getFeedbackKey(message)
  if (isFeedbackDisabled(message)) return
  submittedFeedbackAnswers.value[key] = answer
  handleSendMessage(answer, [], { user_feedback: true })
}

function handleFeedbackSubmitFromBlock(block: StreamBlock, answer: string) {
  const key = block.tool_call_id || String(block.created_at)
  if (submittedFeedbackAnswers.value[key]) return
  submittedFeedbackAnswers.value[key] = answer
  handleSendMessage(answer, [], { user_feedback: true })
}

/** 工具结果走侧栏 toolMessages；主对话流中「未完成」= 仍在生成且当前最后一块仍是工具调用 */
const isStreamingToolBlockPending = (block: StreamBlock, index: number) => {
  if (!props.isGenerating) return false
  if (index !== streamingBlocks.value.length - 1) return false
  return block.type === 'get_tools' || block.type === 'get_agents'
}

// UI状态
const isVisible = ref(false)
const showLogo = ref(false)
const showContent1 = ref(false)
const showContent2 = ref(false)

// 流式消息相关状态
const streamingBlocks = ref<StreamBlock[]>([])
const isStreaming = ref(false)
const currentBlockType = ref<string>('')

// 添加在其他 ref 变量附近
const isAutoScroll = ref(true)
const answerContainer = ref<HTMLElement | null>(null)
const copiedStates = ref(new Set<number>())
const messageInput = ref<InstanceType<typeof MessageInput> | null>(null)
const showSuggestions = ref(false)
const showViewHint = ref(true)
const showHintActive = ref(false)

const soulChannels = [
  { name: '微信', supported: true },
  { name: '飞书', supported: true },
  { name: '企业微信', supported: true },
  { name: '小爱音箱', supported: true },
  { name: 'Rokid AI 眼镜', supported: false },
] as const

const editingUserMessageId = ref<string | null>(null)
const editingUserDraft = ref('')
const userEditTextareaRef = ref<HTMLTextAreaElement | null>(null)

/** v-for 内 ref 在 Vue 3.5 可能变成数组，函数 ref 保证始终指向单个 textarea */
function setUserEditTextareaRef(el: unknown) {
  if (el && el instanceof HTMLTextAreaElement) {
    userEditTextareaRef.value = el
  } else {
    userEditTextareaRef.value = null
  }
}

/** 与 MessageInput.vue 中 `adjustHeight` 一致；测量前去掉全局 .input_field 的 max-height 对 scrollHeight 的影响 */
function adjustUserEditTextareaHeight() {
  const run = () => {
    const el = userEditTextareaRef.value
    if (!el) return
    el.style.maxHeight = 'none'
    el.style.height = 'auto'
    const scrollHeight = el.scrollHeight
    const maxHeight = 200
    if (scrollHeight <= maxHeight) {
      el.style.height = `${scrollHeight}px`
      el.style.overflowY = 'hidden'
    } else {
      el.style.height = `${maxHeight}px`
      el.style.overflowY = 'auto'
    }
  }
  nextTick(() => {
    run()
    requestAnimationFrame(() => {
      run()
      requestAnimationFrame(run)
    })
  })
}

/** 蓝图流式区：仅在 plan 段生成中展示，结束后由 tool result 承接 */
const showPlanInStreamingRow = computed(
  () => props.isGenerating && !!props.planStreamContent
)

watch(
  () => props.reloadStreamingUiToken,
  () => {
    streamingBlocks.value = []
    currentBlockType.value = ''
  },
)

watch(
  editingUserMessageId,
  (id) => {
    if (id) {
      adjustUserEditTextareaHeight()
    }
  },
  { flush: 'post' },
)

function isUserTextMessage(msg: AgentMessage): boolean {
  return msg.role === 'user' && isUserTextMessageType(msg.type)
}

function startEditUserMessage(msg: AgentMessage) {
  if (!msg.id || !isUserTextMessage(msg)) return
  editingUserMessageId.value = msg.id
  editingUserDraft.value = msg.content || ''
}

function cancelEditUser() {
  editingUserMessageId.value = null
  editingUserDraft.value = ''
}

const isConfirmEditPending = ref(false)

async function confirmEditUser() {
  const id = editingUserMessageId.value
  if (!id || isConfirmEditPending.value) return
  const text = editingUserDraft.value.trim()
  if (!text) return
  let idx = props.agent_message_list.findIndex(
    (m) => m.role === 'user' && m.id === id,
  )
  if (idx === -1) {
    cancelEditUser()
    return
  }

  isConfirmEditPending.value = true
  try {
    if (props.isGenerating) {
      emit('stopGeneration')
      await nextTick()
      await nextTick()
      idx = props.agent_message_list.findIndex(
        (m) => m.role === 'user' && m.id === id,
      )
      if (idx === -1) {
        cancelEditUser()
        return
      }
    }

    props.agent_message_list.splice(idx)
    const userMsg: AgentMessage = {
      user_id: '',
      conversation_id: '',
      type: 'text',
      role: 'user',
      content: text,
      id,
      created_at: Date.now(),
    }
    props.agent_message_list.push(userMsg)
    props.agent_message_list.push({
      user_id: '',
      conversation_id: '',
      type: 'init',
      role: 'assistant',
      content: '',
      tool_call_id: '',
      tool_calls: undefined,
      created_at: Date.now(),
    })
    cancelEditUser()
    startStreaming()
    emit('sendMessage', text, [], { input_message_id: id })
  } finally {
    isConfirmEditPending.value = false
  }
}

// 添加滚动到底部的方法
const scrollToBottom = () => {
  if (isAutoScroll.value && answerContainer.value) {
    nextTick(() => {
      if (answerContainer.value) {
        answerContainer.value.scrollTop = answerContainer.value.scrollHeight
      }
    })
  }
}

// 添加处理用户手动滚动的方法
const handleScroll = () => {
  if (answerContainer.value) {
    const { scrollTop, scrollHeight, clientHeight } = answerContainer.value
    // 如果用户滚动到接近底部，恢复自动滚动
    if (scrollHeight - scrollTop - clientHeight < 50) {
      isAutoScroll.value = true
    } else {
      // 用户手动滚动到其他位置，停止自动滚动
      isAutoScroll.value = false
    }
  }
}

const agent_card_list = ref<AgentCard[]>([])
const kb_list = ref([])

async function getAgentCardList() {
  try {
    const response = await axios.get(`/api/agent_cards/${props.userId}`)
    agent_card_list.value = response.data
    console.log('agent_card_list:', agent_card_list.value)
  } catch (error) {
    console.error('获取智能体列表失败:', error)
  }
}

async function getKBList() {
  try {
    const response = await axios.get(`/kb/kb/list/?user_id=${props.userId}`)
    if (response.data.success) {
      kb_list.value = response.data.data.map(kb => ({
        id: kb.kb_id,
        name: kb.kb_name_zh
      }))
    }
  } catch (error) {
    console.error('获取知识库列表失败:', error)
  }
}

function handleSelectModel(model_source: string, model: string) {
  props.chat_request.model_source = model_source
  props.chat_request.model = model
}

function handleStopGeneration() {
  emit('stopGeneration')
  }

  function handleSelectAgent(agent_use: string | null, agent_id: string[] | string | null) {
  props.chat_request.agent_use = agent_use;
  props.chat_request.agent_id = agent_id;
  // 根据 agent_id 设置 agent_name，用于界面显示（发送时仍用 agent_id）
  if (agent_use && agent_id) {
    if (typeof agent_id === 'string') {
      // 特殊智能体：soulprout_create_agent 显示中文名称
      if (agent_id === 'soulprout_create_agent') {
        props.chat_request.agent_name = '创建Agent专家/团队';
      } else {
        const agent = agent_card_list.value.find(a => (a.agent_id || a.name) === agent_id);
        props.chat_request.agent_name = (agent?.name_zh || agent?.name) ?? agent_id;
      }
    } else if (Array.isArray(agent_id)) {
      props.chat_request.agent_name = agent_id.map(id => {
        const agent = agent_card_list.value.find(a => (a.agent_id || a.name) === id);
        return (agent?.name_zh || agent?.name) ?? id;
      });
    } else {
      props.chat_request.agent_name = null;
    }
  } else {
    props.chat_request.agent_name = null;
  }

    if (agent_use && agent_id && typeof agent_id === 'string') {
      const agent = agent_card_list.value.find(a => (a.agent_id || a.name) === agent_id);
    if (agent?.announcement) {
      props.agent_message_list.push({
        user_id: '',
        conversation_id: '',
        type: 'text',
        role: 'assistant',
        content: agent.announcement,
        created_at: Date.now(),
        tool_call_id: '',
        tool_calls: undefined
      });
    }
  }
  // 对于expert-agent和select-agent，暂不添加announcement
}

function handleSelectKB(kbs) {
  props.chat_request.kb_use = kbs
}

// Markdown解析器
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
    } catch (e) {}
  }
  if (!highlighted) {
    highlighted = md.utils.escapeHtml(code)
  }
  const titleBar = `
<div class="code-title">
  <span class="code-lang">${lang}</span>
  <img src="${ContentCopyIcon}" alt="复制" class="code-copy-btn" />
</div>
  `
  const codeBlock = `<pre class="hljs"><code>${highlighted}</code></pre>`
  return `<div class="code-wrapper">${titleBar}${codeBlock}</div>`
}

// 渲染markdown内容（结果缓存，避免重复解析）
const markdownCache = new Map<string, string>()
const MARKDOWN_CACHE_MAX = 80
const renderMarkdown = (content: string | undefined) => {
  const key = content ?? ''
  const cached = markdownCache.get(key)
  if (cached) return cached
  if (markdownCache.size >= MARKDOWN_CACHE_MAX) markdownCache.clear()
  let html = md.render(key)
  html = html.replace(/<a /g, '<a target="_blank" rel="noopener noreferrer" ')
  markdownCache.set(key, html)
  return html
}

// 显示消息列表（只包含历史消息；user_feedback 类型的用户消息不在对话区展示）
const displayMessages = computed(() => {
  return props.agent_message_list.filter(
    (msg) =>
      msg.type !== 'init' &&
      !(msg.role === 'user' && msg.type === 'user_feedback'),
  )
})

// 将连续的相同角色消息分组（user_feedback 归入 assistant 区展示）
const messageDisplayRole = (message: AgentMessage): string => {
  if (message.type === 'user_feedback') return 'assistant'
  return message.role
}

const groupedMessages = computed<MessageGroup[]>(() => {
  const messages = displayMessages.value
  if (messages.length === 0) return []
  
  const groups: MessageGroup[] = []
  let currentGroup: MessageGroup | null = null
  
  for (const message of messages) {
    const displayRole = messageDisplayRole(message)
    if (!currentGroup || currentGroup.role !== displayRole) {
      currentGroup = {
        role: displayRole,
        messages: [message]
      }
      groups.push(currentGroup)
    } else {
      currentGroup.messages.push(message)
    }
  }
  
  return groups
})

// 处理流式数据
const handleStreamingMessage = (streamingMessage: AgentMessage) => {
  if (!streamingMessage || !streamingMessage.type) return
  if (streamingMessage.type === 'init') return
  if (streamingMessage.type === 'input_message_id' || streamingMessage.type === 'reload_history') {
    return
  }

  const { type, content, role, tool_calls, created_at } = streamingMessage
  // 从 tool_calls 中获取 id，如果没有则使用 created_at
  const toolCallId = tool_calls && tool_calls.length > 0 && tool_calls[0].id 
    ? tool_calls[0].id 
    : (streamingMessage.tool_call_id || String(created_at))
  
  // 如果类型改变，创建新的块
  if (type !== currentBlockType.value || type === 'get_tools' || type === 'get_agents' || type === 'user_feedback') {
    currentBlockType.value = type
    streamingBlocks.value.push({
      type: type,
      role: role,
      content: content || '',
      tool_call_id: toolCallId,
      tool_calls: tool_calls || undefined,
      created_at: created_at,
      table: streamingMessage.table,
    })
  } else {
    // 相同类型，累积追加内容到当前块
    const lastBlock = streamingBlocks.value[streamingBlocks.value.length - 1]
    if (lastBlock) {
      lastBlock.content += (content || '')
    }
  }
  nextTick(() => {
  scrollToBottom()
})
}

// 完成流式输出
const finishStreaming = () => {
  // 将流式消息块转换为完整的消息并添加到历史记录
  if (streamingBlocks.value.length > 0) {
    streamingBlocks.value.forEach(block => {
      // 从 tool_calls 中获取 id，如果没有则使用 block.tool_call_id 或 created_at
      const toolCallId = block.tool_calls && block.tool_calls.length > 0 && block.tool_calls[0].id
        ? block.tool_calls[0].id
        : (block.tool_call_id || String(block.created_at || Date.now()))
      
      const assistantMsg: AgentMessage = {
        user_id: '',
        conversation_id: '',
        type: block.type,
        role: block.type === 'user_feedback' ? (block.role || 'tool') : (block.role || 'assistant'),
        content: block.content,
        created_at: block.created_at || Date.now(),
        tool_call_id: toolCallId,
        tool_calls: block.tool_calls || undefined,
        table: block.table,
        from_streaming: true,  // 标记来自流式输出，tool_calls 不显示 content
      }
      props.agent_message_list.push(assistantMsg)
    })
    
    // 移除初始化消息
    const initIndex = props.agent_message_list.findIndex(msg => msg.type === 'init')
    if (initIndex !== -1) {
      props.agent_message_list.splice(initIndex, 1)
    }
  }
  
  // 清理流式状态
  streamingBlocks.value = []
  isStreaming.value = false
  currentBlockType.value = ''
}

// 开始流式输出
const startStreaming = () => {
  isStreaming.value = true
  streamingBlocks.value = []
  currentBlockType.value = ''
}

// 工具是否调用
function handleToolsUseChange() {
  // 切换 tools_use 的值
  props.chat_request.tools_use = !props.chat_request.tools_use
}

// 技能是否调用
function handleSkillsUseChange() {
  // 切换 skills_use 的值
  props.chat_request.skills_use = !props.chat_request.skills_use
}

// 处理发送消息事件
const handleSendMessage = (
  message: string,
  files: File[] = [],
  options?: { user_feedback?: boolean },
) => {
  const now = Date.now()
  const isUserFeedback = !!options?.user_feedback
  const userMsg: AgentMessage = {
    user_id: '',
    conversation_id: '',
    type: isUserFeedback ? 'user_feedback' : 'text',
    role: 'user',
    content: message,
    created_at: now,
  }
  props.agent_message_list.push(userMsg)

  if (files.length > 0) {
    const fileNames = files.map((f) => f.name)
    props.agent_message_list.push({
      user_id: '',
      conversation_id: '',
      type: 'file',
      role: 'user',
      content: `\n\nFILE: 上传文件 -> ${JSON.stringify(fileNames)}`,
      table: { file_names: fileNames },
      created_at: now + 1,
    })
  }

  // 2. 添加初始化标记（用于显示AI正在回复）
  props.agent_message_list.push({
    user_id: '',
    conversation_id: '',
    type: 'init',
    role: 'assistant', 
    content: '',
    tool_call_id: '',
    tool_calls: undefined,
    created_at: Date.now() 
  })
  
  // 3. 开始流式状态
  startStreaming()
  
  // 4. 触发父组件事件
  emit('sendMessage', message, files, options)
}

// 监听currentStreamingMessage变化 - 处理来自父组件的流式数据
watch(() => props.currentStreamingMessage, (newMessage, oldMessage) => {
  // console.log('消息：', props.currentStreamingMessage)
  if (!newMessage) {
    // 如果currentStreamingMessage变为null，说明流式输出结束
    if (isStreaming.value) {
      finishStreaming()
    }
    return
  }
  
  // 开始接收流式消息时，确保处于流式状态
  if (!isStreaming.value) {
    startStreaming()
  }
  
  // 处理流式消息
  handleStreamingMessage(newMessage)
  nextTick(() => {
    scrollToBottom()
  })
}, { deep: true })

// 监听消息列表变化，自动滚动到底部
watch(() => props.agent_message_list, () => {
  nextTick(() => {
    scrollToBottom()
  })
}, { deep: true, immediate: true })

let welcomeAnimationTimers: ReturnType<typeof setTimeout>[] = []

function clearWelcomeAnimationTimers() {
  welcomeAnimationTimers.forEach(clearTimeout)
  welcomeAnimationTimers = []
}

function scheduleWelcomeAnimationStep(fn: () => void, delay: number) {
  welcomeAnimationTimers.push(setTimeout(fn, delay))
}

function replayWelcomeAnimation() {
  clearWelcomeAnimationTimers()
  isVisible.value = false
  showSuggestions.value = false
  showViewHint.value = true
  showHintActive.value = false
  showLogo.value = false
  showContent1.value = false
  showContent2.value = false

  nextTick(() => {
    isVisible.value = true
  })
}

// 欢迎动画逻辑
watch(isVisible, (val) => {
  clearWelcomeAnimationTimers()
  if (val) {
    showLogo.value = false
    showContent1.value = false
    showContent2.value = false
    showHintActive.value = false

    scheduleWelcomeAnimationStep(() => { showLogo.value = true }, 0)
    scheduleWelcomeAnimationStep(() => { showContent1.value = true }, 50)
    scheduleWelcomeAnimationStep(() => { showHintActive.value = true }, 1050)
    scheduleWelcomeAnimationStep(() => { showContent2.value = true }, 900)
  } else {
    showLogo.value = false
    showContent1.value = false
    showContent2.value = false
    showHintActive.value = false
  }
})

// 初始化显示
scheduleWelcomeAnimationStep(() => { isVisible.value = true }, 500)

// Add copy function in script
const copyToClipboard = (text: string | undefined, timestamp: number) => {
     const content = text ?? '';
     if (navigator.clipboard) {
       navigator.clipboard.writeText(content)
         .then(() => {
           copiedStates.value.add(timestamp)
           setTimeout(() => {
             copiedStates.value.delete(timestamp)
           }, 1000)
           console.log('Text copied to clipboard');
         })
         .catch(err => {
           console.error('Failed to copy text: ', err);
         });
     } else {
       // Fallback for older browsers
       const textarea = document.createElement('textarea');
       textarea.value = content;
       textarea.style.position = 'fixed'; // Avoid scrolling to bottom
       document.body.appendChild(textarea);
       textarea.focus();
       textarea.select();
       try {
         const successful = document.execCommand('copy');
         if (successful) {
           copiedStates.value.add(timestamp)
           setTimeout(() => {
             copiedStates.value.delete(timestamp)
           }, 1000)
           console.log('Fallback: Text copied to clipboard');
         } else {
           console.error('Fallback: Failed to copy');
         }
       } catch (err) {
         console.error('Fallback: Failed to copy: ', err);
       }
       document.body.removeChild(textarea);
     }
   }

// Function to attach copy listeners to code block buttons
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
      const img = btn as HTMLImageElement
      const prev = img.src
      img.src = DoneIcon
      setTimeout(() => {
        img.src = prev || ContentCopyIcon
      }, 1000)
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
        const img = btn as HTMLImageElement
        const prev = img.src
        img.src = DoneIcon
        setTimeout(() => {
          img.src = prev || ContentCopyIcon
        }, 1000)
      } else {
        console.error('Fallback: Failed to copy');
      }
    } catch (err) {
      console.error('Fallback: Failed to copy: ', err);
    }
    document.body.removeChild(textarea);
  }
}

// Call attachCopyListeners in onMounted and onUpdated
onMounted(attachCopyListeners)
onUpdated(attachCopyListeners)
onUnmounted(clearWelcomeAnimationTimers)

const hasMessages = computed(
  () =>
    groupedMessages.value.length > 0 ||
    streamingBlocks.value.length > 0 ||
    showPlanInStreamingRow.value
)

watch(hasMessages, (newVal, oldVal) => {
  if (!newVal && oldVal) {
    replayWelcomeAnimation()
  }
})

watch(
  () => props.welcomeAnimationToken,
  () => {
    if (!hasMessages.value) {
      replayWelcomeAnimation()
    }
  },
)

const prefillInput = (text: string) => {
  messageInput.value?.setInput(text)
}

// 定制Agent员工：选中智能体并直接发送
const handleCreateAgentClick = () => {
  handleSelectAgent('expert-agent', 'soulprout_create_agent')
  handleSendMessage('你好，请为我开始创建', [])
}
</script>

<style scoped>
@import '@/assets/css/chat.css';

/* 可以添加一些流式输出的样式 */
.answer-robot-reasoner {
  background-color: #f5f5f5;
  padding: 8px 12px;
  border-radius: 6px;
  margin-bottom: 8px;
  border-left: 3px solid rgba(47, 79, 79, 0.565);
}

.answer-robot-content {
  line-height: 1.6;
}

/* 流式输出时的打字效果（可选） */
@keyframes typing {
  from { opacity: 0.5; }
  to { opacity: 1; }
}

.streaming-content {
  animation: typing 0.5s ease-in-out infinite alternate;
}

/* Consolidate and update message-actions styles */
.message-actions {
  position: absolute;
  opacity: 0;
  transition: opacity 0.2s ease;
  padding: 0;
  pointer-events: none;
}

.message-actions:hover {
  opacity: 1;
  pointer-events: auto;
}

/* 用户消息：与 assistant 一致，整块 text-message-wrapper 悬停显示按钮；底部留白容纳按钮，避免负 bottom 导致悬停丢失 */
.text-message-wrapper--user {
  position: relative;
  width: fit-content;
  max-width: 100%;
  align-self: flex-end;
  padding-bottom: 30px;
  box-sizing: border-box;
}

/* 编辑时占满用户消息列可用宽度，避免 fit-content + textarea 宽度 100% 时父级被压成极窄导致截断、高度只算一行 */
.text-message-wrapper--user.text-message-wrapper--user-editing {
  width: 100%;
  max-width: 100%;
  min-width: 0;
}

/* 编辑时去掉气泡墨绿底；勿用 height:fit-content，否则在 flex 子项里会按 textarea 最小高度卡成一行 */
.answer-me-content--editing {
  background-color: transparent !important;
  box-shadow: none !important;
  width: 100%;
  max-width: 100%;
  min-width: 0;
  height: auto !important;
  min-height: 0;
  align-items: stretch;
  box-sizing: border-box;
  overflow: visible;
}

.text-message-wrapper--user .message-actions--user {
  right: 8px;
  bottom: 2px;
  left: auto;
  display: flex;
  align-items: center;
  gap: 6px;
}

.user-message-column {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 8px;
  max-width: 100%;
}

.user-uploaded-files {
  width: 100%;
  display: flex;
  justify-content: flex-end;
}

.user-uploaded-files .selected-files--history {
  font-size: 12px;
  color: #666;
  display: flex;
  align-items: flex-start;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 10px;
}

.user-uploaded-files .selected-file-item {
  position: relative;
  width: 70px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  padding: 2px;
}

.user-uploaded-files .selected-file-icon {
  width: 40px;
  height: 40px;
  border-radius: 6px;
  object-fit: contain;
  padding: 4px;
}

.user-uploaded-files .selected-file-name {
  max-width: 64px;
  text-align: center;
  font-size: 11px;
  color: #374151;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.answer-single-robot .message-actions {
  bottom: 0px;
  left: 30px;
  right: auto;
}

.text-message-wrapper:hover .message-actions,
.text-message-wrapper:hover .message-actions {
  opacity: 1;
  pointer-events: auto;
}

.message-action-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 2px;
  margin: 0;
  border: 1px solid transparent;
  border-radius: 6px;
  background: transparent;
  cursor: pointer;
  line-height: 0;
  box-sizing: border-box;
  font: inherit;
  appearance: none;
  -webkit-appearance: none;
  opacity: 0.72;
  transition:
    background 0.15s ease,
    opacity 0.15s ease,
    filter 0.15s ease;
}

.message-action-btn:hover {
  opacity: 1;
  background: rgba(17, 24, 39, 0.06);
}

.message-action-btn:focus {
  outline: none;
}

.message-action-btn:focus-visible {
  outline: 1px solid rgba(37, 99, 235, 0.35);
  outline-offset: 1px;
}

.message-action-btn-icon {
  width: 20px;
  height: 20px;
  display: block;
  pointer-events: none;
}

/* 外层绿框；内层与 MessageInput 相同：input-total + input_field，高度由 adjustUserEditTextareaHeight 与全局 .input_field 一致 */
.user-edit-box {
  width: 100%;
  box-sizing: border-box;
  padding: 8px 10px 6px;
  background: transparent;
  border: 2px solid #22c55e;
  border-radius: 12px;
}

.user-edit-box .input-total {
  width: 100%;
  min-width: 0;
  flex-shrink: 0;
}

.user-edit-actions {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
}

.user-edit-btn-cancel {
  padding: 4px 12px;
  border-radius: 999px;
  font-size: 14px;
  cursor: pointer;
  border: 1px solid #e5e7eb;
  background: #fff;
  color: #374151;
  transition: background 0.15s ease, border-color 0.15s ease;
}

.user-edit-btn-cancel:hover {
  background: #f9fafb;
  border-color: #d1d5db;
}

.user-edit-btn-send {
  padding: 4px 12px;
  border-radius: 999px;
  font-size: 14px;
  cursor: pointer;
  border: 1px solid transparent;
  background: #22c55e;
  color: #fff;
  transition: background 0.15s ease, border-color 0.15s ease;
}

.user-edit-btn-send:hover {
  background: #16a34a;
}

.text-message-wrapper {
  position: relative;
}

  .answer-robot-error {
    background-color: #ffebee;
    color: #c62828;
    padding: 8px 12px;
    border-radius: 6px;
    margin-bottom: 8px;
    border-left: 3px solid #c62828;
    display: flex;
    align-items: center;
  }
  
  .error-icon {
    width: 16px;
    height: 16px;
    margin-right: 8px;
  }

.answer-robot-tool {
  cursor: pointer;
}

/* web_search 区块：纵向排列，摘要与详情分区 */
.answer-robot-tool--with-ws {
  flex-direction: column;
  align-items: flex-start;
  flex-wrap: nowrap;
  gap: 0;
  width: 100%;
  max-width: 100%;
  margin-top: 2px;
  margin-bottom: 0;
  padding-top: 0;
  padding-bottom: 0;
  cursor: default;
}

.answer-robot-tool-wrapper {
  margin-top: 2px;
}

.user-feedback-wrapper {
  width: 100%;
  max-width: 100%;
  margin: 4px 0 4px 35px;
}

/* 工具调用未完成：与「查看这里」同款渐变；划过阶段占比加大、周期 2.5s，划过比 view-hint 更慢 */
.answer-robot-tool-name.answer-robot-tool-name--pending {
  position: relative;
  overflow: hidden;
  border-color: rgba(176, 178, 186, 0.95);
  box-shadow: 0 0 0 1px rgba(200, 202, 210, 0.55);
}

.answer-robot-tool-name.answer-robot-tool-name--pending::after {
  content: '';
  position: absolute;
  /* 与 .view-hint::after 同宽（100% 带宽），向左偏移扫过；向外扩展 1px 使高光同时扫过边框 */
  top: -1px;
  left: -100%;
  width: calc(100% + 2px);
  height: calc(100% + 2px);
  background: linear-gradient(
    90deg,
    transparent 0%,
    rgba(255, 255, 255, 0.5) 30%,
    rgba(255, 255, 255, 0.7) 50%,
    rgba(255, 255, 255, 0.5) 70%,
    transparent 100%
  );
  animation: tool-pending-shine 2.5s ease-in-out infinite;
  pointer-events: none;
  border-radius: inherit;
}

/* 较 view-hint-shine（约 17% 时间划过）拉长划过区间，高光从左到右移动更慢、更从容 */
@keyframes tool-pending-shine {
  0%,
  58% {
    left: -100%;
  }
  100% {
    left: 100%;
  }
}

.card-desc-slogan {
  display: block;
  font-size: 12px;
  color: #999;
  margin-top: auto;
  font-style: italic;
}

.card-desc-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}

.card-desc-highlight {
  display: block;
  color: #4a7c59;
  font-weight: 700;
  font-size: 1.15em;
  margin-bottom: 6px;
  text-align: center;
}

.card-desc-sub {
  display: block;
  text-align: center;
}

/* 需要我做些什么 与 提示文字 同行，底部对齐 */
.no-history-title-row {
  display: flex;
  align-items: flex-end;
  justify-content: center;
  gap: 12px;
}

/* 移动到这里查看 提示文字 - 主标题出现约1秒后从右到左进场，底部对齐，悬停到主标题时瞬间消失 */
.view-hint {
  position: relative;
  font-size: 12px;
  font-weight: 500;
  letter-spacing: 0.5px;
  color: rgba(100, 116, 139, 0.95);
  white-space: nowrap;
  overflow: hidden;
  padding: 6px 12px;
  background: linear-gradient(135deg, rgba(248, 250, 252, 0.95) 0%, rgba(241, 245, 249, 0.9) 100%);
  border: 1px solid rgba(0, 0, 0, 0.06);
  box-shadow:
    0 1px 2px rgba(0, 0, 0, 0.04),
    0 4px 12px rgba(0, 0, 0, 0.03),
    inset 0 1px 0 rgba(255, 255, 255, 0.8);
  border-radius: 16px;
  transform: translateX(100%);
  opacity: 0;
  transition: transform 1s cubic-bezier(0.4, 0, 0.2, 1),
    opacity 1s cubic-bezier(0.4, 0, 0.2, 1);
}

.view-hint.active {
  transform: translateX(0);
  opacity: 1;
}

.view-hint::after {
  content: '';
  position: absolute;
  top: 0;
  left: -100%;
  width: 100%;
  height: 100%;
  background: linear-gradient(
    90deg,
    transparent 0%,
    rgba(255, 255, 255, 0.5) 30%,
    rgba(255, 255, 255, 0.7) 50%,
    rgba(255, 255, 255, 0.5) 70%,
    transparent 100%
  );
  animation: view-hint-shine 6s ease-in-out infinite;
}

@keyframes view-hint-shine {
  0%, 83% { left: -100%; }
  100% { left: 100%; }
}

.no-history-container--soul {
  max-width: 720px;
  padding: 0 24px;
  text-align: center;
}

.no-history-container--soul .no-history-title-row {
  align-items: center;
}

.no-history-container .no-history-content1 {
  font-size: 30px;
  font-weight: 550;
  height: auto;
  line-height: 1.2;
  margin-bottom: 5px;
  letter-spacing: 1px;
  color: rgb(0, 0, 0);
}

.soul-channel-desc {
  margin: 14px 0 0;
  font-size: 12px;
  font-weight: 400;
  line-height: 1.5;
  letter-spacing: 0.2px;
  color: rgba(71, 85, 105, 0.92);
  transform: translateY(100%);
  opacity: 0;
  transition: transform 1s cubic-bezier(0.4, 0, 0.2, 1),
    opacity 1s cubic-bezier(0.4, 0, 0.2, 1);
}

.soul-channel-desc.active {
  transform: translateY(0);
  opacity: 1;
}

.soul-channel-line {
  display: flex;
  flex-wrap: nowrap;
  align-items: center;
  justify-content: center;
  gap: 10px;
}

.soul-channel-desc-label {
  flex-shrink: 0;
  color: rgba(100, 116, 139, 0.95);
  font-size: 12px;
  white-space: nowrap;
}

.soul-channel-list {
  display: inline-flex;
  flex-wrap: nowrap;
  align-items: center;
  gap: 12px;
}

.soul-channel-item {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  color: rgba(51, 65, 85, 0.95);
  flex-shrink: 0;
}

.soul-channel-item--unsupported {
  color: rgba(100, 116, 139, 0.88);
}

.soul-channel-box {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 12px;
  height: 12px;
  border: 1px solid rgba(148, 163, 184, 0.75);
  border-radius: 3px;
  background: rgba(248, 250, 252, 0.9);
  flex-shrink: 0;
}

.soul-channel-box--checked {
  border-color: #16a34a;
  background: rgba(22, 163, 74, 0.1);
  color: #16a34a;
}

.soul-channel-box-icon {
  width: 8px;
  height: 8px;
}

.soul-channel-name {
  font-size: 12px;
  white-space: nowrap;
}

.soul-channel-ellipsis {
  flex-shrink: 0;
  color: rgba(100, 116, 139, 0.75);
  font-size: 12px;
  line-height: 12px;
}

</style>

<style>
.code-wrapper {
  margin: 10px 0;
  border: 1px solid #e1e4e8;
  border-radius: 6px;
  overflow: hidden;
  background-color: rgba(248, 251, 249, 0.9);
  box-shadow: 0 1px 3px rgba(0,0,0,0.05);
}

.code-title {
  background-color: #f8f8f86f;
  padding: 3px 12px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid #e1e4e8;
  font-size: 12px;
  color: #586069;
}

.code-lang {
  font-weight: 600;
  text-transform: uppercase;
}

.code-copy-btn {
  width: 16px;
  height: 16px;
  cursor: pointer;
  opacity: 0.7;
  transition: opacity 0.2s;
}

.code-copy-btn:hover {
  opacity: 1;
}

pre.hljs {
  margin: 0;
  padding: 12px;
  overflow: auto;
  background: #fff;
  border-top: none;
}
</style>
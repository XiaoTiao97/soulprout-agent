<template>
    <div class="agent-option-total" :style="{ width: isExpanded ? '60px' : '260px' }">
        <div class="agent-option-container">
            <div class="agent-option-top">
                <div class="agent-option-top-bar" :class="{ 'agent-option-top-bar--collapsed': isExpanded }">
                    <img
                        v-show="!isExpanded"
                        class="sidebar-brand-logo"
                        src="@/assets/images/logo.png"
                        alt="Soulprout"
                    />
                    <button class="close-sidebar" @click="$emit('SidebarChange')" aria-label="关闭边栏" data-testid="close-sidebar-button">
                        <img class="icon-xl-heavy max-md:hidden" width="20" height="20" src="@/assets/images/aspect_ratio.svg" alt="" />
                    </button>
                </div>
            </div>
            <div class="agent-option-main">
                <div class="agent-option" :class="{ 'hidden-text': isExpanded }">
                    <button class="tool-option-btn" @click="$emit('openToolOption')" title="查看工具库">
                        <img class="tools_box" width="24" height="24" src="@/assets/images/tools_box.svg" alt="toolsbox-logo" />
                        <span>工具</span>
                    </button>
                </div>
                <div class="agent-option" :class="{ 'hidden-text': isExpanded }">
                    <button class="tool-option-btn" @click="$emit('openSkillOption')" title="查看技能库">
                        <img class="tools_box" width="24" height="24" src="@/assets/images/skill_icon.svg" alt="skill-logo" />
                        <span>技能</span>
                    </button>
                </div>
                <div class="agent-option" :class="{ 'hidden-text': isExpanded }">
                    <button class="tool-option-btn" @click="$emit('openKBOption')" title="查看知识库">
                        <img class="tools_box" width="24" height="24" src="@/assets/images/kb_icon.svg" alt="knowledgebase-logo" />
                        <span>知识</span>
                    </button>
                </div>
                <div class="agent-option" :class="{ 'hidden-text': isExpanded }">
                    <button class="tool-option-btn" @click="$emit('openAgentOption')" title="查看专家库">
                        <img class="tools_box" width="24" height="24" src="@/assets/images/agent_icon.svg" alt="agent-logo" />
                        <span>专家</span>
                    </button>
                </div>
            </div>
        </div>
        <div class="conversation-select" :class="{ 'disabled-select': isGenerating }" :title="isGenerating ? '正在生成中，无法操作' : ''">
            <div
              class="chat-mode-section"
              :class="{ 'chat-mode-section--collapsed': isExpanded }"
            >
              <div class="chat-mode-header">
                <span class="chat-mode-header-title">对话模式</span>
                <span class="chat-mode-header-hint">
                  {{ chatMode === 'soulprout' ? '越用越懂你' : '专业打工人' }}
                </span>
              </div>
              <div
                class="chat-mode-switch"
                role="tablist"
                aria-label="对话模式切换"
                :data-active="chatMode"
              >
                <span class="chat-mode-switch-thumb" aria-hidden="true"></span>
                <button
                  type="button"
                  role="tab"
                  class="chat-mode-option"
                  :class="{ 'chat-mode-option--active': chatMode === 'soulprout' }"
                  :aria-selected="chatMode === 'soulprout'"
                  :tabindex="chatMode === 'soulprout' ? 0 : -1"
                  title="Soul 模式：日常陪伴对话"
                  @click="handleSwitchMode('soulprout')"
                >
                  <svg class="chat-mode-option-icon" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                    <path d="M8 13.5V7.5" />
                    <path d="M8 7.5c0-2.2 1.7-4 4-4 0 2.2-1.8 4-4 4z" />
                    <path d="M8 8.5c0-1.8-1.5-3.3-3.3-3.3 0 1.8 1.5 3.3 3.3 3.3z" />
                  </svg>
                  <span class="chat-mode-option-label">Soul</span>
                </button>
                <button
                  type="button"
                  role="tab"
                  class="chat-mode-option"
                  :class="{ 'chat-mode-option--active': chatMode === 'task' }"
                  :aria-selected="chatMode === 'task'"
                  :tabindex="chatMode === 'task' ? 0 : -1"
                  title="Task 模式：任务式多会话协作"
                  @click="handleSwitchMode('task')"
                >
                  <svg class="chat-mode-option-icon" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                    <path d="M3 4.5h7M3 8h7M3 11.5h4.5" />
                    <path d="m11.5 10.5 1.6 1.6L15.5 9.5" />
                  </svg>
                  <span class="chat-mode-option-label">Task</span>
                </button>
              </div>
            </div>

            <div v-if="chatMode === 'task'" class="create-conversation">
                <button
                    class="create-conversation-button-agent"
                    :class="{ 'create-conversation-button-agent--collapsed': isExpanded }"
                    @click="$emit('createConversation')"
                >
                    <div class="create-conversation-logo">
                        <img class="shrink-0 group-hover:scale-105 transition" width="20" height="20" src="@/assets/images/create_conversation.svg" alt="" />
                    </div>
                    <div v-show="!isExpanded" class="create-conversation-text">新任务</div>
                </button>
            </div>

            <div
              v-if="chatMode === 'task'"
              class="history-choose"
              :class="{ 'hidden-text': isExpanded }"
              ref="conversationListRef"
            >
            <div
                class="history-agent"
                v-for="item in conversation_list"
                :key="item.conversation_id"
                @click="handlePickConversation(item)"
                :class="{ selected: item.conversation_id === chat_request.conversation_id }"
            >
                <div class="conversation-abstract-wrapper">
                    <input
                      v-if="editingId === item.conversation_id"
                      :ref="el => setEditingInputRef(el, item.conversation_id)"
                      v-model="editingText"
                      class="conversation-edit-input"
                      type="text"
                      @click.stop
                      @keydown.enter.prevent="saveEdit()"
                      @blur="saveEdit()"
                    />
                    <p
                      v-else
                      class="conversation_abstract"
                      :key="item.conversation_id"
                      :title="item.abstract || '未命名对话'"
                    >
                      {{ item.abstract || '未命名对话' }}
                    </p>
                </div>
                <div class="conversation-option-wrapper">
                    <button
                      class="conversation_option"
                      @click.stop="toggleOptionMenu(item, $event)"
                      title="对话选项"
                    >
                      <img src="@/assets/images/option_conversation.svg" width="18" height="18" />
                    </button>
                    <div
                      v-if="activeMenuId === item.conversation_id"
                      class="conversation-option-menu"
                      :style="{
                        top: `${menuPosition.top}px`,
                        left: `${menuPosition.left}px`,
                        minWidth: `${menuPosition.width}px`,
                      }"
                    >
                      <button class="conversation-option-item" @click.stop="startEdit(item)">
                        <img src="@/assets/images/edit_icon.svg" width="16" height="16" />
                        <span>编辑</span>
                      </button>
                      <button class="conversation-option-item conversation-delete" @click.stop="handleDelete(item.conversation_id, $event)">
                        <img src="@/assets/images/delete.svg" width="16" height="16" />
                        <span>删除</span>
                      </button>
                    </div>
                </div>
            </div>
            </div>
        </div>
        <div
          v-if="confirmDeleteId"
          class="confirm-popover"
          :style="{ top: `${confirmPosition.top}px`, left: `${confirmPosition.left}px` }"
          ref="confirmRef"
        >
          <div class="confirm-content">
            <div class="confirm-main">您确定要删除对话吗？</div>
            <div class="confirm-sub">已删除的对话不可恢复。</div>
          </div>
          <div class="confirm-actions">
            <button class="confirm-cancel" @click="cancelDelete">取消</button>
            <button class="confirm-ok" @click="confirmDelete">确定</button>
          </div>
        </div>
        <div class="user-option">
  <button type="button" class="user-button" @click.stop="toggleMenu" title="用户菜单">
    <img class="user-icon" width="25" height="25" src="@/assets/images/user_icon.svg" alt="" />
    <span
      v-if="username"
      class="user-display-name"
      :class="{ 'hidden-text': isExpanded }"
      :title="username"
    >{{ username }}</span>
  </button>
  <div v-if="showMenu" class="user-menu" ref="menuRef">
    <button class="menu-item" @click="goHome">
      <img width="20" height="20" src="@/assets/images/home_icon.svg" alt="home" />
      主页
    </button>
    <button class="menu-item" @click="goDocs">
      <img width="20" height="20" src="@/assets/images/product_file.svg" alt="docs" />
      产品文档
    </button>
    <button class="menu-item" @click="logout">
      <img width="20" height="20" src="@/assets/images/logout_icon.svg" alt="logout" />
      注销
    </button>
  </div>
</div>
    </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, nextTick, toRefs, type ComponentPublicInstance } from 'vue';
import { useRouter } from 'vue-router';
import type { ConversationBase, ChatRequest } from '../types/interface';

const emit = defineEmits([
  'createConversation',
  'deleteConversation',
  'pickConversation',
  'SidebarChange',
  'openToolOption',
  'openSkillOption',
  'openKBOption',
  'openAgentOption',
  'updateConversationAbstract',
  'switchMode',
]);

const props = withDefaults(defineProps<{
  conversation_list: ConversationBase[];
  isExpanded: boolean;
  chat_request: Partial<ChatRequest>;
  isGenerating: boolean;
  username?: string;
  chatMode?: 'soulprout' | 'task';
}>(), {
  chatMode: 'task',
});

const { conversation_list, isExpanded, chat_request, isGenerating } = toRefs(props);

const handleSwitchMode = (mode: 'soulprout' | 'task') => {
  if (props.isGenerating || props.chatMode === mode) return;
  emit('switchMode', mode);
};

const handleToggleMode = () => {
  const next: 'soulprout' | 'task' = props.chatMode === 'soulprout' ? 'task' : 'soulprout';
  handleSwitchMode(next);
};

const router = useRouter();
const showMenu = ref(false);
const menuRef = ref<HTMLElement | null>(null);
const conversationListRef = ref<HTMLElement | null>(null);
const confirmRef = ref<HTMLElement | null>(null);
const activeMenuId = ref<string | null>(null);
const editingId = ref<string | null>(null);
const editingText = ref('');
const editingInputMap = ref<Record<string, HTMLInputElement | null>>({});
const isSavingEdit = ref(false);
const menuPosition = ref<{ top: number; left: number; width: number }>({
  top: 0,
  left: 0,
  width: 120,
});
const confirmPosition = ref<{ top: number; left: number }>({ top: 0, left: 0 });

const setEditingInputRef = (
  el: HTMLInputElement | Element | ComponentPublicInstance | null,
  id: string,
) => {
  const inputEl = el instanceof HTMLInputElement ? el : null;
  editingInputMap.value[id] = inputEl;
};

const toggleMenu = () => {
  showMenu.value = !showMenu.value;
  if (showMenu.value) {
    nextTick(() => {
      document.addEventListener('click', handleClickOutside);
    });
  } else {
    document.removeEventListener('click', handleClickOutside);
  }
};

const handleClickOutside = (event: MouseEvent) => {
  if (menuRef.value && !menuRef.value.contains(event.target as Node)) {
    showMenu.value = false;
    document.removeEventListener('click', handleClickOutside);
  }
};

const goHome = () => {
  showMenu.value = false;
  router.push('/');
};

const goDocs = () => {
  showMenu.value = false;
  window.open('/docs', '_blank', 'noopener,noreferrer');
};

const logout = async () => {
  try {
    await fetch('api/user/logout', { method: 'POST' });
    console.log('后端注销调用成功');
  } catch (error) {
    console.error('注销调用失败:', error);
  }
  // 尝试清除 token cookie（备份）
  document.cookie = 'token=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;';
  showMenu.value = false;
  router.push('/');
  setTimeout(() => location.reload(), 500);
};

const toggleOptionMenu = (item: ConversationBase, event: MouseEvent) => {
  if (activeMenuId.value === item.conversation_id) {
    activeMenuId.value = null;
    return;
  }
  activeMenuId.value = item.conversation_id;
  const target = event.currentTarget as HTMLElement | null;
  const rect = target?.getBoundingClientRect();
  if (rect) {
    menuPosition.value = {
      top: rect.bottom + 6,
      left: rect.left,
      width: rect.width + 80,
    };
  }
  editingId.value = null;
};

const startEdit = (item: ConversationBase) => {
  editingId.value = item.conversation_id;
  editingText.value = item.abstract || '';
  activeMenuId.value = null;
  nextTick(() => {
    const inputEl = editingInputMap.value[item.conversation_id];
    inputEl?.focus();
  });
};

const saveEdit = async () => {
  if (!editingId.value || isSavingEdit.value) return;
  const newAbstract = editingText.value.trim();
  const current = conversation_list.value.find(
    (conv) => conv.conversation_id === editingId.value,
  );
  if (!newAbstract || newAbstract === current?.abstract) {
    editingId.value = null;
    return;
  }

  isSavingEdit.value = true;
  emit('updateConversationAbstract', editingId.value, newAbstract);
  isSavingEdit.value = false;
  editingId.value = null;
};

const handlePickConversation = (item: { conversation_id: string }) => {
  emit('pickConversation', item.conversation_id);
  activeMenuId.value = null;
};

const confirmDeleteId = ref<string | null>(null);

const handleDelete = (conversationId: string, event: MouseEvent) => {
  const rect = (event.currentTarget as HTMLElement | null)?.getBoundingClientRect();
  if (rect) {
    confirmPosition.value = {
      top: rect.top + rect.height / 2 - 100,
      left: rect.right + 12,
    };
  }
  confirmDeleteId.value = conversationId;
  activeMenuId.value = null;
};

const cancelDelete = () => {
  confirmDeleteId.value = null;
};

const confirmDelete = () => {
  if (!confirmDeleteId.value) return;
  emit('deleteConversation', confirmDeleteId.value);
  confirmDeleteId.value = null;
};

const handleConversationOutside = (event: MouseEvent) => {
  if (
    conversationListRef.value &&
    !conversationListRef.value.contains(event.target as Node)
    && (!confirmRef.value || !confirmRef.value.contains(event.target as Node))
  ) {
    activeMenuId.value = null;
    editingId.value = null;
    confirmDeleteId.value = null;
  }
};

onMounted(() => {
  document.addEventListener('click', handleConversationOutside);
});

onUnmounted(() => {
  document.removeEventListener('click', handleConversationOutside);
});
</script>

<style scoped>
@import '@/assets/css/chat.css';

.disabled-select {
  cursor: not-allowed;
  pointer-events: none;
  opacity: 0.7;
}

/* —— 对话模式切换：分段控件（Segmented Control）形态。
 * 作为侧边栏的重要功能，承担"在 Soul / Task 两种对话模式之间切换"的角色。
 * 设计要点：
 * 1) 顶部分隔线 + 小标题"对话模式"，与上方工具/技能/知识/专家区域做出明确的视觉分块；
 * 2) 双段按钮 + 黑色 thumb 平滑滑动，激活态高对比，未激活态保留可点击线索；
 * 3) 沿用全局黑/白/灰色板，不引入新的强调色，保持整体克制。
 */
.chat-mode-section {
  width: 90%;
  margin: 16px auto 10px;
  padding-top: 14px;
  border-top: 1px solid rgba(0, 0, 0, 0.07);
  display: flex;
  flex-direction: column;
  gap: 8px;
  box-sizing: border-box;
}

.chat-mode-section--collapsed {
  display: none;
}

.chat-mode-header {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
  padding: 0 2px;
  user-select: none;
}

.chat-mode-header-title {
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.6px;
  color: rgb(110, 110, 110);
  text-transform: uppercase;
}

.chat-mode-header-hint {
  font-size: 11px;
  font-weight: 500;
  color: rgb(150, 150, 150);
  letter-spacing: 0.2px;
}

.chat-mode-switch {
  position: relative;
  display: flex;
  width: 100%;
  padding: 4px;
  background-color: rgba(0, 0, 0, 0.05);
  border: 1px solid rgba(0, 0, 0, 0.04);
  border-radius: 12px;
  box-sizing: border-box;
}

/* 滑动 thumb：黑色实块，根据 data-active 切换位置 */
.chat-mode-switch-thumb {
  position: absolute;
  top: 4px;
  left: 4px;
  width: calc(50% - 4px);
  height: calc(100% - 8px);
  background-color: rgb(33, 33, 33);
  border-radius: 9px;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.18), 0 0 0 1px rgba(0, 0, 0, 0.04);
  transition: transform 0.32s cubic-bezier(0.4, 0, 0.2, 1);
  pointer-events: none;
  z-index: 0;
}

.chat-mode-switch[data-active="task"] .chat-mode-switch-thumb {
  transform: translateX(100%);
}

.chat-mode-option {
  position: relative;
  z-index: 1;
  flex: 1;
  min-width: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  height: 34px;
  padding: 0 8px;
  border: none;
  border-radius: 9px;
  background-color: transparent;
  color: rgb(110, 110, 110);
  font-size: 13.5px;
  font-weight: 600;
  letter-spacing: 0.4px;
  cursor: pointer;
  outline: none;
  transition: color 0.25s ease, transform 0.18s ease;
}

.chat-mode-option:hover:not(.chat-mode-option--active) {
  color: rgb(33, 33, 33);
}

.chat-mode-option:active:not(.chat-mode-option--active) {
  transform: scale(0.97);
}

.chat-mode-option--active,
.chat-mode-option--active:hover {
  color: #fff;
}

.chat-mode-option:focus-visible {
  outline: 2px solid rgba(0, 0, 0, 0.25);
  outline-offset: 2px;
}

.chat-mode-option-icon {
  width: 14px;
  height: 14px;
  flex-shrink: 0;
  opacity: 0.9;
  transition: transform 0.25s ease, opacity 0.25s ease;
}

.chat-mode-option--active .chat-mode-option-icon {
  opacity: 1;
}

.chat-mode-option:hover:not(.chat-mode-option--active) .chat-mode-option-icon {
  transform: scale(1.06);
}

.chat-mode-option-label {
  line-height: 1;
}

.user-option {
  height: 5%;
  display: flex;
  align-items: center;
  justify-content: flex-start;
  padding: 0 10px;
  border-top: 1px solid #eee;
  position: relative;
  width: 100%;
  box-sizing: border-box;
}

.user-button {
  display: flex;
  align-items: center;
  justify-content: flex-start;
  gap: 6px;
  width: 100%;
  min-width: 0;
  box-sizing: border-box;
  background: none;
  border: none;
  cursor: pointer;
  padding: 6px 8px;
  border-radius: 8px;
  transition: background 0.2s;
  text-align: left;
}

.user-button:hover {
  background: rgba(226, 226, 226, 0.800);
}

.user-icon {
  flex-shrink: 0;
}

.user-display-name {
  min-width: 0;
  flex: 1;
  font-size: 14px;
  font-weight: 500;
  color: rgb(61, 61, 61);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.user-display-name.hidden-text {
  flex: 0 0 0;
  width: 0;
  min-width: 0;
  margin: 0;
  padding: 0;
  overflow: hidden;
}

.user-menu {
  position: absolute;
  bottom: 100%;
  left: 15px;
  background: white;
  border: 1px solid #ddd;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.1);
  z-index: 1000;
  font-size: 20px;
}

.menu-item {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 8px 12px;
  background: none;
  border: none;
  text-align: left;
  cursor: pointer;
  transition: background 0.2s;
}

.menu-item:hover {
  background: #f0f0f0;
}
</style>
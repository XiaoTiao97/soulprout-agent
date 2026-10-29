<template>
  <div class="dk-frame">
    <main class="dk-content">
      <router-view />
    </main>
    <Teleport v-if="shell.panel" to="#dk-embed-host">
      <DesktopPanel
        :page="shell.panel"
        :state="shell.state"
        @close="shell.panel = ''"
        @refresh="poll"
      />
    </Teleport>
    <ApprovalDialog />
    <TitleBar />
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, provide, reactive } from 'vue'
import { useRouter } from 'vue-router'
import TitleBar from './components/TitleBar.vue'
import ApprovalDialog from './components/ApprovalDialog.vue'
import DesktopPanel from './panel/DesktopPanel.vue'
import { getState, openOfficialDocs } from './desktopApi.js'
import { useStrings } from './strings.js'

const router = useRouter()
const s = useStrings()
const shell = reactive({
  panel: '', // '' | 'settings' | 'connect'
  state: null,
})
let timer = null

async function poll() {
  try {
    shell.state = await getState()
  } catch {
    shell.state = null
  }
}

provide('desktopShell', shell)

// 左下角用户菜单里的桌面端入口（web 的 ConversationWindow 通过 inject('desktopMenu') 取用）：
// 第一个是设置，第二个是多端互联；网页端的「主页」「下载客户端」在桌面端不需要，也由它隐藏。
const ICON_SETTINGS =
  '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>'
const ICON_CONNECT =
  '<rect x="2" y="5" width="13" height="10" rx="2"/><path d="M6 19h5M8.5 15v4"/><rect x="17.5" y="8" width="4.5" height="11" rx="1.5"/>'

const desktopMenu = reactive({
  items: computed(() => [
    {
      key: 'settings',
      label: s.value.menuSettings,
      icon: ICON_SETTINGS,
      onClick: () => (shell.panel = 'settings'),
    },
    { key: 'connect', label: s.value.menuConnect, icon: ICON_CONNECT, onClick: () => (shell.panel = 'connect') },
  ]),
  openDocs: () => {
    openOfficialDocs()
  },
})
provide('desktopMenu', desktopMenu)

const DRAG_SELECTORS = '.register-header, .agent-option-top-bar, .dk-chat-drag'

function markDragRegions() {
  document.querySelectorAll(DRAG_SELECTORS).forEach((el) => {
    el.setAttribute('data-tauri-drag-region', '')
  })
}

router.afterEach(() => {
  shell.panel = ''
  requestAnimationFrame(markDragRegions)
})

onMounted(() => {
  poll()
  timer = setInterval(poll, 4000)
  markDragRegions()
})
onBeforeUnmount(() => clearInterval(timer))
</script>

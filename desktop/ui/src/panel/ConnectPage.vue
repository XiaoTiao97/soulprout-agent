<template>
  <div class="dk-page">
    <div class="dk-page-head">
      <h1>{{ s.connectTitle }}</h1>
      <button class="dk-icon-btn is-round" :aria-label="s.serviceSettings" @click="serviceOpen = true">
        <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="12" r="3" />
          <path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z" />
        </svg>
      </button>
    </div>
    <p class="dk-page-sub">{{ s.connectSub }}</p>

    <p v-if="!state" class="dk-note">{{ s.loadFailed }}</p>

    <template v-else>
      <p v-if="!state.gateway.enabled" class="dk-note">{{ s.gatewayDisabled }}</p>
      <p v-else-if="!state.gateway.url" class="dk-note">{{ s.gatewayWaiting }}</p>

      <div v-else class="dk-list dk-channel-list">
        <div v-for="channel in channels" :key="channel.id" class="dk-channel" :class="{ 'is-open': open === channel.id }">
          <button class="dk-channel-head" @click="toggle(channel.id)">
            <img class="dk-channel-logo" :src="channel.logo" alt="" />
            <span class="dk-channel-main">
              <span class="dk-channel-name">{{ s.channels[channel.id].name }}</span>
              <span class="dk-channel-desc">{{ s.channels[channel.id].desc }}</span>
            </span>
            <span class="dk-channel-status" :class="{ 'is-on': isOn(channel.id) }">
              <span class="dk-dot" :class="{ 'is-online': isOn(channel.id) }" />
              {{ summary(channel.id) }}
            </span>
            <svg class="dk-chevron" width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
              <path d="M4 6l4 4 4-4" />
            </svg>
          </button>
          <div v-if="open === channel.id" class="dk-channel-body">
            <component
              :is="channel.component"
              :status="statuses[channel.id]"
              @watch="watchConnected(channel.id)"
              @refresh="loadStatus(channel.id)"
            />
          </div>
        </div>
      </div>
    </template>

    <ServiceDialog v-if="serviceOpen && state" :state="state" @close="serviceOpen = false" @changed="$emit('refresh')" />
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { gateway } from '../desktopApi.js'
import { useStrings } from '../strings.js'
import ServiceDialog from './ServiceDialog.vue'
import WeixinChannel from './channels/WeixinChannel.vue'
import FeishuChannel from './channels/FeishuChannel.vue'
import WecomChannel from './channels/WecomChannel.vue'
import XiaoaiChannel from './channels/XiaoaiChannel.vue'
import RokidChannel from './channels/RokidChannel.vue'
import wechatLogo from '../../../../gateway/static/wechat_logo.png'
import larkLogo from '../../../../gateway/static/lark_logo.png'
import wecomLogo from '../../../../gateway/static/wecom_logo.png'
import xiaoaiLogo from '../../../../gateway/static/xiaoai_logo.png'
import rokidLogo from '../../../../gateway/static/rokid_logo.png'

const props = defineProps({ state: { type: Object, default: null } })
defineEmits(['refresh'])

const s = useStrings()
const serviceOpen = ref(false)
const open = ref('')
const statuses = reactive({})
let timer = null
let watching = 0

const channels = [
  { id: 'weixin', logo: wechatLogo, component: WeixinChannel },
  { id: 'feishu', logo: larkLogo, component: FeishuChannel },
  { id: 'wecom', logo: wecomLogo, component: WecomChannel },
  { id: 'xiaoai', logo: xiaoaiLogo, component: XiaoaiChannel },
  { id: 'rokid', logo: rokidLogo, component: RokidChannel },
]

const ready = computed(() => !!(props.state?.gateway?.enabled && props.state?.gateway?.url))

async function loadStatus(id) {
  try {
    statuses[id] = await gateway.get(`api/${id}/status`)
  } catch {
    /* gateway 还没起来或暂时不可用：保留上一次的结果 */
  }
  return statuses[id]
}

const isConnected = (st) => !!st?.connected

function isOn(id) {
  const st = statuses[id]
  return id === 'rokid' ? !!st?.configured : isConnected(st)
}

function summary(id) {
  const st = statuses[id]
  if (!st) return ''
  if (id === 'rokid') return st.configured ? s.value.rokidReady : s.value.notSet
  if (st.connected) {
    const name = st.account_id || st.bot_name || st.device_name
    return name ? `${s.value.connected} · ${name}` : s.value.connected
  }
  const configured = id === 'weixin' ? (st.saved_accounts || []).length > 0 : !!st.configured
  return configured ? s.value.configuredIdle : s.value.notSet
}

// 登录 / 保存凭证 / 重连之后，gateway 要花几秒才连上：连续查询几次状态直到连上
async function watchConnected(id) {
  const token = ++watching
  for (let i = 0; i < 15 && token === watching; i += 1) {
    await new Promise((resolve) => setTimeout(resolve, 1000))
    const st = await loadStatus(id)
    if (isConnected(st)) return
  }
}

function toggle(id) {
  open.value = open.value === id ? '' : id
  if (open.value === 'rokid') loadStatus('rokid')
}

async function loadAll() {
  if (!ready.value) return
  await Promise.all(['weixin', 'feishu', 'wecom', 'xiaoai'].map(loadStatus))
}

watch(ready, (value) => {
  if (value) {
    loadAll()
    loadStatus('rokid') // 会联网同步账号里的密钥，只在进入页面时取一次
  }
})

onMounted(() => {
  if (ready.value) {
    loadAll()
    loadStatus('rokid')
  }
  timer = setInterval(loadAll, 5000)
})
onBeforeUnmount(() => {
  clearInterval(timer)
  watching += 1
})
</script>

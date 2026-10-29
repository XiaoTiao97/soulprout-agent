<template>
  <div v-if="current" class="dk-overlay dk-approval-overlay" role="dialog" aria-modal="true">
    <div class="dk-dialog dk-approval">
      <div class="dk-dialog-head">
        <span class="dk-shield">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M12 3l8 3v6c0 4.5-3.2 8.2-8 9-4.8-.8-8-4.5-8-9V6z" />
            <path d="M12 8v5M12 16h.01" />
          </svg>
        </span>
        <h3>{{ s.approvalTitle }}</h3>
        <span v-if="queue.length > 1" class="dk-queue">{{ s.queued(queue.length - 1) }}</span>
      </div>

      <p class="dk-muted">{{ s.approvalIntro }}</p>
      <div class="dk-approval-title">{{ current.title }}</div>
      <pre v-if="current.detail" class="dk-approval-detail">{{ current.detail }}</pre>
      <p v-if="current.reason" class="dk-approval-reason">
        <b>{{ s.approvalReason }}：</b>{{ current.reason }}
      </p>
      <p class="dk-muted dk-small">{{ s.approvalFoot }}</p>

      <div class="dk-dialog-actions">
        <button class="dk-btn" :disabled="busy" @click="decide('reject')">{{ s.reject }}</button>
        <button class="dk-btn is-primary" :disabled="busy" @click="decide('allow')">{{ s.allow }}</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { decideApproval, subscribeApprovals } from '../desktopApi.js'
import { useStrings } from '../strings.js'

const s = useStrings()
const queue = ref([])
const busy = ref(false)
const current = computed(() => queue.value[0] || null)
let unsubscribe = null

function onEvent(event) {
  if (event.type === 'request' && event.request) {
    if (!queue.value.some((item) => item.id === event.request.id)) queue.value.push(event.request)
  } else if (event.type === 'resolved') {
    // 已经被别处处理（比如超时、云端取消了这次调用）
    queue.value = queue.value.filter((item) => item.id !== event.id)
  }
}

async function decide(decision) {
  const item = current.value
  if (!item || busy.value) return
  busy.value = true
  try {
    await decideApproval(item.id, decision)
  } catch {
    /* 请求可能已经失效，下面都会把它移出队列 */
  } finally {
    queue.value = queue.value.filter((entry) => entry.id !== item.id)
    busy.value = false
  }
}

onMounted(() => {
  unsubscribe = subscribeApprovals(onEvent)
})
onBeforeUnmount(() => {
  if (unsubscribe) unsubscribe()
})
</script>

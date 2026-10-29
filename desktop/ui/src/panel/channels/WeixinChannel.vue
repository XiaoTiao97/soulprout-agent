<template>
  <div class="dk-detail">
    <div class="dk-field-line">
      <span class="dk-row-label">{{ s.weixinAccounts }}</span>
      <span class="dk-mono">{{ accounts.length ? accounts.join('、') : s.none }}</span>
    </div>
    <QrLogin platform="weixin" @connected="$emit('watch')" />
    <ReconnectBar v-if="accounts.length" platform="weixin" @watch="$emit('watch')" />
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useStrings } from '../../strings.js'
import QrLogin from './QrLogin.vue'
import ReconnectBar from './ReconnectBar.vue'

const props = defineProps({ status: { type: Object, default: null } })
defineEmits(['watch'])

const s = useStrings()
const accounts = computed(() => props.status?.saved_accounts || [])
</script>

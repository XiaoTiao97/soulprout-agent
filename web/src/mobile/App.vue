<template>
  <div class="app-root">
    <div v-if="booting" class="booting">{{ t('mobile.entering') }}</div>
    <MobileLogin v-else-if="!loggedIn" @logged-in="loggedIn = true" />
    <MobileChat v-else @logout="onLogout" />
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import MobileLogin from './MobileLogin.vue'
import MobileChat from './MobileChat.vue'
import { clearToken, http } from './api'

const { t } = useI18n()
const booting = ref(true)
const loggedIn = ref(false)

function onLogout() {
  clearToken()
  loggedIn.value = false
}

onMounted(async () => {
  try {
    const response = await http.get('/api/user/me')
    loggedIn.value = !!response.data?.success
  } catch {
    loggedIn.value = false
  } finally {
    booting.value = false
  }
})
</script>

<style scoped>
.app-root,
.booting {
  height: 100%;
}

.booting {
  display: flex;
  align-items: center;
  justify-content: center;
  color: #6b7280;
  background: #f2f2f2;
}
</style>

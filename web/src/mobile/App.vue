<template>
  <div class="app-root">
    <div v-if="booting" class="booting">{{ t('mobile.entering') }}</div>
    <MobileLogin v-else-if="!loggedIn" @logged-in="loggedIn = true" />
    <MobileChat v-else @logout="onLogout" />

    <!-- 临时：唤醒词最小测试入口（测试完成后整块删除，连同 ./wake 目录） -->
    <button v-if="!booting && !showWakeTest && !showStandby" type="button" class="wake-fab" @click="showWakeTest = true">唤醒测试</button>
    <WakeTest v-if="showWakeTest" @close="showWakeTest = false" />

    <!-- 临时：待命（Standby）调试入口，样式与功能确认后再并入正式界面 -->
    <button
      v-if="loggedIn && !booting && !showWakeTest && !showStandby"
      type="button"
      class="wake-fab standby-fab"
      @click="showStandby = true"
    >
      {{ t('standby.entry') }}
    </button>
    <StandbyDemo v-if="showStandby" @close="showStandby = false" />
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import MobileLogin from './MobileLogin.vue'
import MobileChat from './MobileChat.vue'
import WakeTest from './wake/WakeTest.vue'
import StandbyDemo from './standby/StandbyDemo.vue'
import { clearToken, http } from './api'

const { t } = useI18n()
const booting = ref(true)
const loggedIn = ref(false)
const showWakeTest = ref(false)
const showStandby = ref(false)

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

.wake-fab {
  position: fixed;
  right: 10px;
  bottom: calc(env(safe-area-inset-bottom, 0px) + 150px);
  z-index: 9000;
  border: 0;
  border-radius: 16px;
  padding: 6px 12px;
  font-size: 12px;
  color: #fff;
  background: rgba(16, 185, 129, 0.9);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
}

.standby-fab {
  bottom: calc(env(safe-area-inset-bottom, 0px) + 196px);
  background: rgba(99, 102, 241, 0.92);
}
</style>

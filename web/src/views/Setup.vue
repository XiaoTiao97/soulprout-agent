<template>
  <div class="soulprout-setup-page">
    <header class="setup-header">
      <div class="header-inner">
        <a href="/" class="logo-link">
          <img src="@/assets/images/logo.png" alt="Soulprout" class="header-logo" />
        </a>
        <LocaleSwitcher />
      </div>
    </header>

    <main class="setup-main">
      <div class="setup-card">
        <h1 class="setup-title">{{ t('setup.title') }}</h1>
        <p class="setup-desc">{{ t('setup.desc') }}</p>

        <form class="setup-form" @submit.prevent="handleSubmit">
          <input
            class="input-field"
            type="text"
            v-model="username"
            :placeholder="t('setup.nicknamePlaceholder')"
            maxlength="32"
            autocomplete="nickname"
            required
            ref="inputRef"
          />

          <span class="error-text" :class="{ ok: messageOk }">{{ message }}</span>

          <button class="submit-btn" type="submit" :disabled="submitting">
            <span>{{ submitting ? t('setup.entering') : t('setup.start') }}</span>
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.5">
              <path d="M5 12h14M12 5l7 7-7 7" />
            </svg>
          </button>
        </form>

        <p class="hint-text">{{ t('setup.hint') }}</p>
      </div>
    </main>

    <div class="bg-decoration" aria-hidden="true">
      <div class="bg-ring bg-ring-1" />
      <div class="bg-ring bg-ring-2" />
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import LocaleSwitcher from '@/components/LocaleSwitcher.vue'

const router = useRouter()
const { t } = useI18n()
const username = ref('')
const message = ref('')
const messageOk = ref(false)
const submitting = ref(false)
const inputRef = ref(null)

onMounted(() => {
  inputRef.value?.focus()
})

async function handleSubmit() {
  const name = username.value.trim()
  if (!name) {
    message.value = t('setup.nicknameRequired')
    return
  }

  submitting.value = true
  message.value = ''

  try {
    const res = await fetch('/api/user/sso-token', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ user_id: 'private', username: name }),
    })
    const data = await res.json()

    if (data.success) {
      messageOk.value = true
      message.value = t('setup.successRedirect')
      window.location.href = '/chat'
    } else {
      message.value = data.message || t('setup.createFailed')
    }
  } catch (e) {
    message.value = t('setup.networkError')
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.soulprout-setup-page {
  min-height: 100vh;
  background: #f8fafa;
  display: flex;
  flex-direction: column;
  position: relative;
  overflow: hidden;
}

.setup-header {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  z-index: 100;
  padding: 1rem 2rem;
  background: rgba(248, 250, 250, 0.9);
  backdrop-filter: blur(12px);
  border-bottom: 1px solid rgba(15, 15, 15, 0.06);
}

.header-inner {
  max-width: 1200px;
  margin: 0 auto;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.logo-link {
  display: inline-block;
  text-decoration: none;
}

.header-logo {
  height: 28px;
  display: block;
}

.setup-main {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 6rem 1.5rem 3rem;
}

.setup-card {
  width: 100%;
  max-width: 420px;
  background: #ffffff;
  border: 1px solid rgba(15, 15, 15, 0.08);
  border-radius: 1.25rem;
  padding: 2.5rem 2.5rem 2rem;
  box-shadow: 0 4px 40px rgba(0, 0, 0, 0.06);
  position: relative;
  z-index: 10;
}

.setup-title {
  font-size: 1.5rem;
  font-weight: 700;
  color: #0f0f0f;
  letter-spacing: -0.02em;
  margin: 0 0 0.5rem;
}

.setup-desc {
  font-size: 0.9rem;
  color: rgba(15, 15, 15, 0.5);
  margin: 0 0 1.75rem;
}

.setup-form {
  display: flex;
  flex-direction: column;
  gap: 0.875rem;
}

.input-field {
  width: 100%;
  padding: 0.75rem 1rem;
  background: #f8fafa;
  border: 1px solid rgba(15, 15, 15, 0.1);
  border-radius: 0.625rem;
  font-size: 0.9375rem;
  color: #0f0f0f;
  outline: none;
  transition: border-color 0.2s, box-shadow 0.2s;
  box-sizing: border-box;
}

.input-field:focus {
  border-color: rgba(30, 180, 140, 0.5);
  box-shadow: 0 0 0 3px rgba(30, 180, 140, 0.08);
}

.input-field::placeholder {
  color: rgba(15, 15, 15, 0.3);
}

.error-text {
  font-size: 0.8125rem;
  color: #e55;
  min-height: 1.2em;
  display: block;
}

.error-text.ok {
  color: rgb(30, 180, 140);
}

.submit-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  width: 100%;
  padding: 0.8125rem 1.5rem;
  background: #0f0f0f;
  color: #ffffff;
  border: none;
  border-radius: 0.625rem;
  font-size: 0.9375rem;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.2s, transform 0.15s;
}

.submit-btn:hover:not(:disabled) {
  background: #1a1a1a;
}

.submit-btn:active:not(:disabled) {
  transform: scale(0.98);
}

.submit-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.hint-text {
  font-size: 0.8rem;
  color: rgba(15, 15, 15, 0.35);
  text-align: center;
  margin: 1.25rem 0 0;
}

/* Decorative rings */
.bg-decoration {
  position: fixed;
  inset: 0;
  pointer-events: none;
  z-index: 0;
}

.bg-ring {
  position: absolute;
  border-radius: 50%;
  border: 1px solid rgba(30, 180, 140, 0.06);
}

.bg-ring-1 {
  width: 800px;
  height: 800px;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
}

.bg-ring-2 {
  width: 500px;
  height: 500px;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
}
</style>

<template>
  <div class="login-screen">
    <img src="@/assets/images/logo.png" alt="Soulprout" class="logo" />
    <h1>{{ t('register.title') }}</h1>
    <p class="desc">{{ t('register.desc') }}</p>

    <form class="form" @submit.prevent="submitForm">
      <input
        v-model="email"
        class="field"
        type="email"
        autocomplete="email"
        :placeholder="t('register.emailPlaceholder')"
        required
      />
      <div class="code-row">
        <input
          v-model="code"
          class="field"
          type="text"
          inputmode="numeric"
          maxlength="6"
          :placeholder="t('register.codePlaceholder')"
          required
        />
        <button type="button" class="code-btn" :disabled="codeBtnDisabled" @click="sendCode">
          {{ codeBtnLabel }}
        </button>
      </div>
      <span class="message" :class="{ ok: messageOk }">{{ message }}</span>
      <button class="submit" type="submit" :disabled="submitting">
        {{ submitting ? t('register.submitting') : t('register.submit') }}
      </button>
    </form>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { apiFetch, setToken } from './api'

const emit = defineEmits(['logged-in'])
const { t } = useI18n()

const email = ref('')
const code = ref('')
const message = ref('')
const messageOk = ref(false)
const sending = ref(false)
const submitting = ref(false)
const countdown = ref(0)
let countdownTimer = null

const codeBtnDisabled = computed(() => sending.value || countdown.value > 0 || !email.value.trim())
const codeBtnLabel = computed(() => {
  if (countdown.value > 0) return t('register.resendIn', { n: countdown.value })
  if (sending.value) return t('register.sending')
  return t('register.getCode')
})

function isValidEmail(value) {
  return /^[\w.%+-]+@[\w.-]+\.[A-Za-z]{2,}$/.test((value || '').trim())
}

function showMessage(text, ok = false) {
  message.value = text
  messageOk.value = ok
}

function startCountdown(seconds = 60) {
  countdown.value = seconds
  if (countdownTimer) clearInterval(countdownTimer)
  countdownTimer = setInterval(() => {
    countdown.value -= 1
    if (countdown.value <= 0) {
      clearInterval(countdownTimer)
      countdownTimer = null
    }
  }, 1000)
}

onBeforeUnmount(() => {
  if (countdownTimer) clearInterval(countdownTimer)
})

async function sendCode() {
  if (!isValidEmail(email.value)) {
    showMessage(t('register.invalidEmail'))
    return
  }
  sending.value = true
  showMessage('')
  try {
    const res = await apiFetch('/api/user/email/send-code', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: email.value.trim() }),
    })
    const data = await res.json()
    if (data.success) {
      showMessage(t('register.codeSent'), true)
      startCountdown(60)
    } else {
      showMessage(data.message || t('register.sendFailed'))
    }
  } catch (err) {
    showMessage(t('register.networkError', { msg: err.message }))
  } finally {
    sending.value = false
  }
}

async function submitForm() {
  if (!isValidEmail(email.value)) {
    showMessage(t('register.invalidEmail'))
    return
  }
  if (!/^\d{4,8}$/.test(code.value.trim())) {
    showMessage(t('register.invalidCode'))
    return
  }
  submitting.value = true
  showMessage('')
  try {
    const res = await apiFetch('/api/user/email/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        email: email.value.trim(),
        code: code.value.trim(),
      }),
    })
    const data = await res.json()
    if (data.success) {
      setToken(data.token)
      emit('logged-in')
    }
    else showMessage(data.message || t('register.sendFailed'))
  } catch (err) {
    showMessage(t('register.networkError', { msg: err.message }))
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.login-screen {
  min-height: 100%;
  box-sizing: border-box;
  padding: calc(48px + env(safe-area-inset-top)) 24px calc(32px + env(safe-area-inset-bottom));
  background:
    radial-gradient(circle at 10% 0%, rgba(30, 180, 140, 0.16), transparent 42%),
    #f7f7f7;
}

.logo {
  width: 132px;
  height: auto;
  display: block;
  margin-bottom: 28px;
}

h1 {
  margin: 0 0 8px;
  font-size: 28px;
  letter-spacing: -0.03em;
  color: #0f0f0f;
}

.desc {
  margin: 0 0 28px;
  color: rgba(15, 15, 15, 0.45);
  font-size: 14px;
  line-height: 1.6;
  font-weight: 300;
}

.form {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.field {
  width: 100%;
  box-sizing: border-box;
  padding: 14px 14px;
  border: 1px solid rgba(15, 15, 15, 0.1);
  border-radius: 12px;
  font-size: 16px;
  color: #0f0f0f;
  background: #fff;
  outline: none;
}

.field:focus {
  border-color: #1eb48c;
  box-shadow: 0 0 0 3px rgba(30, 180, 140, 0.12);
}

.code-row {
  display: flex;
  gap: 8px;
}

.code-row .field {
  flex: 1;
  min-width: 0;
}

.code-btn {
  flex-shrink: 0;
  padding: 0 12px;
  border-radius: 12px;
  border: 1px solid rgba(30, 180, 140, 0.4);
  background: #fff;
  color: #1eb48c;
  font-size: 14px;
}

.code-btn:disabled {
  color: rgba(15, 15, 15, 0.3);
  border-color: rgba(15, 15, 15, 0.12);
  background: #f3f3f3;
}

.message {
  min-height: 1.2em;
  font-size: 13px;
  color: #e55a5a;
}

.message.ok {
  color: #1eb48c;
}

.submit {
  margin-top: 4px;
  height: 48px;
  border: none;
  border-radius: 999px;
  background: #1eb48c;
  color: #fff;
  font-size: 16px;
  font-weight: 600;
}

.submit:disabled {
  opacity: 0.7;
}
</style>

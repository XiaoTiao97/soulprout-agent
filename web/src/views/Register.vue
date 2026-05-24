<template>
  <div class="soulprout-register-page">
    <!-- Header -->
    <header class="register-header">
      <div class="header-inner">
        <a href="/" class="logo-link">
          <img src="@/assets/images/logo.png" alt="Soulprout" class="header-logo" />
        </a>
      </div>
    </header>

    <!-- Main -->
    <main class="register-main">
      <div class="register-card">
        <h1 class="register-title">登录 / 注册 Soulprout</h1>
        <p class="register-desc">
          输入邮箱即可登录，新邮箱将自动为你创建账号。
        </p>

        <form class="register-form" @submit.prevent="submitForm">
          <input
            class="input-field"
            type="email"
            v-model="email"
            placeholder="邮箱地址"
            autocomplete="email"
            required
          />

          <div class="code-row">
            <input
              class="input-field code-input"
              type="text"
              v-model="code"
              placeholder="6 位邮箱验证码"
              inputmode="numeric"
              maxlength="6"
              required
            />
            <button
              type="button"
              class="code-btn"
              :disabled="codeBtnDisabled"
              @click="sendCode"
            >
              {{ countdown > 0 ? `${countdown}s 后重发` : (sending ? '发送中…' : '获取验证码') }}
            </button>
          </div>

          <input
            class="input-field"
            type="text"
            v-model="username"
            placeholder="昵称（可选，首次登录用）"
            maxlength="32"
          />

          <span class="error-text" :class="{ ok: messageOk }">{{ message }}</span>

          <button class="submit-btn" type="submit" :disabled="submitting">
            <span>{{ submitting ? '登录中…' : '登录 / 注册' }}</span>
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.5">
              <path d="M5 12h14M12 5l7 7-7 7" />
            </svg>
          </button>
        </form>

        <p class="hint-text">
          首次使用？直接输入邮箱获取验证码即可自动注册。
        </p>
      </div>
    </main>

    <!-- Decorative background -->
    <div class="bg-decoration" aria-hidden="true">
      <div class="bg-ring bg-ring-1" />
      <div class="bg-ring bg-ring-2" />
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()
const email = ref('')
const code = ref('')
const username = ref('')

const message = ref('')
const messageOk = ref(false)
const sending = ref(false)
const submitting = ref(false)
const countdown = ref(0)
let countdownTimer = null

const codeBtnDisabled = computed(
  () => sending.value || countdown.value > 0 || !email.value.trim(),
)

onMounted(async () => {
  try {
    const res = await fetch('/api/user/me')
    const data = await res.json()
    if (data.success) {
      router.replace('/chat')
    }
  } catch {
    // 未登录或网络错误，继续显示登录页
  }
})

function isValidEmail(value) {
  return /^[\w.%+-]+@[\w.-]+\.[A-Za-z]{2,}$/.test((value || '').trim())
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

function showMessage(text, ok = false) {
  message.value = text
  messageOk.value = ok
}

async function sendCode() {
  if (!isValidEmail(email.value)) {
    showMessage('请填写正确的邮箱地址')
    return
  }
  sending.value = true
  showMessage('')
  try {
    const res = await fetch('/api/user/email/send-code', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: email.value.trim() }),
    })
    const data = await res.json()
    if (data.success) {
      showMessage('验证码已发送，请查收邮箱', true)
      startCountdown(60)
    } else {
      showMessage(data.message || '发送失败，请稍后重试')
    }
  } catch (err) {
    showMessage('网络错误：' + err.message)
  } finally {
    sending.value = false
  }
}

async function submitForm() {
  if (!isValidEmail(email.value)) {
    showMessage('请填写正确的邮箱地址')
    return
  }
  if (!/^\d{4,8}$/.test(code.value.trim())) {
    showMessage('请填写正确的验证码')
    return
  }
  submitting.value = true
  showMessage('')
  try {
    const res = await fetch('/api/user/email/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        email: email.value.trim(),
        code: code.value.trim(),
        username: username.value.trim() || null,
      }),
    })
    const data = await res.json()
    if (data.success) {
      window.location.href = '/chat'
    } else {
      showMessage(data.message || '登录失败，请重试')
    }
  } catch (err) {
    showMessage('网络错误：' + err.message)
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.soulprout-register-page {
  font-family: 'Noto Sans SC', -apple-system, BlinkMacSystemFont, 'PingFang SC', sans-serif;
  min-height: 100vh;
  background: #ffffff;
  display: flex;
  flex-direction: column;
  position: relative;
  overflow: hidden;
}

/* Header */
.register-header {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  z-index: 50;
  background: rgba(255, 255, 255, 0.6);
  backdrop-filter: blur(24px) saturate(150%);
  -webkit-backdrop-filter: blur(24px) saturate(150%);
  border-bottom: 1px solid rgba(30, 180, 140, 0.06);
}

.header-inner {
  padding: 1rem 2rem;
  display: flex;
  align-items: center;
}

.logo-link { display: inline-flex; align-items: center; text-decoration: none; }
.header-logo { height: 2.5rem; width: auto; }

/* Main */
.register-main {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 7rem 1.5rem 3rem;
  position: relative;
  z-index: 10;
}

.register-card {
  width: 100%;
  max-width: 440px;
  background: rgba(255, 255, 255, 0.85);
  backdrop-filter: blur(20px);
  border: 1px solid rgba(15, 15, 15, 0.06);
  border-radius: 1.5rem;
  padding: 2.5rem;
  box-shadow: 0 0 60px rgba(30, 180, 140, 0.06), 0 4px 24px rgba(0, 0, 0, 0.04);
}

.register-title {
  font-size: 1.75rem;
  font-weight: 700;
  color: #0f0f0f;
  letter-spacing: -0.025em;
  margin-bottom: 0.5rem;
  line-height: 1.2;
}

.register-desc {
  font-size: 0.9rem;
  color: rgba(15, 15, 15, 0.4);
  margin-bottom: 2rem;
  font-weight: 300;
  line-height: 1.6;
}

.register-form { display: flex; flex-direction: column; gap: 0.875rem; }

.input-field {
  padding: 0.8rem 1rem;
  border: 1px solid rgba(15, 15, 15, 0.1);
  border-radius: 0.625rem;
  font-size: 0.95rem;
  font-family: inherit;
  color: #0f0f0f;
  background: #ffffff;
  transition: border-color 0.3s ease, box-shadow 0.3s ease;
  outline: none;
  width: 100%;
}
.input-field::placeholder { color: rgba(15, 15, 15, 0.3); }
.input-field:focus {
  border-color: #1eb48c;
  box-shadow: 0 0 0 3px rgba(30, 180, 140, 0.1);
}

/* 验证码行 */
.code-row { display: flex; gap: 0.625rem; }
.code-input { flex: 1; }
.code-btn {
  flex-shrink: 0;
  padding: 0 1rem;
  background: #ffffff;
  color: #1eb48c;
  border: 1px solid rgba(30, 180, 140, 0.4);
  border-radius: 0.625rem;
  font-size: 0.85rem;
  font-family: inherit;
  cursor: pointer;
  white-space: nowrap;
  transition: all 0.25s ease;
  min-width: 7.5rem;
}
.code-btn:hover:not(:disabled) {
  background: rgba(30, 180, 140, 0.08);
  border-color: #1eb48c;
}
.code-btn:disabled {
  color: rgba(15, 15, 15, 0.3);
  border-color: rgba(15, 15, 15, 0.12);
  background: #f7f7f7;
  cursor: not-allowed;
}

.error-text {
  color: #e55a5a;
  font-size: 0.85rem;
  min-height: 1.2rem;
  display: block;
}
.error-text.ok { color: #1eb48c; }

.submit-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 0.875rem 2rem;
  background: #1eb48c;
  color: #ffffff;
  border: none;
  border-radius: 60px;
  font-size: 1rem;
  font-weight: 500;
  font-family: inherit;
  letter-spacing: 0.05em;
  cursor: pointer;
  margin-top: 0.5rem;
  transition: all 0.4s cubic-bezier(0.25, 1, 0.5, 1);
  box-shadow: 0 4px 20px rgba(30, 180, 140, 0.22);
}
.submit-btn:hover:not(:disabled) {
  background: #22c99d;
  box-shadow: 0 8px 28px rgba(30, 180, 140, 0.3);
  transform: translateY(-2px);
}
.submit-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
.submit-btn svg { transition: transform 0.3s ease; }
.submit-btn:hover:not(:disabled) svg { transform: translateX(3px); }

.hint-text {
  margin-top: 1.5rem;
  text-align: center;
  font-size: 0.85rem;
  color: rgba(15, 15, 15, 0.4);
}

/* Decorative background */
.bg-decoration {
  position: fixed;
  inset: 0;
  z-index: 0;
  pointer-events: none;
  display: flex;
  align-items: center;
  justify-content: center;
}
.bg-ring { position: absolute; border-radius: 50%; border: 1px solid rgba(30, 180, 140, 0.05); }
.bg-ring-1 { width: 800px; height: 800px; }
.bg-ring-2 { width: 500px; height: 500px; border-color: rgba(30, 180, 140, 0.07); }

@media (max-width: 480px) {
  .register-card { padding: 2rem 1.5rem; border-radius: 1rem; }
  .register-title { font-size: 1.5rem; }
  .code-row { flex-direction: column; }
  .code-btn { width: 100%; padding: 0.7rem; }
}
</style>

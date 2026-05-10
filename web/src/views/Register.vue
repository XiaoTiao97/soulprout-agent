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
        <h1 class="register-title">
          {{ mode === 'register' ? '创建 Soulprout 账号' : '登录 Soulprout' }}
        </h1>
        <p class="register-desc">
          {{ mode === 'register' ? '创建一个账号，开始您的智能之旅' : '输入您的账号信息，继续您的智能之旅' }}
        </p>

        <form class="register-form" @submit.prevent="submitForm">
          <input
            v-if="mode === 'register'"
            class="input-field"
            type="text"
            v-model="username"
            placeholder="输入昵称"
            required
          />
          <input class="input-field" type="text" v-model="usernumber" placeholder="输入账号" required />
          <input class="input-field" type="password" v-model="userpwd" placeholder="输入密码" required />
          <span class="error-text">{{ errorText }}</span>
          <button class="submit-btn" type="submit">
            <span>{{ mode === 'register' ? '创建并登录' : '登录' }}</span>
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.5">
              <path d="M5 12h14M12 5l7 7-7 7" />
            </svg>
          </button>
        </form>

        <p class="toggle-text">
          {{ mode === 'register' ? '已有账号？' : '没有账号？' }}
          <a class="toggle-link" @click.prevent="toggleMode">
            {{ mode === 'register' ? '立即登录' : '立即创建' }}
          </a>
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
import { ref } from 'vue'

const mode = ref('register')
const username = ref('')
const usernumber = ref('')
const userpwd = ref('')
const errorText = ref('')

const toggleMode = () => {
  mode.value = mode.value === 'register' ? 'login' : 'register'
  errorText.value = ''
  if (mode.value === 'login') {
    username.value = ''
  }
}

const submitForm = async () => {
  if (mode.value === 'register') {
    if (!username.value.trim() || !usernumber.value.trim() || !userpwd.value.trim()) {
      errorText.value = '所有字段均为必填'
      return
    }
    try {
      const res = await fetch('/api/user/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: username.value, user_id: usernumber.value, userpwd: userpwd.value }),
      })
      const data = await res.json()
      if (data.success) {
        window.location.href = '/chat'
      } else if (data.code === 1001) {
        errorText.value = '账号重复啦，换一个吧！'
        usernumber.value = ''
      } else {
        errorText.value = '创建失败，请稍后再试'
      }
    } catch (error) {
      errorText.value = '创建失败: ' + error.message
    }
  } else {
    if (!usernumber.value.trim() || !userpwd.value.trim()) {
      errorText.value = '账号和密码均为必填'
      return
    }
    try {
      const res = await fetch('/api/user/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: usernumber.value, userpwd: userpwd.value }),
      })
      const data = await res.json()
      if (data.success) {
        window.location.href = '/chat'
      } else if (data.code === 1002) {
        errorText.value = '账号或密码错误'
        userpwd.value = ''
      } else {
        errorText.value = '登录失败，请稍后再试'
      }
    } catch (error) {
      errorText.value = '登录失败: ' + error.message
    }
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
  transition: all 0.5s;
}

.header-inner {
  padding: 1rem 2rem;
  display: flex;
  align-items: center;
}

.logo-link {
  display: inline-flex;
  align-items: center;
  text-decoration: none;
}

.header-logo {
  height: 2.5rem;
  width: auto;
}

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

/* Card */
.register-card {
  width: 100%;
  max-width: 420px;
  background: rgba(255, 255, 255, 0.8);
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

/* Form */
.register-form {
  display: flex;
  flex-direction: column;
  gap: 0.875rem;
}

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
}

.input-field::placeholder {
  color: rgba(15, 15, 15, 0.3);
}

.input-field:focus {
  border-color: #1eb48c;
  box-shadow: 0 0 0 3px rgba(30, 180, 140, 0.1);
}

.error-text {
  color: #e55a5a;
  font-size: 0.85rem;
  min-height: 1.2rem;
  display: block;
}

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

.submit-btn:hover {
  background: #22c99d;
  box-shadow: 0 8px 28px rgba(30, 180, 140, 0.3);
  transform: translateY(-2px);
}

.submit-btn svg {
  transition: transform 0.3s ease;
}

.submit-btn:hover svg {
  transform: translateX(3px);
}

/* Toggle */
.toggle-text {
  margin-top: 1.5rem;
  text-align: center;
  font-size: 0.9rem;
  color: rgba(15, 15, 15, 0.4);
}

.toggle-link {
  color: #1eb48c;
  text-decoration: none;
  cursor: pointer;
  font-weight: 500;
  transition: color 0.3s ease;
}

.toggle-link:hover {
  color: #22c99d;
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

.bg-ring {
  position: absolute;
  border-radius: 50%;
  border: 1px solid rgba(30, 180, 140, 0.05);
}

.bg-ring-1 {
  width: 800px;
  height: 800px;
}

.bg-ring-2 {
  width: 500px;
  height: 500px;
  border-color: rgba(30, 180, 140, 0.07);
}

@media (max-width: 480px) {
  .register-card {
    padding: 2rem 1.5rem;
    border-radius: 1rem;
  }

  .register-title {
    font-size: 1.5rem;
  }
}
</style>

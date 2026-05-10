<template>
  <div class="container__form container--signin">
    <form class="form" @submit.prevent="denglu">
      <h2 class="form__title">登陆</h2>
      <input class="input-field" type="text" v-model="usernumber" placeholder="输入账号" />
      <input class="input-field" type="password" v-model="userpwd" placeholder="输入密码" />
      <p id="error-login">{{ errorText }}</p>
      <button class="btn" type="submit">登陆</button>
    </form>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
const router = useRouter()

const usernumber = ref('')
const userpwd = ref('')
const errorText = ref('')

const denglu = async () => {
  const res = await fetch('api/user/login', {
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
  }
}
</script>
<style scoped>
@import '@/assets/css/init.css';
</style>
<template>
  <div class="container__form container--signup">
    <form class="form" @submit.prevent="zhuce">
      <h2 class="form__title">个性化设置 (建议)</h2>
      <input class="input-field" type="text" v-model="username" placeholder="输入昵称" />
      <input class="input-field" type="text" v-model="usernumber" placeholder="输入账号" />
      <input class="input-field" type="password" v-model="userpwd" placeholder="输入密码" />
      <span id="errortext">{{ errorText }}</span>
      <button class="btn" type="submit">添加并登陆</button>
    </form>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()

const username = ref('')
const usernumber = ref('')
const userpwd = ref('')
const errorText = ref('')

const zhuce = async () => {
  console.log('user_id', usernumber.value)
  const res = await fetch('/api/user/register', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username: username.value, user_id: usernumber.value, userpwd: userpwd.value }),
  })
  const data = await res.json()
  if (data.success) {
    // router.push('/chat')
    window.location.href = '/chat'
  } else if (data.code === 1001) {
    errorText.value = '账号重复啦，换一个吧！'
    usernumber.value = ''
  } else {
    errorText.value = '注册失败，请稍后再试'
  }
}
</script>
<style scoped>
@import '@/assets/css/init.css';
</style>
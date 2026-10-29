// 桌面端路由：没有官网首页，从登录页开始。
// 页面组件全部复用 web/src/views；web 里有些地方会 router.push('/') 表示「回到入口」，
// 这里按登录状态转到聊天页或登录页。
import { createRouter, createWebHistory } from 'vue-router'
import Register from '@/views/Register.vue'
import Chat from '@/views/Chat.vue'
import { getState } from './desktopApi.js'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      // 已登录进聊天，没登录进登录页（产品文档里的 logo 也是 router-link 到 /）
      beforeEnter: async () => {
        try {
          return (await getState()).cloud.logged_in ? '/chat' : '/register'
        } catch {
          return '/register'
        }
      },
      component: Register,
    },
    { path: '/register', name: 'Register', component: Register },
    { path: '/login', redirect: '/register' },
    { path: '/chat', name: 'Chat', component: Chat },
    { path: '/:pathMatch(.*)*', redirect: '/register' },
  ],
})

export default router

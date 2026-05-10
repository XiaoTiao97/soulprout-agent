import { createRouter, createWebHistory } from 'vue-router'
import Init from '@/views/Init.vue'
import Register from '@/views/Register.vue'
import Login from '@/components/Login.vue'
import Chat from '@/views/Chat.vue'
import ProductDocs from '@/views/ProductDocs.vue'

const routes = [
  {
    path: '/',
    name: 'Init',
    component: Init,
    children: [
      {
        path: 'login',
        name: 'Login',
        component: Login
      }
    ]
  },
  {
    path: '/register',
    name: 'Register',
    component: Register
  },
  {
    path: '/chat',
    name: 'Chat',
    component: Chat
  },
  {
    path: '/docs',
    name: 'ProductDocs',
    component: ProductDocs
    // 产品文档无需 token 验证，所有人可访问
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

export default router

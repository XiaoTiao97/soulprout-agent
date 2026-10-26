import { createRouter, createWebHistory } from 'vue-router'
import Init from '@/views/Init.vue'
import Register from '@/views/Register.vue'
import Chat from '@/views/Chat.vue'
import ProductDocs from '@/views/ProductDocs.vue'
const routes = [
  { path: '/',         name: 'Init',        component: Init },
  { path: '/register', name: 'Register',    component: Register },
  { path: '/login',    redirect: '/register' },
  { path: '/chat',     name: 'Chat',        component: Chat },
  { path: '/docs',     name: 'ProductDocs', component: ProductDocs },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router

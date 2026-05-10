import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'path'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'), // ⬅️ 这行必须有
    },
  },
  server: {
    proxy: {
      // Agent 主服务（含 /tools_info、/skills_info、/skill、聊天等），不再走 6666 MCP 端口
      '/api': {
        target: 'http://localhost:8080', // 后端地址
        changeOrigin: true,
        rewrite: path => path.replace(/^\/api/, ''),
      },
      '/kb': {
        target: 'http://localhost:7777', // 后端地址
        changeOrigin: true,
        rewrite: path => path.replace(/^\/kb/, ''),
      },
    },
  },
})

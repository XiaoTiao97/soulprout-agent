import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'path'
import fs from 'fs'

// https://vite.dev/config/
// mode=mobile 只影响安卓入口，默认 dev / build 仍是原来的网站。
export default defineConfig(({ mode }) => {
  const mobile = mode === 'mobile'
  return {
    base: mobile ? './' : '/',
    plugins: [
      vue(),
      mobile && {
        name: 'mobile-index-html',
        closeBundle() {
          const from = path.resolve(__dirname, 'dist-mobile/index-mobile.html')
          const to = path.resolve(__dirname, 'dist-mobile/index.html')
          if (fs.existsSync(from)) fs.copyFileSync(from, to)
        },
      },
    ].filter(Boolean),
    resolve: {
      alias: {
        '@': path.resolve(__dirname, './src'),
      },
    },
    build: {
      // 不统计 gzip 后的体积：产物有好几 MB，逐个文件压缩一遍统计会让构建卡在
      // "modules transformed" 之后很久，而这个数字只是控制台里看看，不影响产物。
      reportCompressedSize: false,
      // 单个包超过 500kB 的警告在本项目一直存在，关掉免得刷屏。
      chunkSizeWarningLimit: 10000,
      ...(mobile && {
        outDir: 'dist-mobile',
        rollupOptions: {
          input: path.resolve(__dirname, 'index-mobile.html'),
        },
      }),
    },
    server: {
      proxy: {
        // Agent 主服务（含 /tools_info、/skills_info、/skill、聊天等），不再走 6666 MCP 端口
        '/api': {
          target: 'http://localhost:8080', // 后端地址（含 /api/kb 知识库接口）
          changeOrigin: true,
          rewrite: (requestPath) => requestPath.replace(/^\/api/, ''),
        },
      },
    },
  }
})

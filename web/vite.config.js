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
      ...(mobile && { outDir: 'dist-mobile' }),
      rollupOptions: {
        ...(mobile && {
          input: path.resolve(__dirname, 'index-mobile.html'),
        }),
        output: {
          // 把特别大的依赖拆成独立 chunk，避免「modules transformed」之后
          // 对单个近 10MB 的包做 minify 把低配服务器 CPU/内存打满卡死。
          // 只改产物文件切分，页面仍同步加载这些包，不做懒加载。
          manualChunks(id) {
            if (!id.includes('node_modules')) return
            if (id.includes('three') || id.includes('postprocessing')) return 'vendor-three'
            // office 预览库体积很大，按包拆开，避免单个 chunk 压缩时把服务器打满
            if (id.includes('@vue-office/docx') || id.includes('mammoth')) return 'vendor-docx'
            if (id.includes('@vue-office/excel')) return 'vendor-excel'
            if (id.includes('@vue-office/pdf')) return 'vendor-pdf'
            if (id.includes('@vue-office/pptx')) return 'vendor-pptx'
            if (id.includes('@toast-ui')) return 'vendor-editor'
            if (id.includes('highlight.js') || id.includes('markdown-it')) return 'vendor-markdown'
            if (id.includes('lottie-web')) return 'vendor-lottie'
            if (id.includes('pinyin-pro')) return 'vendor-pinyin'
            if (
              id.includes('/vue/') ||
              id.includes('\\vue\\') ||
              id.includes('vue-router') ||
              id.includes('vue-i18n') ||
              id.includes('@vue/')
            ) {
              return 'vendor-vue'
            }
            if (id.includes('axios')) return 'vendor-axios'
          },
        },
      },
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

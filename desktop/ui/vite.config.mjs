// 桌面端界面的构建配置。
//
// 不另外 npm install：直接借用 web/node_modules（vite、vue、插件都在那里），
// 并把 vue / vue-router / vue-i18n 固定指到同一份，避免出现两个 Vue 实例。
// 页面代码来自 web/src（别名 @），本目录只放桌面外壳。
import { createRequire } from 'node:module'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const here = path.dirname(fileURLToPath(import.meta.url))
const webDir = path.resolve(here, '../../web')
const requireFromWeb = createRequire(path.join(webDir, 'package.json'))
const vue = requireFromWeb('@vitejs/plugin-vue')
const pkgDir = (name) => path.dirname(requireFromWeb.resolve(`${name}/package.json`))

// 桌面窗口顶部多了一条自绘标题栏，页面里写死的 100vh 要扣掉它。
// 只在构建期替换 web/src 里的样式，不改 web 源码。
const TITLEBAR_HEIGHT = 36
function viewportHeightPlugin() {
  const isStyle = (id) => /\.(css|scss|less)(\?|$)/.test(id) || /\.vue\?.*type=style/.test(id)
  return {
    name: 'desktop-viewport-height',
    enforce: 'pre',
    transform(code, id) {
      if (!id.includes(`${path.sep}web${path.sep}src${path.sep}`) && !id.includes('/web/src/')) return null
      if (!/100vh/.test(code)) return null
      if (id.endsWith('.vue')) {
        // 单文件组件：只处理 <style> 块
        const next = code.replace(/(<style[\s\S]*?<\/style>)/g, (block) => block.replace(/100vh/g, 'var(--dk-vh, 100vh)'))
        return next === code ? null : { code: next, map: null }
      }
      if (isStyle(id)) return { code: code.replace(/100vh/g, 'var(--dk-vh, 100vh)'), map: null }
      return null
    },
  }
}

export default {
  root: here,
  base: '/',
  publicDir: path.resolve(webDir, 'public'),
  plugins: [vue(), viewportHeightPlugin()],
  define: { __DESKTOP__: 'true', __TITLEBAR_HEIGHT__: String(TITLEBAR_HEIGHT) },
  resolve: {
    alias: [
      { find: /^@\//, replacement: path.resolve(webDir, 'src') + '/' },
      { find: /^vue$/, replacement: pkgDir('vue') },
      { find: /^vue-router$/, replacement: pkgDir('vue-router') },
      { find: /^vue-i18n$/, replacement: pkgDir('vue-i18n') },
      { find: /^qrcode$/, replacement: path.join(pkgDir('qrcode'), 'lib/browser.js') },
    ],
    dedupe: ['vue', 'vue-router', 'vue-i18n'],
  },
  server: {
    port: 5180,
    fs: { allow: [path.resolve(here, '../..')] },
    proxy: {
      // 开发时直接连一个已经在跑的 sidecar（SOULPROUT_DESKTOP_PORT）。
      '/api': { target: `http://127.0.0.1:${process.env.SOULPROUT_DESKTOP_PORT || 8765}`, changeOrigin: true },
      '/__desktop': { target: `http://127.0.0.1:${process.env.SOULPROUT_DESKTOP_PORT || 8765}`, changeOrigin: true },
    },
  },
  build: {
    outDir: path.resolve(here, 'dist'),
    emptyOutDir: true,
    reportCompressedSize: false,
    chunkSizeWarningLimit: 10000,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) return
          if (id.includes('three') || id.includes('postprocessing')) return 'vendor-three'
          if (id.includes('@vue-office/docx') || id.includes('mammoth')) return 'vendor-docx'
          if (id.includes('@vue-office/excel')) return 'vendor-excel'
          if (id.includes('@vue-office/pdf')) return 'vendor-pdf'
          if (id.includes('@vue-office/pptx')) return 'vendor-pptx'
          if (id.includes('@toast-ui')) return 'vendor-editor'
          if (id.includes('highlight.js') || id.includes('markdown-it')) return 'vendor-markdown'
          if (id.includes('lottie-web')) return 'vendor-lottie'
          if (id.includes('pinyin-pro')) return 'vendor-pinyin'
          if (id.includes('/vue/') || id.includes('\\vue\\') || id.includes('vue-router') || id.includes('vue-i18n') || id.includes('@vue/')) return 'vendor-vue'
          if (id.includes('axios')) return 'vendor-axios'
        },
      },
    },
  },
}

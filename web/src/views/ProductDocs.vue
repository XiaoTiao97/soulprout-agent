<template>
  <div class="product-docs">
    <header class="docs-header">
      <div class="header-content">
        <router-link to="/" class="logo-link">
          <img :src="logo" alt="Soulprout" width="40" height="36" />
          <span class="logo-text">Soulprout</span>
        </router-link>
        <h1 class="docs-title">产品文档</h1>
      </div>
    </header>

    <div class="docs-layout">
      <aside class="docs-toc">
        <nav class="toc-nav">
          <div
            v-for="(part, partIndex) in toc"
            :key="partIndex"
            class="toc-part"
          >
            <div
              class="toc-part-title"
              :class="{ active: activePart === partIndex }"
              @click="scrollToPart(partIndex)"
            >
              {{ part.title }}
            </div>
            <div class="toc-sections">
              <div
                v-for="(section, sectionIndex) in part.sections"
                :key="sectionIndex"
                class="toc-section"
                :class="{ active: activeSection === `${partIndex}-${sectionIndex}` }"
                @click="scrollToSection(partIndex, sectionIndex)"
              >
                {{ section.title }}
              </div>
            </div>
          </div>
        </nav>
      </aside>

      <main class="docs-content">
        <article
          v-for="(part, partIndex) in docParts"
          :key="partIndex"
          :ref="el => setPartRef(el, partIndex)"
          class="doc-part"
        >
          <div class="doc-part-content p-content-markdown" v-html="part.html"></div>
        </article>
      </main>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import MarkdownIt from 'markdown-it'
import hljs from 'highlight.js'
import 'highlight.js/styles/github.css'
import logo from '@/assets/images/soulprout_logo.png'

import part1Raw from '@/utils/docs/第一部分_认识Soulprout.md?raw'
import part2Raw from '@/utils/docs/第二部分_快速上手.md?raw'
import part3Raw from '@/utils/docs/第三部分_四大功能库详解.md?raw'
import part4Raw from '@/utils/docs/第四部分_专家模式实战.md?raw'
import part5Raw from '@/utils/docs/第五部分_Soul模式.md?raw'
import part6Raw from '@/utils/docs/第六部分_开源与私有化部署.md?raw'

// 文档图片：用 import 方式加载，打包进 assets，确保生产环境一定能访问到
const docImageModules = import.meta.glob('@/assets/docs-images/*.png', { eager: true, as: 'url' })
const docImageMap = {}
for (const path in docImageModules) {
  const filename = path.split('/').pop()
  docImageMap[filename] = docImageModules[path]
}

const md = new MarkdownIt({
  html: true,
  breaks: true,
  linkify: true,
  typographer: true,
  highlight: (str, lang) => {
    if (lang && hljs.getLanguage(lang)) {
      try {
        return hljs.highlight(str, { language: lang }).value
      } catch (_) {}
    }
    return ''
  }
})

md.renderer.rules.fence = (tokens, idx, options, env, slf) => {
  const token = tokens[idx]
  const lang = token.info.trim() || 'text'
  const code = token.content
  let highlighted = ''
  if (lang && hljs.getLanguage(lang)) {
    try {
      highlighted = hljs.highlight(code, { language: lang }).value
    } catch (_) {}
  }
  if (!highlighted) highlighted = md.utils.escapeHtml(code)
  return `<pre class="hljs"><code>${highlighted}</code></pre>`
}

const renderMarkdown = (content) => {
  let html = md.render(content)
  html = html.replace(/<a /g, '<a target="_blank" rel="noopener noreferrer" ')
  // 用构建时导入的图片 URL 替换，确保本地和生产环境都能正确加载
  html = html.replace(/src="\/docs-images\/([^"]+)"/g, (_, filename) => {
    const url = docImageMap[filename]
    return url ? `src="${url}"` : `src="/docs-images/${filename}"`
  })
  return html
}

function extractToc(markdown) {
  if (!markdown || typeof markdown !== 'string') {
    return { title: '(未加载)', sections: [] }
  }
  const lines = markdown.split('\n')
  const result = { title: '', sections: [] }
  for (const line of lines) {
    const trimmed = line.trim()
    const h1Match = trimmed.match(/^#\s+(.+)$/)
    const h2Match = trimmed.match(/^##\s+(.+)$/)
    if (h1Match && !h2Match) result.title = h1Match[1].trim()
    if (h2Match) result.sections.push({ title: h2Match[1].trim(), raw: line })
  }
  return result
}

const rawDocs = [part1Raw, part2Raw, part3Raw, part4Raw, part5Raw, part6Raw]

const toc = computed(() =>
  rawDocs.map((raw) => extractToc(raw))
)

const docParts = computed(() =>
  rawDocs.map((raw) => ({ html: renderMarkdown(raw || '') }))
)

const partRefs = ref({})
const setPartRef = (el, index) => {
  if (el) partRefs.value[index] = el
}

const activePart = ref(0)
const activeSection = ref('0-0')

const HEADER_OFFSET = 80

const scrollToPart = (partIndex) => {
  const el = partRefs.value[partIndex]
  if (el) {
    const node = Array.isArray(el) ? el[0] : el
    if (node) {
      const y = node.getBoundingClientRect().top + window.scrollY - HEADER_OFFSET
      window.scrollTo({ top: y, behavior: 'smooth' })
    }
  }
  activePart.value = partIndex
  activeSection.value = `${partIndex}-0`
}

const scrollToSection = (partIndex, sectionIndex) => {
  const partEl = partRefs.value[partIndex]
  if (!partEl) return
  const node = Array.isArray(partEl) ? partEl[0] : partEl
  const h2 = node?.querySelectorAll('h2')[sectionIndex]
  if (h2) {
    const y = h2.getBoundingClientRect().top + window.scrollY - HEADER_OFFSET
    window.scrollTo({ top: y, behavior: 'smooth' })
  }
  activePart.value = partIndex
  activeSection.value = `${partIndex}-${sectionIndex}`
}

const updateActiveOnScroll = () => {
  const scrollTop = window.scrollY + 120
  for (let p = 0; p < docParts.value.length; p++) {
    const el = partRefs.value[p]
    if (!el) continue
    const node = Array.isArray(el) ? el[0] : el
    if (!node) continue
    const rect = node.getBoundingClientRect()
    const top = rect.top + window.scrollY
    const height = rect.height
    if (scrollTop >= top && scrollTop < top + height) {
      activePart.value = p
      const h2s = node.querySelectorAll('h2')
      for (let s = 0; s < h2s.length; s++) {
        const h2Rect = h2s[s].getBoundingClientRect()
        const h2Top = h2Rect.top + window.scrollY
        if (scrollTop < h2Top + 80) {
          activeSection.value = `${p}-${s}`
          break
        }
        activeSection.value = `${p}-${h2s.length - 1}`
      }
      break
    }
  }
}

onMounted(() => {
  window.addEventListener('scroll', updateActiveOnScroll, { passive: true })
})
onUnmounted(() => {
  window.removeEventListener('scroll', updateActiveOnScroll)
})
</script>

<style scoped>
.product-docs {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', sans-serif;
  min-height: 100vh;
  background: #f8fafc;
}

.docs-header {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  background: rgba(255, 255, 255, 0.95);
  backdrop-filter: blur(10px);
  border-bottom: 1px solid rgba(0, 0, 0, 0.05);
  z-index: 100;
}

.header-content {
  max-width: 1400px;
  margin: 0 auto;
  padding: 1rem 2rem;
  display: flex;
  align-items: center;
  gap: 2rem;
}

.logo-link {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  text-decoration: none;
  color: #1e293b;
  font-weight: 700;
  font-size: 1.25rem;
}

.logo-link:hover {
  color: #10b981;
}

.docs-title {
  font-size: 1.25rem;
  font-weight: 600;
  color: #64748b;
  margin: 0;
}

.docs-layout {
  display: flex;
  max-width: 1400px;
  margin: 0 auto;
  padding: 6rem 2rem 2rem;
  gap: 2rem;
}

.docs-toc {
  width: 240px;
  flex-shrink: 0;
  position: sticky;
  top: 90px;
  max-height: calc(100vh - 110px);
  overflow-y: auto;
  padding-right: 8px;
}

.docs-toc::-webkit-scrollbar {
  width: 6px;
}

.docs-toc::-webkit-scrollbar-thumb {
  background: #cbd5e1;
  border-radius: 3px;
}

.toc-nav {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.toc-part {
  border-radius: 8px;
}

.toc-part-title {
  padding: 0.5rem 0.75rem;
  font-weight: 600;
  font-size: 0.95rem;
  color: #1e293b;
  cursor: pointer;
  transition: background 0.2s, color 0.2s;
}

.toc-part-title:hover {
  background: #f1f5f9;
  color: #10b981;
}

.toc-part-title.active {
  background: #ecfdf5;
  color: #10b981;
}

.toc-sections {
  padding-left: 0.75rem;
  border-left: 2px solid #e2e8f0;
  margin-left: 0.75rem;
  margin-bottom: 0.25rem;
}

.toc-section {
  padding: 0.35rem 0.5rem;
  font-size: 0.85rem;
  color: #64748b;
  cursor: pointer;
  transition: color 0.2s, background 0.2s;
  border-radius: 4px;
  margin-bottom: 1px;
}

.toc-section:hover {
  color: #10b981;
  background: #f8fafc;
}

.toc-section.active {
  color: #10b981;
  font-weight: 500;
  background: #ecfdf5;
}

.docs-content {
  flex: 1;
  min-width: 0;
}

.doc-part {
  background: white;
  border-radius: 12px;
  padding: 2rem 3rem;
  margin-bottom: 2rem;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
  border: 1px solid rgba(0, 0, 0, 0.05);
  scroll-margin-top: 80px;
}

.doc-part-content {
  max-width: 720px;
  margin: 0 auto;
}

.doc-part-content :deep(h1) {
  font-size: 2rem;
  color: #1e293b;
  margin-bottom: 1.5rem;
  padding-bottom: 0.5rem;
  border-bottom: 2px solid #10b981;
}

.doc-part-content :deep(h2) {
  font-size: 1.35rem;
  color: #1e293b;
  margin-top: 2rem;
  margin-bottom: 1rem;
  scroll-margin-top: 80px;
}

.doc-part-content :deep(h3) {
  font-size: 1.1rem;
  color: #475569;
  margin-top: 1.5rem;
  margin-bottom: 0.75rem;
}

.doc-part-content :deep(p) {
  color: #475569;
  line-height: 1.8;
  margin-bottom: 1rem;
}

.doc-part-content :deep(ul),
.doc-part-content :deep(ol) {
  margin: 1rem 0;
  padding-left: 1.5rem;
}

.doc-part-content :deep(li) {
  margin: 0.4rem 0;
  line-height: 1.6;
  color: #475569;
}

.doc-part-content :deep(blockquote) {
  border-left: 4px solid #10b981;
  background: #f8fafc;
  padding: 1rem 1.5rem;
  margin: 1rem 0;
  color: #64748b;
  border-radius: 0 8px 8px 0;
}

.doc-part-content :deep(table) {
  width: 100%;
  border-collapse: collapse;
  margin: 1rem 0;
}

.doc-part-content :deep(th),
.doc-part-content :deep(td) {
  border: 1px solid #e2e8f0;
  padding: 0.6rem 1rem;
  text-align: left;
}

.doc-part-content :deep(th) {
  background: #f8fafc;
  font-weight: 600;
  color: #1e293b;
}

.doc-part-content :deep(tr:hover td) {
  background: #f8fafc;
}

.doc-part-content :deep(pre) {
  background: #1e293b;
  color: #e2e8f0;
  padding: 1rem;
  border-radius: 8px;
  overflow-x: auto;
  margin: 1rem 0;
}

.doc-part-content :deep(code) {
  font-family: Consolas, Monaco, monospace;
  font-size: 0.9em;
}

.doc-part-content :deep(pre code) {
  background: none;
  padding: 0;
  border: none;
  color: inherit;
}

.doc-part-content :deep(hr) {
  border: none;
  border-top: 1px solid #e2e8f0;
  margin: 2rem 0;
}

.doc-part-content :deep(img) {
  max-width: 100%;
  max-height: 400px;
  height: auto;
  object-fit: contain;
  border-radius: 8px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
}

.doc-part-content :deep(a) {
  color: #10b981;
  text-decoration: none;
}

.doc-part-content :deep(a:hover) {
  text-decoration: underline;
}

@media (max-width: 768px) {
  .docs-toc {
    display: none;
  }

  .docs-layout {
    padding: 5rem 1rem 1rem;
  }

  .doc-part {
    padding: 1.5rem 1.5rem;
  }
}
</style>

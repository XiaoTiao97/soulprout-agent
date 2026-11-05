const DocIconUrl = new URL('@/assets/images/doc_update.svg', import.meta.url).href
const ExcelIconUrl = new URL('@/assets/images/excel_update.svg', import.meta.url).href
const PptIconUrl = new URL('@/assets/images/ppt_update.svg', import.meta.url).href
const PdfIconUrl = new URL('@/assets/images/pdf_update.svg', import.meta.url).href
const FileIconUrl = new URL('@/assets/images/file_update.svg', import.meta.url).href

const IMAGE_EXTENSIONS = new Set(['png', 'jpg', 'jpeg', 'gif', 'webp', 'svg', 'bmp', 'ico', 'avif'])
const VIDEO_EXTENSIONS = new Set(['mp4', 'mov', 'webm'])

export function isUserTextMessageType(type?: string): boolean {
  return !type || type === 'text'
}

function extensionFromName(fileName: string): string {
  const name = (fileName || '').split('?')[0].split('#')[0]
  const idx = name.lastIndexOf('.')
  return idx >= 0 ? name.slice(idx + 1).toLowerCase() : ''
}

export function isImageFileName(fileName: string): boolean {
  return IMAGE_EXTENSIONS.has(extensionFromName(fileName))
}

export function isVideoFileName(fileName: string): boolean {
  return VIDEO_EXTENSIONS.has(extensionFromName(fileName))
}

/**
 * 清理工作区相对路径：
 * - 去掉开头的 `./`、`/`、`workspace/`、`/workspace/`
 * - 统一正斜杠
 */
export function normalizeWorkspaceFilePath(rawPath: string): string {
  let clean = (rawPath || '').trim()
  try {
    clean = decodeURIComponent(clean)
  } catch {
    // keep raw if malformed percent encoding
  }
  clean = clean.replace(/\\/g, '/')
  clean = clean.replace(/^(\.\/)+/, '')
  clean = clean.replace(/^\/+/, '')
  if (clean.startsWith('workspace/')) {
    clean = clean.slice('workspace/'.length)
  }
  clean = clean.replace(/^(\.\/)+/, '').replace(/^\/+/, '')
  return clean
}

/**
 * 判断 Markdown 图片 src 是否为工作区内的相对路径文件
 */
export function isWorkspaceRelativeUrl(src: string): boolean {
  const s = (src || '').trim()
  if (!s) return false
  if (/^(https?:|data:|blob:|mailto:|tel:|\/\/)/i.test(s)) return false
  if (s.startsWith('/api/') || s.startsWith('/static/') || s.startsWith('/assets/')) return false
  return true
}

/**
 * 构建工作区文件的后端访问 URL（/api/file_content/{path}?conversation_id=...）
 */
export function buildWorkspaceFileContentUrl(filePath: string, conversationId?: string | null): string {
  const cid = (conversationId || '').trim()
  const clean = normalizeWorkspaceFilePath(filePath)
  if (!clean || !cid) return filePath
  const encodedPath = clean
    .split('/')
    .filter(Boolean)
    .map((seg) => encodeURIComponent(seg))
    .join('/')
  return `/api/file_content/${encodedPath}?conversation_id=${encodeURIComponent(cid)}`
}

/**
 * 预处理 Markdown 文本中的裸图片链接、反引号包裹的图片链接与普通图片超链接：
 * - 跳过多行代码块（```...```）和已有的 ![...](...)
 * - 将反引号包裹的纯图片 URL（`http://...jpg`）或尖括号包裹的图片 URL（<http://...jpg>）转为 ![图片](http://...jpg)
 * - 将指向图片后缀（png/jpg/jpeg/gif/webp/svg/bmp/avif）的普通链接 [text](http://...jpg) 转为 ![text](http://...jpg)
 * - 将正文中的裸图片 URL（如 图：http://.../xxx.jpg）自动转为 ![图片](http://.../xxx.jpg)
 */
const MD_IMAGE_PREPROCESS_RE =
  /(```[\s\S]*?```|~~~[\s\S]*?~~~)|(!\[[^\]]*\]\([^)]*\))|`\s*(https?:\/\/[^`\s]+?\.(?:png|jpe?g|gif|webp|svg|bmp|avif|mp4|mov|webm)(?:\?[^`\s]*)?)\s*`|<((?:https?:\/\/)[^>\s]+?\.(?:png|jpe?g|gif|webp|svg|bmp|avif|mp4|mov|webm)(?:\?[^>\s]*)?)>|(`[^`\n]+`)|(<[a-zA-Z][^>]*>)|\[([^\]]*)\]\(([^)\s]+?\.(?:png|jpe?g|gif|webp|svg|bmp|avif|mp4|mov|webm)(?:\?[^)\s#]*)?(?:#[^)\s]*)?)\)|(https?:\/\/[^\s<>`)"'\]】）]+?\.(?:png|jpe?g|gif|webp|svg|bmp|avif|mp4|mov|webm)(?:\?[^\s<>`)"'\]】）]*)?)/gi

export function preprocessMarkdownImages(markdown: string): string {
  if (!markdown) return ''
  return markdown.replace(
    MD_IMAGE_PREPROCESS_RE,
    (
      match,
      fencedCode,
      mdImage,
      backtickImgUrl,
      angleImgUrl,
      inlineCode,
      htmlTag,
      linkText,
      linkImgUrl,
      bareImgUrl,
    ) => {
      if (fencedCode || mdImage || inlineCode || htmlTag) {
        return match
      }
      if (backtickImgUrl) {
        const label = isVideoFileName(backtickImgUrl) ? '视频' : '图片'
        return `![${label}](${backtickImgUrl})`
      }
      if (angleImgUrl) {
        const label = isVideoFileName(angleImgUrl) ? '视频' : '图片'
        return `![${label}](${angleImgUrl})`
      }
      if (linkImgUrl) {
        const defaultLabel = isVideoFileName(linkImgUrl) ? '视频' : '图片'
        const alt = (linkText || '').trim() || defaultLabel
        return `![${alt}](${linkImgUrl})`
      }
      if (bareImgUrl) {
        const label = isVideoFileName(bareImgUrl) ? '视频' : '图片'
        return `![${label}](${bareImgUrl})`
      }
      return match
    },
  )
}

export function getFileIconUrlForName(fileName: string): string {
  const ext = extensionFromName(fileName)
  if (['doc', 'docx'].includes(ext)) return DocIconUrl
  if (['xls', 'xlsx', 'csv'].includes(ext)) return ExcelIconUrl
  if (['ppt', 'pptx'].includes(ext)) return PptIconUrl
  if (['pdf'].includes(ext)) return PdfIconUrl
  return FileIconUrl
}

/** 从 table.file_names 解析用户上传文件名（历史接口为 table，流式为 json_table 写入 table） */
export function parseUserFileNames(message: { table?: Record<string, unknown> }): string[] {
  const names = message.table?.file_names
  if (!Array.isArray(names)) return []
  return names.map((n) => String(n))
}


const DocIconUrl = new URL('@/assets/images/doc_update.svg', import.meta.url).href
const ExcelIconUrl = new URL('@/assets/images/excel_update.svg', import.meta.url).href
const PptIconUrl = new URL('@/assets/images/ppt_update.svg', import.meta.url).href
const PdfIconUrl = new URL('@/assets/images/pdf_update.svg', import.meta.url).href
const FileIconUrl = new URL('@/assets/images/file_update.svg', import.meta.url).href

export function isUserTextMessageType(type?: string): boolean {
  return !type || type === 'text'
}

function extensionFromName(fileName: string): string {
  const name = fileName || ''
  const idx = name.lastIndexOf('.')
  return idx >= 0 ? name.slice(idx + 1).toLowerCase() : ''
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

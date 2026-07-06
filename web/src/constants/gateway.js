/** GitHub Releases latest 固定资产名，发新版后 URL 无需变更 */
export const GATEWAY_DOWNLOAD_URL =
  import.meta.env.VITE_GATEWAY_DOWNLOAD_URL ||
  'https://github.com/XiaoTiao97/soulprout-agent/releases/latest/download/Soulprout-Gateway-setup.exe'

export const GATEWAY_DOWNLOAD_FILENAME = 'Soulprout-Gateway-setup.exe'

/** GitHub Release 禁止 iframe 嵌入，需用 a 标签触发下载 */
export function downloadGatewayClient() {
  const link = document.createElement('a')
  link.href = GATEWAY_DOWNLOAD_URL
  link.download = GATEWAY_DOWNLOAD_FILENAME
  link.rel = 'noopener noreferrer'
  link.target = '_blank'
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
}

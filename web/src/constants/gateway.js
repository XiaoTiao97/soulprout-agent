/** 阿里云 OSS 固定资产名，发新版后覆盖同名文件即可，URL 无需变更 */
export const GATEWAY_DOWNLOAD_URL =
  import.meta.env.VITE_GATEWAY_DOWNLOAD_URL ||
  'https://soulprout-gateway-app.oss-cn-hongkong.aliyuncs.com/Soulprout-Gateway-setup.exe'

export const GATEWAY_DOWNLOAD_FILENAME = 'Soulprout-Gateway-setup.exe'

/** 需用 a 标签触发下载 */
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

/** GitHub Releases latest 固定资产名，发新版后 URL 无需变更 */
export const GATEWAY_DOWNLOAD_URL =
  import.meta.env.VITE_GATEWAY_DOWNLOAD_URL ||
  'https://github.com/XiaoTiao97/soulprout-agent/releases/latest/download/Soulprout-Gateway-setup.exe'

export const GATEWAY_DOWNLOAD_FILENAME = 'Soulprout-Gateway-setup.exe'

/** 通过隐藏 iframe 触发下载，避免跳转页面 */
export function downloadGatewayClient() {
  const iframe = document.createElement('iframe')
  iframe.style.display = 'none'
  iframe.src = GATEWAY_DOWNLOAD_URL
  document.body.appendChild(iframe)
  window.setTimeout(() => {
    iframe.remove()
  }, 120000)
}

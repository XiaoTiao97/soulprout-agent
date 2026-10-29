/** 阿里云 OSS 固定资产名，发新版后覆盖同名文件即可，URL 无需变更 */

export const DESKTOP_DOWNLOAD_URL =
  import.meta.env.VITE_DESKTOP_DOWNLOAD_URL ||
  import.meta.env.VITE_GATEWAY_DOWNLOAD_URL ||
  'https://oss.soulprout.com/desktop/Soulprout-setup.exe'

export const DESKTOP_DOWNLOAD_FILENAME = 'Soulprout-setup.exe'

/** @deprecated 旧名，指向现在的桌面端安装包 */
export const GATEWAY_DOWNLOAD_URL = DESKTOP_DOWNLOAD_URL
export const GATEWAY_DOWNLOAD_FILENAME = DESKTOP_DOWNLOAD_FILENAME

/** APK 直接下载（官网落地页 / 强制更新清单里的固定名） */
export const ANDROID_APK_URL =
  import.meta.env.VITE_ANDROID_APK_URL ||
  'https://oss.soulprout.com/android/Soulprout.apk'

export const ANDROID_APK_FILENAME = 'Soulprout.apk'

/**
 * 扫码落地页。手机扫码后打开该页：微信内提示用浏览器打开，浏览器内自动开始下 APK。
 * 默认走生产域名，避免扫到 localhost。
 */
export const ANDROID_LANDING_URL =
  import.meta.env.VITE_ANDROID_LANDING_URL ||
  'https://www.soulprout.com/android-download.html'

/** 需用 a 标签触发下载 */
export function downloadDesktopClient() {
  triggerDownload(DESKTOP_DOWNLOAD_URL, DESKTOP_DOWNLOAD_FILENAME)
}

/** @deprecated 旧名 */
export function downloadGatewayClient() {
  downloadDesktopClient()
}

export function downloadAndroidApk() {
  triggerDownload(ANDROID_APK_URL, ANDROID_APK_FILENAME)
}

function triggerDownload(href, filename) {
  const link = document.createElement('a')
  link.href = href
  link.download = filename
  link.rel = 'noopener noreferrer'
  link.target = '_blank'
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
}

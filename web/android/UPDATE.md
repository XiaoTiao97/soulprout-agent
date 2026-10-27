# Android 强制更新与发版

与 Gateway 同一套思路：安装包与版本清单放在阿里云 OSS，客户端启动后拉取清单，发现更高 `versionCode` 则**强制更新**（不可取消）。

## OSS 布局

Bucket 与 Gateway 相同：`soulprout`（杭州 `cn-hangzhou`，可用环境变量覆盖）。

| 对象 | 缓存 | 用途 |
|------|------|------|
| `android/Soulprout.apk` | `no-cache` | 官网扫码落地页 /「直接下载」固定链接 |
| `android/updates/<version>/Soulprout-<version>.apk` | 一年 | 强制更新下载（内容不变） |
| `android/updates/version.json` | `no-cache, no-store` | 版本清单，每次覆盖，**最后上传** |

清单示例：

```json
{
  "version": "1.0.1",
  "versionCode": 2,
  "notes": "修复待命唤醒稳定性",
  "url": "https://oss.soulprout.com/android/updates/1.0.1/Soulprout-1.0.1.apk"
}
```

- 客户端比较的是 **`versionCode`（整数）**，不是 semver 字符串。
- `build.gradle` 里的 `versionCode` / `versionName` 必须与清单一致。
- 清单地址硬编码在 `ForceUpdateChecker.java` 的 `MANIFEST_URL`。

## 发版步骤

1. 递增 `web/android/app/build.gradle` 的 `versionCode` 与 `versionName`。
2. 打 release APK（Android Studio 或 Gradle）。
3. 上传三个对象（可用 `scripts/publish-update.ps1`）：
   - 覆盖 `android/Soulprout.apk`
   - 上传带版本号的副本
   - 覆盖 `version.json`（禁缓存，最后传）

上传完成后，所有已安装且能联网的旧版 App 下次启动都会弹出「需要更新」，只能点「立即更新」。

## 官网

- 左下角菜单 / 首页互联区 →「桌面端 / 移动端下载」弹窗。
- 二维码指向 `https://www.soulprout.com/android-download.html`（仓库内 `web/public/android-download.html`）。
- 微信内提示「在浏览器中打开」；系统浏览器打开后自动跳转下载 `android/Soulprout.apk`。

部署前端时请带上 `android-download.html`。

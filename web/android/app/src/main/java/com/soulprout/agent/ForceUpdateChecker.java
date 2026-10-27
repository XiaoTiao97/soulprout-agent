package com.soulprout.agent;

import android.app.Activity;
import android.app.AlertDialog;
import android.app.ProgressDialog;
import android.content.Intent;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.os.Build;
import android.os.Handler;
import android.os.Looper;
import android.provider.Settings;
import android.util.Log;
import android.widget.Toast;

import androidx.core.content.FileProvider;

import org.json.JSONObject;

import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicBoolean;

import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.Response;
import okhttp3.ResponseBody;

/**
 * 强制更新：启动后拉取 OSS 上的 version.json，若远程 versionCode 更高则阻断使用，
 * 仅提供「立即更新」→ 下载 APK → 调起系统安装器。
 *
 * 清单地址与发版约定一致，发新版时覆盖上传即可。
 */
public final class ForceUpdateChecker {
    private static final String TAG = "ForceUpdate";

    /** 版本清单；请求时附时间戳绕过 CDN 缓存 */
    private static final String MANIFEST_URL =
            "https://oss.soulprout.com/android/updates/version.json";

    private static final OkHttpClient HTTP = new OkHttpClient.Builder()
            .followRedirects(true)
            .followSslRedirects(true)
            .build();

    private static final ExecutorService IO = Executors.newSingleThreadExecutor();
    private static final Handler MAIN = new Handler(Looper.getMainLooper());
    private static final AtomicBoolean CHECKING = new AtomicBoolean(false);

    private static AlertDialog forceDialog;
    private static String pendingApkUrl;
    private static String pendingNotes;
    private static String pendingVersion;
    private static boolean waitingInstallPermission;
    private static boolean updateRequired;
    private static boolean downloading;

    private ForceUpdateChecker() {}

    public static void check(Activity activity) {
        if (activity == null || activity.isFinishing()) return;
        if (!CHECKING.compareAndSet(false, true)) return;

        IO.execute(() -> {
            try {
                RemoteVersion remote = fetchManifest();
                if (remote == null || remote.versionCode <= 0) {
                    Log.i(TAG, "manifest missing or invalid");
                    return;
                }
                int local = localVersionCode(activity);
                if (remote.versionCode <= local) {
                    Log.i(TAG, "up to date local=" + local + " remote=" + remote.versionCode);
                    return;
                }
                Log.i(TAG, "force update required local=" + local + " remote=" + remote.versionCode);
                pendingApkUrl = remote.url;
                pendingNotes = remote.notes;
                pendingVersion = remote.version;
                updateRequired = true;
                MAIN.post(() -> showForceDialog(activity, remote));
            } catch (Exception e) {
                // 检查失败不阻断（断网时仍可先用）；有清单且版本落后才强制
                Log.w(TAG, "check failed: " + e.getMessage());
            } finally {
                CHECKING.set(false);
            }
        });
    }

    /**
     * 从「允许安装未知应用」设置页返回后继续下载；
     * 若用户取消了系统安装器，回到前台时再次弹出强制更新。
     */
    public static void onResume(Activity activity) {
        if (activity == null || !updateRequired || pendingApkUrl == null) return;
        if (downloading) return;

        if (waitingInstallPermission) {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O
                    && !activity.getPackageManager().canRequestPackageInstalls()) {
                return;
            }
            waitingInstallPermission = false;
            startDownload(activity, pendingApkUrl,
                    pendingVersion != null ? pendingVersion : "update");
            return;
        }

        if (forceDialog != null && forceDialog.isShowing()) return;

        RemoteVersion again = new RemoteVersion();
        again.version = pendingVersion != null ? pendingVersion : "";
        again.notes = pendingNotes != null ? pendingNotes : "";
        again.url = pendingApkUrl;
        again.versionCode = Integer.MAX_VALUE;
        showForceDialog(activity, again);
    }

    private static RemoteVersion fetchManifest() throws Exception {
        long nonce = System.currentTimeMillis() / 1000L;
        Request req = new Request.Builder()
                .url(MANIFEST_URL + "?t=" + nonce)
                .get()
                .header("Cache-Control", "no-cache")
                .build();
        try (Response resp = HTTP.newCall(req).execute()) {
            if (!resp.isSuccessful() || resp.body() == null) {
                throw new IllegalStateException("HTTP " + resp.code());
            }
            String body = resp.body().string();
            JSONObject json = new JSONObject(body);
            RemoteVersion v = new RemoteVersion();
            v.version = json.optString("version", "");
            v.versionCode = json.optInt("versionCode", 0);
            v.notes = json.optString("notes", "");
            v.url = json.optString("url", "");
            if (v.url.trim().isEmpty()) {
                throw new IllegalStateException("manifest url empty");
            }
            return v;
        }
    }

    private static int localVersionCode(Activity activity) {
        try {
            PackageManager pm = activity.getPackageManager();
            PackageInfo info;
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                info = pm.getPackageInfo(activity.getPackageName(), PackageManager.PackageInfoFlags.of(0));
            } else {
                info = pm.getPackageInfo(activity.getPackageName(), 0);
            }
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
                return (int) info.getLongVersionCode();
            }
            return info.versionCode;
        } catch (Exception e) {
            Log.w(TAG, "read local version failed", e);
            return 0;
        }
    }

    private static void showForceDialog(Activity activity, RemoteVersion remote) {
        if (activity.isFinishing()) return;
        dismissForceDialog();

        String notes = remote.notes == null ? "" : remote.notes.trim();
        String detail = notes.isEmpty()
                ? ("发现新版本 " + remote.version + "，需更新后才能继续使用。")
                : ("发现新版本 " + remote.version + "\n\n" + notes);

        AlertDialog dialog = new AlertDialog.Builder(activity)
                .setTitle("需要更新")
                .setMessage(detail)
                .setCancelable(false)
                .setPositiveButton("立即更新", null)
                .create();

        dialog.setOnShowListener(d -> dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(v -> {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O
                    && !activity.getPackageManager().canRequestPackageInstalls()) {
                waitingInstallPermission = true;
                try {
                    Intent intent = new Intent(
                            Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
                            Uri.parse("package:" + activity.getPackageName()));
                    activity.startActivity(intent);
                    Toast.makeText(activity, "请允许安装未知应用后返回", Toast.LENGTH_LONG).show();
                } catch (Exception e) {
                    Toast.makeText(activity, "无法打开安装权限设置", Toast.LENGTH_SHORT).show();
                }
                return;
            }
            startDownload(activity, remote.url, remote.version);
        }));

        forceDialog = dialog;
        dialog.show();
    }

    private static void dismissForceDialog() {
        AlertDialog d = forceDialog;
        forceDialog = null;
        if (d != null) {
            try {
                d.dismiss();
            } catch (Exception ignored) {}
        }
    }

    @SuppressWarnings("deprecation")
    private static void startDownload(Activity activity, String url, String version) {
        if (activity.isFinishing() || downloading) return;
        dismissForceDialog();
        downloading = true;

        ProgressDialog progress = new ProgressDialog(activity);
        progress.setTitle("正在下载更新");
        progress.setMessage("请稍候…");
        progress.setProgressStyle(ProgressDialog.STYLE_HORIZONTAL);
        progress.setMax(100);
        progress.setCancelable(false);
        progress.setCanceledOnTouchOutside(false);
        progress.show();

        IO.execute(() -> {
            File apkFile = null;
            try {
                apkFile = downloadApk(activity, url, version, (read, total) -> MAIN.post(() -> {
                    if (total > 0) {
                        progress.setIndeterminate(false);
                        progress.setProgress((int) Math.min(100, read * 100 / total));
                    } else {
                        progress.setIndeterminate(true);
                    }
                }));
                File finalFile = apkFile;
                MAIN.post(() -> {
                    downloading = false;
                    try {
                        progress.dismiss();
                    } catch (Exception ignored) {}
                    installApk(activity, finalFile);
                });
            } catch (Exception e) {
                Log.e(TAG, "download failed", e);
                if (apkFile != null) {
                    //noinspection ResultOfMethodCallIgnored
                    apkFile.delete();
                }
                MAIN.post(() -> {
                    downloading = false;
                    try {
                        progress.dismiss();
                    } catch (Exception ignored) {}
                    Toast.makeText(activity, "下载失败：" + e.getMessage(), Toast.LENGTH_LONG).show();
                    RemoteVersion again = new RemoteVersion();
                    again.version = version;
                    again.notes = pendingNotes != null ? pendingNotes : "";
                    again.url = url;
                    again.versionCode = Integer.MAX_VALUE;
                    showForceDialog(activity, again);
                });
            }
        });
    }

    private interface ProgressCallback {
        void onProgress(long read, long total);
    }

    private static File downloadApk(Activity activity, String url, String version, ProgressCallback cb)
            throws Exception {
        Request req = new Request.Builder().url(url).get().build();
        try (Response resp = HTTP.newCall(req).execute()) {
            if (!resp.isSuccessful() || resp.body() == null) {
                throw new IllegalStateException("HTTP " + resp.code());
            }
            ResponseBody body = resp.body();
            long total = body.contentLength();
            File dir = new File(activity.getCacheDir(), "updates");
            if (!dir.exists() && !dir.mkdirs()) {
                throw new IllegalStateException("无法创建下载目录");
            }
            String safeVer = version == null ? "update" : version.replaceAll("[^0-9A-Za-z._-]", "_");
            File out = new File(dir, "Soulprout-" + safeVer + ".apk");
            try (InputStream in = body.byteStream();
                 FileOutputStream fos = new FileOutputStream(out)) {
                byte[] buf = new byte[8192];
                long read = 0;
                int n;
                while ((n = in.read(buf)) != -1) {
                    fos.write(buf, 0, n);
                    read += n;
                    if (cb != null) cb.onProgress(read, total);
                }
                fos.flush();
            }
            return out;
        }
    }

    private static void installApk(Activity activity, File apk) {
        if (activity.isFinishing() || apk == null || !apk.exists()) return;
        try {
            Uri uri = FileProvider.getUriForFile(
                    activity,
                    activity.getPackageName() + ".fileprovider",
                    apk);
            Intent intent = new Intent(Intent.ACTION_VIEW);
            intent.setDataAndType(uri, "application/vnd.android.package-archive");
            intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            activity.startActivity(intent);
        } catch (Exception e) {
            Log.e(TAG, "install launch failed", e);
            Toast.makeText(activity, "无法打开安装程序：" + e.getMessage(), Toast.LENGTH_LONG).show();
        }
    }

    private static final class RemoteVersion {
        String version;
        int versionCode;
        String notes;
        String url;
    }
}

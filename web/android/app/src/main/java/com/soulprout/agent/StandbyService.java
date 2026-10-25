package com.soulprout.agent;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.content.pm.ServiceInfo;
import android.net.wifi.WifiManager;
import android.os.Build;
import android.os.IBinder;
import android.os.PowerManager;
import android.util.Log;

/**
 * 待命（Standby）常驻前台服务。
 *
 * 它本身不录音：录音与唤醒仍由 {@link WakeWordPlugin} 的线程完成。这个服务的作用是
 *   1. 以「麦克风类型前台服务」的身份让进程在切后台 / 息屏后仍有权使用麦克风；
 *   2. 常驻通知，告诉用户并让系统知道这是用户可感知的长期任务，降低被杀概率；
 *   3. 持有 CPU 唤醒锁（PARTIAL_WAKE_LOCK）和 Wi-Fi 锁，息屏后识别 / 合成的网络连接不休眠。
 *
 * 注意：Android 14+ 要求麦克风前台服务必须在 App 处于前台、且已授予录音权限时启动，
 * 所以只能由用户在界面里点击「开始待命」触发，不能在后台自启。
 */
public class StandbyService extends Service {
    private static final String TAG = "StandbyService";

    public static final String ACTION_START = "com.soulprout.agent.standby.START";
    public static final String ACTION_STOP = "com.soulprout.agent.standby.STOP";
    public static final String EXTRA_TITLE = "title";
    public static final String EXTRA_TEXT = "text";
    public static final String EXTRA_STOP_LABEL = "stopLabel";

    private static final String CHANNEL_ID = "standby";
    private static final int NOTIFICATION_ID = 7101;

    /** 服务被通知栏「停止」按钮或系统停止时回调，由插件设置，用来联动停止录音引擎 */
    public interface StopListener {
        void onServiceStopped();
    }

    private static volatile boolean running = false;
    private static volatile StopListener stopListener;

    private PowerManager.WakeLock wakeLock;
    private WifiManager.WifiLock wifiLock;

    public static boolean isRunning() {
        return running;
    }

    public static void setStopListener(StopListener l) {
        stopListener = l;
    }

    /** 启动前台服务；失败时抛异常由调用方转成错误提示 */
    public static void start(Context ctx, String title, String text, String stopLabel) {
        Intent i = new Intent(ctx, StandbyService.class);
        i.setAction(ACTION_START);
        i.putExtra(EXTRA_TITLE, title);
        i.putExtra(EXTRA_TEXT, text);
        i.putExtra(EXTRA_STOP_LABEL, stopLabel);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            ctx.startForegroundService(i);
        } else {
            ctx.startService(i);
        }
    }

    public static void stop(Context ctx) {
        ctx.stopService(new Intent(ctx, StandbyService.class));
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        if (intent != null && ACTION_STOP.equals(intent.getAction())) {
            notifyStopped();
            stopSelf();
            return START_NOT_STICKY;
        }

        String title = intent != null ? intent.getStringExtra(EXTRA_TITLE) : null;
        String text = intent != null ? intent.getStringExtra(EXTRA_TEXT) : null;
        String stopLabel = intent != null ? intent.getStringExtra(EXTRA_STOP_LABEL) : null;

        try {
            Notification n = buildNotification(
                title != null ? title : "待命中",
                text != null ? text : "说出唤醒词即可唤醒",
                stopLabel != null ? stopLabel : "停止待命");
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                startForeground(NOTIFICATION_ID, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE);
            } else {
                startForeground(NOTIFICATION_ID, n);
            }
        } catch (Throwable e) {
            // 典型原因：未授予录音权限、或在后台启动麦克风前台服务（Android 14+）
            Log.e(TAG, "startForeground failed", e);
            stopSelf();
            return START_NOT_STICKY;
        }

        acquireLocks();
        running = true;
        // 进程被杀后不要自动拉起：没有界面和录音引擎，拉起来只会留一个空通知
        return START_NOT_STICKY;
    }

    @Override
    public void onTaskRemoved(Intent rootIntent) {
        // 用户从最近任务划掉 App：WebView 与录音引擎都会随之失效，服务不应继续挂着
        notifyStopped();
        stopSelf();
        super.onTaskRemoved(rootIntent);
    }

    @Override
    public void onDestroy() {
        running = false;
        releaseLocks();
        super.onDestroy();
    }

    private void notifyStopped() {
        StopListener l = stopListener;
        if (l != null) {
            try {
                l.onServiceStopped();
            } catch (Throwable e) {
                Log.w(TAG, "stop listener failed", e);
            }
        }
    }

    private Notification buildNotification(String title, String text, String stopLabel) {
        NotificationManager nm = (NotificationManager) getSystemService(Context.NOTIFICATION_SERVICE);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O && nm != null) {
            NotificationChannel ch = new NotificationChannel(CHANNEL_ID, "Standby", NotificationManager.IMPORTANCE_LOW);
            ch.setShowBadge(false);
            nm.createNotificationChannel(ch);
        }

        int piFlags = PendingIntent.FLAG_UPDATE_CURRENT
            | (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M ? PendingIntent.FLAG_IMMUTABLE : 0);

        Intent open = new Intent(this, MainActivity.class);
        open.setFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        PendingIntent openPi = PendingIntent.getActivity(this, 0, open, piFlags);

        Intent stop = new Intent(this, StandbyService.class);
        stop.setAction(ACTION_STOP);
        PendingIntent stopPi = PendingIntent.getService(this, 1, stop, piFlags);

        Notification.Builder b = Build.VERSION.SDK_INT >= Build.VERSION_CODES.O
            ? new Notification.Builder(this, CHANNEL_ID)
            : new Notification.Builder(this);
        b.setSmallIcon(android.R.drawable.ic_btn_speak_now)
            .setContentTitle(title)
            .setContentText(text)
            .setContentIntent(openPi)
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .addAction(new Notification.Action.Builder(null, stopLabel, stopPi).build());
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            b.setForegroundServiceBehavior(Notification.FOREGROUND_SERVICE_IMMEDIATE);
        }
        return b.build();
    }

    @SuppressWarnings("deprecation")
    private void acquireLocks() {
        try {
            if (wakeLock == null) {
                PowerManager pm = (PowerManager) getSystemService(Context.POWER_SERVICE);
                wakeLock = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "soulprout:standby");
                wakeLock.setReferenceCounted(false);
            }
            if (!wakeLock.isHeld()) wakeLock.acquire();

            if (wifiLock == null) {
                WifiManager wm = (WifiManager) getApplicationContext().getSystemService(Context.WIFI_SERVICE);
                if (wm != null) {
                    int mode = Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q
                        ? WifiManager.WIFI_MODE_FULL_LOW_LATENCY
                        : WifiManager.WIFI_MODE_FULL_HIGH_PERF;
                    wifiLock = wm.createWifiLock(mode, "soulprout:standby");
                    wifiLock.setReferenceCounted(false);
                }
            }
            if (wifiLock != null && !wifiLock.isHeld()) wifiLock.acquire();
        } catch (Throwable e) {
            Log.w(TAG, "acquireLocks failed", e);
        }
    }

    private void releaseLocks() {
        try {
            if (wakeLock != null && wakeLock.isHeld()) wakeLock.release();
            if (wifiLock != null && wifiLock.isHeld()) wifiLock.release();
        } catch (Throwable e) {
            Log.w(TAG, "releaseLocks failed", e);
        }
    }
}

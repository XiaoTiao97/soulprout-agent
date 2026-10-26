package com.soulprout.agent;

import android.Manifest;
import android.content.ActivityNotFoundException;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.net.Uri;
import android.os.Build;
import android.os.PowerManager;
import android.provider.Settings;
import android.util.Log;
import android.webkit.WebView;

import androidx.core.app.NotificationManagerCompat;

import com.getcapacitor.JSObject;
import com.getcapacitor.PermissionState;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginHandle;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import com.getcapacitor.annotation.Permission;
import com.getcapacitor.annotation.PermissionCallback;

import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

/**
 * 待命（Standby）常驻支持：前台服务启停、权限 / 保活状态查询、跳转各系统设置页。
 *
 * JS 事件：
 *   serviceStopped {}   通知栏「停止待命」或用户划掉 App 导致服务停止
 */
@CapacitorPlugin(
    name = "Standby",
    permissions = {
        @Permission(strings = { Manifest.permission.RECORD_AUDIO }, alias = "microphone"),
        @Permission(strings = { Manifest.permission.POST_NOTIFICATIONS }, alias = "notifications"),
        @Permission(strings = { Manifest.permission.BLUETOOTH_CONNECT }, alias = "bluetooth")
    }
)
public class StandbyPlugin extends Plugin {
    private static final String TAG = "StandbyPlugin";

    @Override
    public void load() {
        StandbyService.setStopListener(() -> {
            // 通知栏「停止」：连带停掉录音引擎，再通知界面复位
            PluginHandle h = getBridge().getPlugin("WakeWord");
            if (h != null && h.getInstance() instanceof WakeWordPlugin) {
                ((WakeWordPlugin) h.getInstance()).stopEngine();
            }
            notifyListeners("serviceStopped", new JSObject());
        });
    }

    @Override
    protected void handleOnDestroy() {
        StandbyService.setStopListener(null);
    }

    // ------------------------------------------------------------------ 状态

    @PluginMethod
    public void getStatus(PluginCall call) {
        call.resolve(buildStatus());
    }

    private JSObject buildStatus() {
        Context ctx = getContext();
        JSObject o = new JSObject();
        o.put("sdk", Build.VERSION.SDK_INT);
        o.put("manufacturer", Build.MANUFACTURER == null ? "" : Build.MANUFACTURER.toLowerCase(Locale.ROOT));
        o.put("model", Build.MODEL);
        o.put("microphone", getPermissionState("microphone") == PermissionState.GRANTED);
        // 通知：用系统总开关判断（含「在设置里整体关闭」的情况），比单查运行时权限更准
        o.put("notifications", NotificationManagerCompat.from(ctx).areNotificationsEnabled());
        o.put("bluetooth", Build.VERSION.SDK_INT < Build.VERSION_CODES.S
            || getPermissionState("bluetooth") == PermissionState.GRANTED);
        boolean unrestricted = true;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            PowerManager pm = (PowerManager) ctx.getSystemService(Context.POWER_SERVICE);
            unrestricted = pm != null && pm.isIgnoringBatteryOptimizations(ctx.getPackageName());
        }
        o.put("batteryUnrestricted", unrestricted);
        o.put("serviceRunning", StandbyService.isRunning());
        return o;
    }

    // ------------------------------------------------------------------ 权限请求

    /** 依次补齐录音 / 通知 / 蓝牙权限，返回最新状态（用户拒绝不算失败，由界面根据状态提示） */
    @PluginMethod
    public void requestPermissions(PluginCall call) {
        step1Microphone(call);
    }

    private void step1Microphone(PluginCall call) {
        if (getPermissionState("microphone") != PermissionState.GRANTED) {
            requestPermissionForAlias("microphone", call, "onMicDone");
            return;
        }
        step2Notifications(call);
    }

    @PermissionCallback
    private void onMicDone(PluginCall call) {
        step2Notifications(call);
    }

    private void step2Notifications(PluginCall call) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU
            && getPermissionState("notifications") != PermissionState.GRANTED) {
            requestPermissionForAlias("notifications", call, "onNotifDone");
            return;
        }
        step3Bluetooth(call);
    }

    @PermissionCallback
    private void onNotifDone(PluginCall call) {
        step3Bluetooth(call);
    }

    private void step3Bluetooth(PluginCall call) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S
            && getPermissionState("bluetooth") != PermissionState.GRANTED) {
            requestPermissionForAlias("bluetooth", call, "onBluetoothDone");
            return;
        }
        call.resolve(buildStatus());
    }

    @PermissionCallback
    private void onBluetoothDone(PluginCall call) {
        call.resolve(buildStatus());
    }

    // ------------------------------------------------------------------ 前台服务

    @PluginMethod
    public void startService(PluginCall call) {
        if (getPermissionState("microphone") != PermissionState.GRANTED) {
            call.reject("还没有麦克风权限，请先授权", "PERMISSION_DENIED");
            return;
        }
        String title = call.getString("title", "待命中");
        String text = call.getString("text", "说出唤醒词即可唤醒");
        String stopLabel = call.getString("stopLabel", "停止待命");
        try {
            StandbyService.start(getContext(), title, text, stopLabel);
            keepRendererImportant();
            call.resolve();
        } catch (Throwable e) {
            Log.e(TAG, "startService failed", e);
            call.reject("启动常驻服务失败: " + e.getMessage(), "SERVICE_START_FAILED");
        }
    }

    /**
     * 待命的整条语音链路（识别 / 合成连接、Agent 流、状态机）都跑在 WebView 的渲染进程里。
     * 前台服务只保住了 App 主进程；息屏后 Activity 不可见，系统会把 WebView 渲染进程当成
     * 「看不见的后台进程」降权（CPU 受限、内存紧张时最先被杀），表现就是聊一会儿之后事件越来越慢直至停摆。
     * 这里声明：该渲染进程在不可见时也保持重要优先级，不被降权。
     */
    private void keepRendererImportant() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O || getActivity() == null) return;
        getActivity().runOnUiThread(() -> {
            try {
                getBridge().getWebView().setRendererPriorityPolicy(WebView.RENDERER_PRIORITY_IMPORTANT, false);
            } catch (Throwable e) {
                Log.w(TAG, "setRendererPriorityPolicy failed", e);
            }
        });
    }

    @PluginMethod
    public void stopService(PluginCall call) {
        StandbyService.stop(getContext());
        call.resolve();
    }

    // ------------------------------------------------------------------ 设置页跳转

    /**
     * target:
     *   app          应用详情页（权限、通知、电池入口都能从这里进）
     *   notification 本 App 的通知设置
     *   battery      电池优化白名单（优先弹系统确认框）
     *   autostart    厂商的「自启动 / 后台运行」管理页，找不到就退回应用详情页
     * 返回 { opened: 实际打开的页面, fallback: 是否退回了应用详情页 }
     */
    @PluginMethod
    public void openSettings(PluginCall call) {
        String target = call.getString("target", "app");
        String opened;
        boolean fallback = false;
        switch (target) {
            case "notification":
                opened = openNotificationSettings() ? "notification" : openAppDetails();
                fallback = !"notification".equals(opened);
                break;
            case "battery":
                opened = openBatterySettings();
                fallback = "app".equals(opened);
                break;
            case "batteryList":
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M
                    && startSafely(new Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS))) {
                    opened = "battery-list";
                } else {
                    opened = openAppDetails();
                    fallback = true;
                }
                break;
            case "autostart":
                opened = openAutoStart();
                fallback = "app".equals(opened);
                break;
            default:
                opened = openAppDetails();
        }
        JSObject o = new JSObject();
        o.put("opened", opened);
        o.put("fallback", fallback);
        call.resolve(o);
    }

    private boolean startSafely(Intent i) {
        try {
            i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            getContext().startActivity(i);
            return true;
        } catch (ActivityNotFoundException | SecurityException e) {
            return false;
        } catch (Throwable e) {
            Log.w(TAG, "startActivity failed", e);
            return false;
        }
    }

    private String openAppDetails() {
        Intent i = new Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS,
            Uri.parse("package:" + getContext().getPackageName()));
        startSafely(i);
        return "app";
    }

    private boolean openNotificationSettings() {
        Intent i = new Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS);
        i.putExtra(Settings.EXTRA_APP_PACKAGE, getContext().getPackageName());
        return startSafely(i);
    }

    private String openBatterySettings() {
        String pkg = getContext().getPackageName();
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            Intent req = new Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS, Uri.parse("package:" + pkg));
            if (startSafely(req)) return "battery-request";
            if (startSafely(new Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS))) return "battery-list";
        }
        return openAppDetails();
    }

    private static ComponentName cn(String pkg, String cls) {
        return new ComponentName(pkg, cls);
    }

    /** 各厂商自启动 / 后台管理页，按品牌排序，逐个尝试；类名随系统版本会变，所以必须有兜底 */
    private List<ComponentName> autoStartCandidates() {
        String m = Build.MANUFACTURER == null ? "" : Build.MANUFACTURER.toLowerCase(Locale.ROOT);
        List<ComponentName> list = new ArrayList<>();
        if (m.contains("xiaomi") || m.contains("redmi") || m.contains("poco")) {
            list.add(cn("com.miui.securitycenter", "com.miui.permcenter.autostart.AutoStartManagementActivity"));
        } else if (m.contains("huawei")) {
            list.add(cn("com.huawei.systemmanager", "com.huawei.systemmanager.startupmgr.ui.StartupNormalAppListActivity"));
            list.add(cn("com.huawei.systemmanager", "com.huawei.systemmanager.optimize.process.ProtectActivity"));
        } else if (m.contains("honor")) {
            list.add(cn("com.hihonor.systemmanager", "com.hihonor.systemmanager.startupmgr.ui.StartupNormalAppListActivity"));
            list.add(cn("com.huawei.systemmanager", "com.huawei.systemmanager.startupmgr.ui.StartupNormalAppListActivity"));
        } else if (m.contains("oppo") || m.contains("realme")) {
            list.add(cn("com.coloros.safecenter", "com.coloros.safecenter.permission.startup.StartupAppListActivity"));
            list.add(cn("com.oppo.safe", "com.oppo.safe.permission.startup.StartupAppListActivity"));
            list.add(cn("com.coloros.safecenter", "com.coloros.safecenter.startupapp.StartupAppListActivity"));
        } else if (m.contains("oneplus")) {
            list.add(cn("com.oneplus.security", "com.oneplus.security.chainlaunch.view.ChainLaunchAppListActivity"));
        } else if (m.contains("vivo") || m.contains("iqoo")) {
            list.add(cn("com.vivo.permissionmanager", "com.vivo.permissionmanager.activity.BgStartUpManagerActivity"));
            list.add(cn("com.iqoo.secure", "com.iqoo.secure.ui.phoneoptimize.AddWhiteListActivity"));
        } else if (m.contains("samsung")) {
            list.add(cn("com.samsung.android.lool", "com.samsung.android.sm.ui.battery.BatteryActivity"));
        }
        return list;
    }

    private String openAutoStart() {
        for (ComponentName c : autoStartCandidates()) {
            Intent i = new Intent();
            i.setComponent(c);
            if (startSafely(i)) return "autostart";
        }
        return openAppDetails();
    }
}

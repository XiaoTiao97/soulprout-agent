package com.soulprout.agent;

import android.os.Bundle;

import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {
    @Override
    public void onCreate(Bundle savedInstanceState) {
        // 本地插件必须在 super.onCreate 之前注册
        registerPlugin(WakeWordPlugin.class);
        registerPlugin(StandbyPlugin.class);
        super.onCreate(savedInstanceState);
        ForceUpdateChecker.check(this);
    }

    @Override
    public void onResume() {
        super.onResume();
        // 从「安装未知应用」设置返回后继续强制更新下载
        ForceUpdateChecker.onResume(this);
    }
}

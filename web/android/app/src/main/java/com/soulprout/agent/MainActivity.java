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
    }
}

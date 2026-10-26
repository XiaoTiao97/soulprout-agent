package com.soulprout.agent;

import android.util.Log;

import org.json.JSONObject;

import java.util.ArrayDeque;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.Response;
import okhttp3.WebSocket;
import okhttp3.WebSocketListener;
import okio.ByteString;

/**
 * 待命模式下的识别通道：在原生层直接连后端 /api/voice/asr，把麦克风 PCM 送上去。
 *
 * 为什么不走 WebView：息屏 / 后台时 Chromium 会冻住或限制 WebView 的网络与定时器，
 * JS 里的 WebSocket 建不起来或发不出音频，表现就是「唤醒还有提示音，但说话没人听」。
 * 原生线程不受这个限制，前台服务 + WakeLock 下可以一直跑。
 *
 * 协议与 JS AsrClient 一致：上行二进制 PCM，下行 JSON ready / partial / final / error / end / pong。
 */
final class NativeAsrSession {
    private static final String TAG = "Yavis";

    interface Listener {
        void onReady();

        void onPartial(String text);

        void onFinal(String text);

        void onError(String message);

        void onEnd();

        void onClose();
    }

    private static final OkHttpClient CLIENT = new OkHttpClient.Builder()
        // 协议层 ping：息屏后靠它保活，并比应用层心跳更早发现死连接
        .pingInterval(15, TimeUnit.SECONDS)
        .connectTimeout(20, TimeUnit.SECONDS)
        .readTimeout(0, TimeUnit.MILLISECONDS)
        .build();

    /** ready 前最多缓存约 4 秒音频（200ms 一包），避免慢连时把用户刚说的话丢掉 */
    private static final int MAX_PENDING = 20;
    private static final int MAX_CONNECT_ATTEMPTS = 3;

    private final Listener listener;
    private final AtomicBoolean open = new AtomicBoolean(false);
    private final AtomicBoolean ready = new AtomicBoolean(false);
    private final AtomicInteger connectAttempt = new AtomicInteger(0);
    private final ArrayDeque<byte[]> pending = new ArrayDeque<>();
    private WebSocket socket;
    private String url;
    private volatile boolean intentionalClose = false;

    NativeAsrSession(Listener listener) {
        this.listener = listener;
    }

    boolean isOpen() {
        return open.get();
    }

    boolean isReady() {
        return ready.get();
    }

    void connect(String url) {
        this.url = url;
        intentionalClose = false;
        connectAttempt.set(0);
        startConnect();
    }

    private void startConnect() {
        closeSocketOnly();
        open.set(true);
        ready.set(false);
        int attempt = connectAttempt.incrementAndGet();
        Log.i(TAG, "asr connect attempt=" + attempt + " url=" + redact(url));
        Request req = new Request.Builder().url(url).build();
        socket = CLIENT.newWebSocket(req, new WebSocketListener() {
            @Override
            public void onOpen(WebSocket webSocket, Response response) {
                Log.i(TAG, "asr tcp/ws open code=" + response.code());
            }

            @Override
            public void onMessage(WebSocket webSocket, String text) {
                handleMessage(text);
            }

            @Override
            public void onClosing(WebSocket webSocket, int code, String reason) {
                Log.i(TAG, "asr closing code=" + code + " reason=" + reason);
                webSocket.close(code, reason);
            }

            @Override
            public void onClosed(WebSocket webSocket, int code, String reason) {
                Log.i(TAG, "asr closed code=" + code + " reason=" + reason);
                boolean wasOpen = open.getAndSet(false);
                ready.set(false);
                if (wasOpen && !intentionalClose) listener.onClose();
            }

            @Override
            public void onFailure(WebSocket webSocket, Throwable t, Response response) {
                String msg = t.getMessage() != null ? t.getMessage() : "识别通道连接失败";
                int http = response != null ? response.code() : -1;
                Log.w(TAG, "asr failure http=" + http + " msg=" + msg, t);
                ready.set(false);
                if (intentionalClose) {
                    open.set(false);
                    return;
                }
                if (connectAttempt.get() < MAX_CONNECT_ATTEMPTS) {
                    Log.i(TAG, "asr retry after failure (" + connectAttempt.get() + "/" + MAX_CONNECT_ATTEMPTS + ")");
                    // 短暂退避后重连；在 worker / OkHttp 线程里直接睡一下即可
                    try {
                        Thread.sleep(400L * connectAttempt.get());
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                    }
                    if (!intentionalClose) startConnect();
                    return;
                }
                open.set(false);
                listener.onError(msg);
                listener.onClose();
            }
        });
    }

    private static String redact(String u) {
        if (u == null) return "";
        return u.replaceAll("token=[^&]+", "token=***");
    }

    private void handleMessage(String text) {
        try {
            JSONObject ev = new JSONObject(text);
            String type = ev.optString("type", "");
            switch (type) {
                case "ready":
                    ready.set(true);
                    Log.i(TAG, "asr ready, flush pending=" + pending.size());
                    flushPending();
                    listener.onReady();
                    break;
                case "partial":
                    listener.onPartial(ev.optString("text", ""));
                    break;
                case "final":
                    Log.i(TAG, "asr final「" + ev.optString("text", "") + "」");
                    listener.onFinal(ev.optString("text", ""));
                    break;
                case "error":
                    Log.w(TAG, "asr server error: " + ev.optString("message", ""));
                    listener.onError(ev.optString("message", "识别服务出错"));
                    break;
                case "end":
                    Log.i(TAG, "asr end");
                    listener.onEnd();
                    break;
                case "pong":
                    break;
                default:
                    break;
            }
        } catch (Exception e) {
            Log.w(TAG, "bad asr message: " + text, e);
        }
    }

    private void flushPending() {
        WebSocket ws = socket;
        if (ws == null || !ready.get()) return;
        while (!pending.isEmpty()) {
            byte[] pcm = pending.pollFirst();
            if (pcm != null) ws.send(ByteString.of(pcm));
        }
    }

    /** 16k / 16bit / 单声道 PCM。未就绪时先入队，连上后补发，避免慢连丢掉唤醒后的话。 */
    void sendPcm(byte[] pcm) {
        if (!open.get() || pcm == null || pcm.length == 0) return;
        if (!ready.get()) {
            if (pending.size() >= MAX_PENDING) pending.pollFirst();
            pending.addLast(pcm);
            return;
        }
        WebSocket ws = socket;
        if (ws == null) return;
        ws.send(ByteString.of(pcm));
    }

    void finish() {
        WebSocket ws = socket;
        if (!open.get() || ws == null) return;
        try {
            Log.i(TAG, "asr finish");
            ws.send("{\"type\":\"finish\"}");
        } catch (Exception e) {
            Log.w(TAG, "finish failed", e);
        }
    }

    void close() {
        intentionalClose = true;
        open.set(false);
        ready.set(false);
        pending.clear();
        closeSocketOnly();
    }

    private void closeSocketOnly() {
        WebSocket ws = socket;
        socket = null;
        if (ws != null) {
            try {
                ws.close(1000, "bye");
            } catch (Exception ignored) {
            }
        }
    }
}

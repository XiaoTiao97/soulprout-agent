package com.soulprout.agent;

import android.util.Log;

import org.json.JSONObject;

import java.util.ArrayDeque;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.Response;
import okhttp3.WebSocket;
import okhttp3.WebSocketListener;
import okio.ByteString;

/** 原生双向流式合成：连后端 /api/voice/tts，不经 WebView。 */
final class NativeTtsSession {
    private static final String TAG = "Yavis";

    interface Listener {
        void onReady();

        void onAudio(byte[] pcm);

        void onSentenceStart(String text);

        void onDone();

        void onError(String message);

        void onClose();
    }

    private static final OkHttpClient CLIENT = new OkHttpClient.Builder()
        .pingInterval(15, TimeUnit.SECONDS)
        .connectTimeout(20, TimeUnit.SECONDS)
        .readTimeout(0, TimeUnit.MILLISECONDS)
        .build();

    private final Listener listener;
    private final AtomicBoolean open = new AtomicBoolean(false);
    private final AtomicBoolean ready = new AtomicBoolean(false);
    private final ArrayDeque<String> queue = new ArrayDeque<>();
    private WebSocket socket;
    private volatile boolean intentionalClose = false;
    private volatile boolean doneSeen = false;

    NativeTtsSession(Listener listener) {
        this.listener = listener;
    }

    boolean isOpen() {
        return open.get();
    }

    boolean isReady() {
        return ready.get();
    }

    boolean isDone() {
        return doneSeen;
    }

    void connect(String url) {
        intentionalClose = false;
        doneSeen = false;
        closeSocketOnly();
        open.set(true);
        ready.set(false);
        queue.clear();
        Log.i(TAG, "tts connect " + redact(url));
        Request req = new Request.Builder().url(url).build();
        socket = CLIENT.newWebSocket(req, new WebSocketListener() {
            @Override
            public void onOpen(WebSocket webSocket, Response response) {
                Log.i(TAG, "tts ws open " + response.code());
            }

            @Override
            public void onMessage(WebSocket webSocket, String text) {
                handleJson(text);
            }

            @Override
            public void onMessage(WebSocket webSocket, ByteString bytes) {
                if (!open.get()) return;
                listener.onAudio(bytes.toByteArray());
            }

            @Override
            public void onClosing(WebSocket webSocket, int code, String reason) {
                webSocket.close(code, reason);
            }

            @Override
            public void onClosed(WebSocket webSocket, int code, String reason) {
                Log.i(TAG, "tts closed " + code + " " + reason);
                boolean was = open.getAndSet(false);
                ready.set(false);
                if (was && !intentionalClose && !doneSeen) listener.onClose();
            }

            @Override
            public void onFailure(WebSocket webSocket, Throwable t, Response response) {
                String msg = t.getMessage() != null ? t.getMessage() : "合成通道连接失败";
                Log.w(TAG, "tts failure " + msg, t);
                boolean was = open.getAndSet(false);
                ready.set(false);
                if (was && !intentionalClose && !doneSeen) {
                    listener.onError(msg);
                    listener.onClose();
                }
            }
        });
    }

    private void handleJson(String text) {
        try {
            JSONObject ev = new JSONObject(text);
            String type = ev.optString("type", "");
            switch (type) {
                case "ready":
                    ready.set(true);
                    Log.i(TAG, "tts ready, flush queue=" + queue.size());
                    while (!queue.isEmpty()) {
                        String m = queue.pollFirst();
                        if (m != null && socket != null) socket.send(m);
                    }
                    listener.onReady();
                    break;
                case "sentence_start":
                    listener.onSentenceStart(ev.optString("text", ""));
                    break;
                case "done":
                    doneSeen = true;
                    listener.onDone();
                    break;
                case "canceled":
                    doneSeen = true;
                    break;
                case "error":
                    listener.onError(ev.optString("message", "合成服务出错"));
                    break;
                case "pong":
                    break;
                default:
                    break;
            }
        } catch (Exception e) {
            Log.w(TAG, "bad tts message", e);
        }
    }

    void sendText(String text) {
        if (text == null || text.trim().isEmpty() || !open.get()) return;
        String msg = "{\"type\":\"text\",\"text\":" + JSONObject.quote(text) + "}";
        if (ready.get() && socket != null) socket.send(msg);
        else queue.addLast(msg);
    }

    void finish() {
        sendRaw("{\"type\":\"finish\"}");
    }

    void cancel() {
        if (ready.get() && socket != null) {
            try {
                socket.send("{\"type\":\"cancel\"}");
            } catch (Exception ignored) {
            }
        }
        close();
    }

    private void sendRaw(String msg) {
        if (!open.get()) return;
        if (ready.get() && socket != null) socket.send(msg);
        else queue.addLast(msg);
    }

    void close() {
        intentionalClose = true;
        open.set(false);
        ready.set(false);
        queue.clear();
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

    private static String redact(String u) {
        if (u == null) return "";
        return u.replaceAll("token=[^&]+", "token=***");
    }
}

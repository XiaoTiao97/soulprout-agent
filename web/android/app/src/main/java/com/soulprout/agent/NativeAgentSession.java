package com.soulprout.agent;

import android.util.Log;

import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

import okhttp3.MultipartBody;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.RequestBody;
import okhttp3.Response;
import okhttp3.ResponseBody;

/**
 * 原生 Agent SSE：POST /api/message/chat，解析 data: 行。
 * 密钥仍在后端；这里只用用户登录 token。
 */
final class NativeAgentSession {
    private static final String TAG = "Yavis";

    interface Listener {
        void onEvent(String type);

        void onDelta(String text);

        void onTurnDone();

        void onError(String message);
    }

    private static final OkHttpClient CLIENT = new OkHttpClient.Builder()
        .connectTimeout(20, TimeUnit.SECONDS)
        .readTimeout(0, TimeUnit.MILLISECONDS)
        .writeTimeout(30, TimeUnit.SECONDS)
        .build();

    private final ExecutorService executor = Executors.newSingleThreadExecutor(r -> {
        Thread t = new Thread(r, "native-agent");
        t.setDaemon(true);
        return t;
    });

    /** 通知后端终止这一轮运行（只断开 SSE 的话，后端的 Agent 仍会在后台继续跑） */
    private static final OkHttpClient STOP_CLIENT = new OkHttpClient.Builder()
        .connectTimeout(3, TimeUnit.SECONDS)
        .readTimeout(3, TimeUnit.SECONDS)
        .callTimeout(4, TimeUnit.SECONDS)
        .build();

    private final ExecutorService stopExecutor = Executors.newSingleThreadExecutor(r -> {
        Thread t = new Thread(r, "native-agent-stop");
        t.setDaemon(true);
        return t;
    });
    private volatile Future<?> pendingStop;

    private final AtomicBoolean cancelled = new AtomicBoolean(false);
    private Future<?> running;
    private okhttp3.Call call;

    /**
     * 立即向后端发送终止信号（POST /api/message/stop）。
     * 新一轮 start() 会等这个请求结束再发，避免终止信号误伤刚提交的新一轮。
     */
    void stopRemote(String stopUrl, String token, String conversationId) {
        if (stopUrl == null || stopUrl.isEmpty() || conversationId == null || conversationId.isEmpty()) return;
        pendingStop = stopExecutor.submit(() -> {
            try {
                JSONObject payload = new JSONObject();
                payload.put("conversation_id", conversationId);
                Request.Builder rb = new Request.Builder()
                    .url(stopUrl)
                    .post(RequestBody.create(payload.toString(), okhttp3.MediaType.parse("application/json; charset=utf-8")));
                if (token != null && !token.isEmpty()) rb.header("Authorization", "Bearer " + token);
                try (Response r = STOP_CLIENT.newCall(rb.build()).execute()) {
                    Log.i(TAG, "agent stop signal http=" + r.code());
                }
            } catch (Exception e) {
                Log.w(TAG, "agent stop signal failed: " + e.getMessage());
            }
        });
    }

    private void awaitPendingStop() {
        Future<?> f = pendingStop;
        if (f == null) return;
        try {
            f.get(3, TimeUnit.SECONDS);
        } catch (Exception ignored) {
        }
    }

    void start(String chatUrl, String token, String userId, String message, Listener listener) {
        cancel();
        cancelled.set(false);
        running = executor.submit(() -> run(chatUrl, token, userId, message, listener));
    }

    void cancel() {
        cancelled.set(true);
        okhttp3.Call c = call;
        call = null;
        if (c != null) {
            try {
                c.cancel();
            } catch (Exception ignored) {
            }
        }
        Future<?> f = running;
        running = null;
        if (f != null) f.cancel(true);
    }

    void shutdown() {
        cancel();
        executor.shutdownNow();
        stopExecutor.shutdown();
    }

    private void run(String chatUrl, String token, String userId, String message, Listener listener) {
        awaitPendingStop();
        if (cancelled.get()) return;
        try {
            JSONObject payload = new JSONObject();
            payload.put("message", message);
            payload.put("conversation_id", userId);
            payload.put("agent_use", "soulprout");
            // 消息来源：手机端（待命语音），后端据此在用户消息前标注 Source: Mobile
            payload.put("client", "mobile");
            payload.put("agent_id", JSONObject.NULL);
            payload.put("agent_name", JSONObject.NULL);
            payload.put("tools_use", true);
            payload.put("skills_use", true);
            payload.put("kb_use", new org.json.JSONArray());
            payload.put("files", new org.json.JSONArray());

            // 与浏览器 FormData.append('chat_request', JSON.stringify(...)) 对齐：纯文本字段
            RequestBody body = new MultipartBody.Builder()
                .setType(MultipartBody.FORM)
                .addFormDataPart("chat_request", payload.toString())
                .build();

            Request.Builder rb = new Request.Builder()
                .url(chatUrl)
                .post(body)
                .header("Accept", "text/event-stream")
                .header("Cache-Control", "no-store");
            if (token != null && !token.isEmpty()) {
                rb.header("Authorization", "Bearer " + token);
            }

            call = CLIENT.newCall(rb.build());
            Log.i(TAG, "agent POST " + chatUrl);
            try (Response response = call.execute()) {
                if (cancelled.get()) return;
                if (!response.isSuccessful()) {
                    listener.onError("Agent 请求失败（HTTP " + response.code() + "）");
                    return;
                }
                ResponseBody rbod = response.body();
                if (rbod == null) {
                    listener.onError("Agent 没有返回数据流");
                    return;
                }
                parseSse(rbod.byteStream(), listener);
            }
        } catch (Exception e) {
            if (cancelled.get()) return;
            String msg = e.getMessage() != null ? e.getMessage() : "Agent 请求失败";
            Log.w(TAG, "agent failed", e);
            listener.onError(msg);
        }
    }

    private void parseSse(InputStream in, Listener listener) throws Exception {
        BufferedReader reader = new BufferedReader(new InputStreamReader(in, StandardCharsets.UTF_8));
        String followedTurnId = "";
        boolean turnEnded = false;
        String line;
        while (!cancelled.get() && (line = reader.readLine()) != null) {
            String trimmed = line.trim();
            if (trimmed.startsWith(":")) {
                listener.onEvent("ping");
                continue;
            }
            if (!trimmed.startsWith("data:")) continue;
            String data = trimmed.substring(5).trim();
            if (data.isEmpty()) continue;
            JSONObject chunk;
            try {
                chunk = new JSONObject(data);
            } catch (Exception e) {
                continue;
            }
            String type = chunk.optString("type", "");
            listener.onEvent(type.isEmpty() ? "data" : type);

            String turnId = chunk.optString("turn_id", "");
            if ("turn_started".equals(type) && !turnId.isEmpty()) followedTurnId = turnId;
            else if (!turnId.isEmpty() && !followedTurnId.isEmpty() && !turnId.equals(followedTurnId)) continue;
            else if (followedTurnId.isEmpty() && !turnId.isEmpty()) followedTurnId = turnId;

            if ("turn_done".equals(type) || "interrupted".equals(type) || "stopped".equals(type)) {
                turnEnded = true;
                break;
            }
            if ("error".equals(type)) {
                listener.onError(chunk.optString("content", "Agent 回复异常"));
                return;
            }
            String content = chunk.optString("content", "");
            if (content.isEmpty()) continue;
            String role = chunk.optString("role", "assistant");
            if ("user_feedback".equals(type) || ("assistant".equals(role) && "text".equals(type))) {
                listener.onDelta(content);
            }
        }
        if (turnEnded && !cancelled.get()) listener.onTurnDone();
        else if (!cancelled.get() && !turnEnded) {
            // 流结束但没有 turn_done：仍收尾，避免卡死
            Log.w(TAG, "agent stream ended without turn_done");
            listener.onTurnDone();
        }
    }
}

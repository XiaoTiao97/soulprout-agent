package com.soulprout.agent;

import android.util.Log;

import org.json.JSONObject;

import java.io.IOException;
import java.util.concurrent.TimeUnit;

import okhttp3.Call;
import okhttp3.Callback;
import okhttp3.MediaType;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.RequestBody;
import okhttp3.Response;
import okhttp3.ResponseBody;

/**
 * 语义断句判断：把 total_voice_text / current_voice_text 交给后端的轻量大模型，
 * 判断用户这轮话是真的说完了，还是中间停顿 / 思考。
 *
 * 判断失败（网络、超时、服务未配置）一律回调「说完了」，保证对话不会卡住。
 */
final class NativeTurnJudge {
    private static final String TAG = "Yavis";
    private static final MediaType JSON = MediaType.parse("application/json; charset=utf-8");

    interface Callback2 {
        /** @param finished true=说完了（含判断失败兜底），false=还没说完 */
        void onResult(boolean finished);
    }

    private static final OkHttpClient CLIENT = new OkHttpClient.Builder()
        .connectTimeout(3, TimeUnit.SECONDS)
        .readTimeout(5, TimeUnit.SECONDS)
        .callTimeout(6, TimeUnit.SECONDS)
        .build();

    private Call current;

    /** 发起一次判断；同一时刻只保留最新一次，旧的会被取消（不会回调）。 */
    synchronized void judge(String url, String token, String total, String currentText, Callback2 cb) {
        cancel();
        if (url == null || url.isEmpty()) {
            cb.onResult(true);
            return;
        }
        try {
            JSONObject body = new JSONObject();
            body.put("total_voice_text", total);
            body.put("current_voice_text", currentText);
            Request.Builder rb = new Request.Builder()
                .url(url)
                .post(RequestBody.create(body.toString(), JSON));
            if (token != null && !token.isEmpty()) rb.header("Authorization", "Bearer " + token);
            final long t0 = System.currentTimeMillis();
            final Call call = CLIENT.newCall(rb.build());
            current = call;
            call.enqueue(new Callback() {
                @Override
                public void onFailure(Call c, IOException e) {
                    if (c.isCanceled()) return;
                    Log.w(TAG, "turn judge failed: " + e.getMessage());
                    cb.onResult(true);
                }

                @Override
                public void onResponse(Call c, Response response) {
                    boolean finished = true;
                    try (Response r = response) {
                        ResponseBody rbody = r.body();
                        if (r.isSuccessful() && rbody != null) {
                            JSONObject o = new JSONObject(rbody.string());
                            // null / 缺省 = 判断失败，按说完处理
                            if (o.has("user_finished") && !o.isNull("user_finished")) {
                                finished = o.optBoolean("user_finished", true);
                            }
                        } else {
                            Log.w(TAG, "turn judge http " + r.code());
                        }
                    } catch (Exception e) {
                        if (c.isCanceled()) return;
                        Log.w(TAG, "turn judge parse failed: " + e.getMessage());
                    }
                    if (c.isCanceled()) return;
                    Log.i(TAG, "turn judge finished=" + finished + " cost=" + (System.currentTimeMillis() - t0) + "ms");
                    cb.onResult(finished);
                }
            });
        } catch (Exception e) {
            Log.w(TAG, "turn judge build failed", e);
            cb.onResult(true);
        }
    }

    synchronized void cancel() {
        Call c = current;
        current = null;
        if (c != null) {
            try {
                c.cancel();
            } catch (Exception ignored) {
            }
        }
    }
}

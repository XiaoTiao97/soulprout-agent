package com.soulprout.agent;

import android.util.Log;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * 待命对话编排（全原生，不依赖 WebView）：
 *   唤醒 → 识别 → 断句 → Agent SSE → 分句合成 → 播放 → 连续听
 *
 * 豆包 Key 仍在后端；这里只用用户 token 调自家 /api。
 */
final class StandbyOrchestrator {
    private static final String TAG = "Yavis";
    private static final int MIN_VALID_CHARS = 2;
    private static final int TTS_SAMPLE_RATE = 24000;
    private static final long TTS_IDLE_REFRESH_MS = 8_000;

    interface Host {
        void openAsr();

        void closeAsr();

        void beginCapture();

        void endCapture();

        void thinkStart();

        void thinkStop();

        void playStart(int sampleRate);

        void playWrite(byte[] pcm);

        void playFinish();

        void playStop();

        /** 把状态推给 JS 仅供界面显示（冻住也不影响对话） */
        void emitPipeline(String phase, String key, String value);
    }

    private final Host host;
    private final ExecutorService playExec = Executors.newSingleThreadExecutor(r -> {
        Thread t = new Thread(r, "standby-play");
        t.setDaemon(true);
        return t;
    });

    private volatile boolean enabled = false;
    private volatile boolean continuous = true;
    private volatile String asrUrl = "";
    private volatile String ttsUrl = "";
    private volatile String chatUrl = "";
    private volatile String token = "";
    private volatile String userId = "";

    private final AtomicInteger turnId = new AtomicInteger(0);
    private volatile String phase = "standby"; // standby|listening|thinking|speaking
    private NativeAgentSession agent;
    private NativeTtsSession tts;
    private SentenceSplitter splitter;
    private volatile boolean playStarted = false;
    private volatile boolean ttsUsed = false;
    private volatile long ttsIoAt = 0;
    private volatile boolean ttsFinishSent = false;

    StandbyOrchestrator(Host host) {
        this.host = host;
    }

    void configure(String asrUrl, String ttsUrl, String chatUrl, String token, String userId,
                   boolean continuous, String voice, int speechRate) {
        this.asrUrl = asrUrl != null ? asrUrl : "";
        // ttsUrl 已由 JS 带好 voice / speech_rate / token
        this.ttsUrl = ttsUrl != null ? ttsUrl : "";
        this.chatUrl = chatUrl != null ? chatUrl : "";
        this.token = token != null ? token : "";
        this.userId = userId != null ? userId : "";
        this.continuous = continuous;
        this.enabled = !this.asrUrl.isEmpty() && !this.ttsUrl.isEmpty() && !this.chatUrl.isEmpty();
        Log.i(TAG, "pipeline configure enabled=" + enabled + " continuous=" + continuous
            + " userId=" + this.userId);
    }

    boolean isEnabled() {
        return enabled;
    }

    String getAsrUrl() {
        return asrUrl;
    }

    void setContinuous(boolean continuous) {
        this.continuous = continuous;
        // 关掉连续对话时：若正在「免唤醒聆听」，立刻回到待命，避免未唤醒仍继续收音发消息
        if (!continuous && "listening".equals(phase)) {
            host.closeAsr();
            host.endCapture();
            setPhase("standby");
            host.emitPipeline(phase, "standby", "");
        }
    }

    void updateUrls(String asrUrl, String ttsUrl, String chatUrl, String token) {
        if (asrUrl != null && !asrUrl.isEmpty()) this.asrUrl = asrUrl;
        if (ttsUrl != null && !ttsUrl.isEmpty()) this.ttsUrl = ttsUrl;
        if (chatUrl != null && !chatUrl.isEmpty()) this.chatUrl = chatUrl;
        if (token != null) this.token = token;
        this.enabled = !this.asrUrl.isEmpty() && !this.ttsUrl.isEmpty() && !this.chatUrl.isEmpty();
    }

    /** 命中唤醒词：取消当前轮，进入聆听 */
    void onWake(String keyword) {
        if (!enabled) return;
        Log.i(TAG, "pipeline wake 「" + keyword + "」");
        cancelTurn();
        setPhase("listening");
        host.beginCapture();
        host.openAsr();
        host.emitPipeline(phase, "wake", keyword);
    }

    /** 识别 partial：思考/播报中听到人声则打断 */
    void onAsrPartial(String text) {
        if (!enabled) return;
        if ("thinking".equals(phase) || "speaking".equals(phase)) {
            if (SentenceSplitter.validChars(text) >= MIN_VALID_CHARS) {
                Log.i(TAG, "pipeline barge-in 「" + text + "」");
                cancelTurn();
                setPhase("listening");
                host.emitPipeline(phase, "bargeIn", text);
            }
            return;
        }
        if ("listening".equals(phase)) {
            host.emitPipeline(phase, "partial", text);
        }
    }

    /** 识别断句：交给 Agent */
    void onAsrFinal(String text) {
        if (!enabled) return;
        // 待命/关闭态即使有残留识别结果也不能发消息，必须先唤醒
        if (!"listening".equals(phase) && !"thinking".equals(phase) && !"speaking".equals(phase)) {
            Log.i(TAG, "pipeline ignore final in phase=" + phase + " 「" + text + "」");
            return;
        }
        if (SentenceSplitter.validChars(text) < MIN_VALID_CHARS) {
            Log.i(TAG, "pipeline ignore short 「" + text + "」");
            return;
        }
        // 思考/播报中的 final：先打断再开新一轮
        if ("thinking".equals(phase) || "speaking".equals(phase)) {
            cancelTurn();
        }
        Log.i(TAG, "pipeline final → agent 「" + text + "」");
        startAgentTurn(text);
    }

    void onPlayEnd(boolean interrupted) {
        if (!enabled) return;
        if (interrupted) return;
        if (!"speaking".equals(phase) && !playStarted) return;
        Log.i(TAG, "pipeline playEnd continuous=" + continuous);
        playStarted = false;
        host.thinkStop();
        closeTts();
        if (continuous) {
            setPhase("listening");
            host.beginCapture();
            // 识别通道在思考/播报期间保持；若已关则重开
            host.openAsr();
            host.emitPipeline(phase, "continue", "");
        } else {
            host.closeAsr();
            host.endCapture();
            setPhase("standby");
            host.emitPipeline(phase, "standby", "");
        }
    }

    void interrupt() {
        if (!enabled) return;
        cancelTurn();
        if (continuous) {
            setPhase("listening");
            host.beginCapture();
            host.openAsr();
        } else {
            host.closeAsr();
            host.endCapture();
            setPhase("standby");
        }
        host.emitPipeline(phase, "interrupt", "");
    }

    void stop() {
        enabled = false;
        cancelTurn();
        if (agent != null) {
            agent.shutdown();
            agent = null;
        }
        host.closeAsr();
        host.endCapture();
        setPhase("off");
    }

    private void startAgentTurn(String text) {
        final int myTurn = turnId.incrementAndGet();
        setPhase("thinking");
        host.thinkStart();
        host.emitPipeline(phase, "sent", text);
        playStarted = false;
        ttsUsed = false;
        ttsFinishSent = false;
        ttsIoAt = 0;

        splitter = new SentenceSplitter(sentence -> {
            if (myTurn != turnId.get()) return;
            maybeRefreshTts();
            ttsUsed = true;
            ensureTts();
            ttsIoAt = System.currentTimeMillis();
            if (tts != null) tts.sendText(sentence);
            host.emitPipeline(phase, "replyAppend", sentence);
        });

        ensureTts();

        if (agent == null) agent = new NativeAgentSession();
        agent.start(chatUrl, token, userId, text, new NativeAgentSession.Listener() {
            @Override
            public void onEvent(String type) {
                if (myTurn != turnId.get()) return;
                if (!"ping".equals(type) && !"data".equals(type)) {
                    Log.i(TAG, "pipeline agent event " + type);
                }
                host.emitPipeline(phase, "agentEvent", type);
            }

            @Override
            public void onDelta(String delta) {
                if (myTurn != turnId.get()) return;
                if (splitter != null) splitter.push(delta);
            }

            @Override
            public void onTurnDone() {
                if (myTurn != turnId.get()) return;
                Log.i(TAG, "pipeline agent turn_done ttsUsed=" + ttsUsed);
                if (splitter != null) splitter.flush();
                if (ttsUsed && tts != null) {
                    ttsFinishSent = true;
                    ttsIoAt = System.currentTimeMillis();
                    tts.finish();
                } else {
                    host.thinkStop();
                    afterSilentTurn();
                }
            }

            @Override
            public void onError(String message) {
                if (myTurn != turnId.get()) return;
                Log.w(TAG, "pipeline agent error " + message);
                host.emitPipeline(phase, "error", message);
                cancelTurn();
                if (continuous) {
                    setPhase("listening");
                    host.openAsr();
                } else {
                    setPhase("standby");
                    host.endCapture();
                    host.closeAsr();
                }
                host.emitPipeline(phase, "errorDone", message);
            }
        });
    }

    private void afterSilentTurn() {
        playStarted = false;
        closeTts();
        if (continuous) {
            setPhase("listening");
            host.beginCapture();
            host.openAsr();
            host.emitPipeline(phase, "continue", "");
        } else {
            host.closeAsr();
            host.endCapture();
            setPhase("standby");
            host.emitPipeline(phase, "standby", "");
        }
    }

    private void maybeRefreshTts() {
        if (tts != null && ttsIoAt > 0 && System.currentTimeMillis() - ttsIoAt > TTS_IDLE_REFRESH_MS) {
            Log.i(TAG, "pipeline tts idle refresh");
            closeTts();
        }
    }

    private void ensureTts() {
        if (tts != null && tts.isOpen()) return;
        final int myTurn = turnId.get();
        NativeTtsSession session = new NativeTtsSession(new NativeTtsSession.Listener() {
            @Override
            public void onReady() {
                ttsIoAt = System.currentTimeMillis();
                Log.i(TAG, "pipeline tts ready");
            }

            @Override
            public void onAudio(byte[] pcm) {
                if (myTurn != turnId.get()) return;
                ttsIoAt = System.currentTimeMillis();
                playExec.execute(() -> {
                    if (myTurn != turnId.get()) return;
                    try {
                        if (!playStarted) {
                            playStarted = true;
                            host.thinkStop();
                            host.playStart(TTS_SAMPLE_RATE);
                            setPhase("speaking");
                            host.emitPipeline(phase, "speaking", "");
                        }
                        host.playWrite(pcm);
                    } catch (Exception e) {
                        Log.w(TAG, "pipeline play write failed", e);
                    }
                });
            }

            @Override
            public void onSentenceStart(String text) {
                if (myTurn != turnId.get()) return;
                host.emitPipeline(phase, "speakingText", text);
            }

            @Override
            public void onDone() {
                if (myTurn != turnId.get()) return;
                playExec.execute(() -> {
                    if (myTurn != turnId.get()) return;
                    try {
                        if (playStarted) host.playFinish();
                        else afterSilentTurn();
                    } catch (Exception e) {
                        Log.w(TAG, "pipeline playFinish failed", e);
                        afterSilentTurn();
                    }
                });
            }

            @Override
            public void onError(String message) {
                if (myTurn != turnId.get()) return;
                Log.w(TAG, "pipeline tts error " + message);
                host.emitPipeline(phase, "error", message);
                // 尝试重建一次
                closeTts();
                if (ttsUsed && !ttsFinishSent) {
                    ensureTts();
                }
            }

            @Override
            public void onClose() {
                if (myTurn != turnId.get()) return;
                if (ttsUsed && !ttsFinishSent && tts != null && !tts.isDone()) {
                    Log.w(TAG, "pipeline tts closed early, reopen");
                    closeTts();
                    ensureTts();
                }
            }
        });
        tts = session;
        session.connect(ttsUrl);
    }

    private void cancelTurn() {
        turnId.incrementAndGet();
        if (agent != null) agent.cancel();
        if (splitter != null) splitter.reset();
        splitter = null;
        closeTts();
        host.thinkStop();
        if (playStarted) {
            playStarted = false;
            try {
                host.playStop();
            } catch (Exception ignored) {
            }
        }
        ttsUsed = false;
        ttsFinishSent = false;
    }

    private void closeTts() {
        if (tts != null) {
            tts.close();
            tts = null;
        }
    }

    private void setPhase(String p) {
        phase = p;
        Log.i(TAG, "pipeline phase=" + p);
    }

    String getPhase() {
        return phase;
    }
}

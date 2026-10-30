package com.soulprout.agent;

import android.util.Log;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * 待命对话编排（全原生，不依赖 WebView）：
 *   唤醒 → 识别 → 断句 → 语义判断 → Agent SSE → 分句合成 → 播放 → 连续听
 *
 * 语义断句：
 *   - ASR 静默 endWindowMs（默认 1300ms）只是「候选断句点」，到了之后交给后端的轻量大模型
 *     从语义层判断用户是真说完了，还是中间停顿 / 思考。
 *   - 一个「监听窗口」内用户说过的全部内容保存在 totalVoice（用于语义判断的上下文）；
 *     每次真正发给 Agent 的只有 currentVoice（尚未发送的最新内容）。
 *   - Agent 开始回复后 {@link #WINDOW_MS} 内，用户继续说话 → 立刻终止 Agent、重置窗口计时、
 *     新说的话追加进 totalVoice 并重新判断；超过这个时间 totalVoice 清空，一切从头开始。
 *
 * 豆包 Key 仍在后端；这里只用用户 token 调自家 /api。
 */
final class StandbyOrchestrator {
    private static final String TAG = "Yavis";
    private static final int MIN_VALID_CHARS = 2;
    private static final int TTS_SAMPLE_RATE = 24000;
    private static final long TTS_IDLE_REFRESH_MS = 8_000;
    /** Agent 开始回复后，totalVoice 保留多久；期间用户继续说话视为同一轮对话的延续 */
    private static final long WINDOW_MS = 5_000;
    /**
     * 语义判断为「没说完」后，如果用户一直没有再开口，最多等多久就兜底发送，
     * 避免模型误判时用户一直干等。
     */
    private static final long HOLD_FALLBACK_MS = 6_000;

    interface Host {
        void openAsr();

        /** 识别通道已打开就复用，否则新开一路（语义断句期间不能因为换通道丢掉用户的话） */
        void ensureAsr();

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

    private static final int MAX_ASR_REOPEN = 6;
    private final ScheduledExecutorService timer = Executors.newSingleThreadScheduledExecutor(r -> {
        Thread t = new Thread(r, "standby-timer");
        t.setDaemon(true);
        return t;
    });
    private final AtomicInteger asrReopenCount = new AtomicInteger(0);
    private final AtomicBoolean asrReopenPending = new AtomicBoolean(false);

    private volatile boolean enabled = false;
    private volatile boolean continuous = true;
    private volatile String asrUrl = "";
    private volatile String ttsUrl = "";
    private volatile String chatUrl = "";
    private volatile String token = "";
    private volatile String userId = "";
    private volatile String judgeUrl = "";
    private volatile String stopUrl = "";

    // ---- 语义断句：监听窗口内的语音文本 ----
    private final Object voiceLock = new Object();
    /** 窗口内用户说过的全部内容（只用于语义判断，不会整体发给 Agent） */
    private final StringBuilder totalVoice = new StringBuilder();
    /** 尚未发给 Agent 的最新内容；发送出去的永远只有它 */
    private final StringBuilder currentVoice = new StringBuilder();
    /** 每次用户有新语音 / 状态重置都递增，用来作废过期的语义判断结果与兜底计时 */
    private final AtomicInteger voiceSeq = new AtomicInteger(0);
    private final NativeTurnJudge judge = new NativeTurnJudge();
    private ScheduledFuture<?> windowTask;
    private ScheduledFuture<?> holdTask;
    /** 当前 Agent 轮是否还在运行（SSE 未结束），取消时据此决定要不要通知后端终止 */
    private volatile boolean agentRunning = false;
    private volatile int windowArmedTurn = -1;

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
                   boolean continuous, String voice, int speechRate, String judgeUrl, String stopUrl) {
        this.asrUrl = asrUrl != null ? asrUrl : "";
        this.judgeUrl = judgeUrl != null && !judgeUrl.isEmpty() ? judgeUrl : deriveUrl(chatUrl, "/message/chat", "/voice/turn-judge");
        this.stopUrl = stopUrl != null && !stopUrl.isEmpty() ? stopUrl : deriveUrl(chatUrl, "/message/chat", "/message/stop");
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

    private static String deriveUrl(String chatUrl, String from, String to) {
        if (chatUrl == null || !chatUrl.endsWith(from)) return "";
        return chatUrl.substring(0, chatUrl.length() - from.length()) + to;
    }

    boolean isEnabled() {
        return enabled;
    }

    String getAsrUrl() {
        return asrUrl;
    }

    void setContinuous(boolean continuous) {
        this.continuous = continuous;
        if (!continuous) {
            // 非连续：立刻停收音，避免思考/播报中被环境声或残留识别打断
            host.closeAsr();
            host.endCapture();
            if ("listening".equals(phase)) {
                setPhase("standby");
                host.emitPipeline(phase, "standby", "");
            }
        }
    }

    void updateUrls(String asrUrl, String ttsUrl, String chatUrl, String token) {
        if (asrUrl != null && !asrUrl.isEmpty()) this.asrUrl = asrUrl;
        if (ttsUrl != null && !ttsUrl.isEmpty()) this.ttsUrl = ttsUrl;
        if (chatUrl != null && !chatUrl.isEmpty()) this.chatUrl = chatUrl;
        if (token != null) this.token = token;
        this.enabled = !this.asrUrl.isEmpty() && !this.ttsUrl.isEmpty() && !this.chatUrl.isEmpty();
    }

    /** 命中唤醒词：随时可打断当前轮（含非连续对话的思考/播报），进入聆听 */
    void onWake(String keyword) {
        if (!enabled) return;
        Log.i(TAG, "pipeline wake 「" + keyword + "」");
        cancelTurn();
        // 唤醒词意味着新的一轮对话，之前窗口里的内容不再作为语义判断依据
        resetVoiceState();
        setPhase("listening");
        host.beginCapture();
        host.openAsr();
        host.emitPipeline(phase, "wake", keyword);
    }

    /**
     * 识别 partial：用户正在说话。
     *  - 思考 / 播报中（连续对话）：打断 Agent，保留窗口内的 totalVoice，等这段话说完后一起判断；
     *  - 聆听中：说明用户还在继续说，作废进行中的语义判断与兜底计时。
     */
    void onAsrPartial(String text) {
        if (!enabled) return;
        if ("thinking".equals(phase) || "speaking".equals(phase)) {
            if (!continuous) return;
            if (SentenceSplitter.validChars(text) >= MIN_VALID_CHARS) {
                Log.i(TAG, "pipeline barge-in 「" + text + "」");
                // 立即终止 Agent（含通知后端），并重置 5s 窗口计时：新一轮回复开始后才会重新计时
                cancelTurn();
                markUserSpeaking();
                setPhase("listening");
                host.emitPipeline(phase, "bargeIn", text);
            }
            return;
        }
        if ("listening".equals(phase)) {
            if (SentenceSplitter.validChars(text) >= 1) {
                markUserSpeaking();
                // 正常情况下马上会来 final 重新判断；万一 final 没来（杂音 partial），兜底发出，不让话悬在半空
                if (hasPendingVoice()) armHold(voiceSeq.get());
            }
            host.emitPipeline(phase, "partial", text);
        }
    }

    /**
     * 识别断句（ASR 静默 endWindowMs 之后）：先把这段话追加进 totalVoice / currentVoice，
     * 再交给大模型做语义判断；说完了才把 currentVoice 发给 Agent。
     */
    void onAsrFinal(String text) {
        if (!enabled) return;
        // 待命/关闭态即使有残留识别结果也不能发消息，必须先唤醒
        if (!"listening".equals(phase) && !"thinking".equals(phase) && !"speaking".equals(phase)) {
            Log.i(TAG, "pipeline ignore final in phase=" + phase + " 「" + text + "」");
            return;
        }
        // 非连续：思考/播报中不再接收新的断句
        if (!continuous && ("thinking".equals(phase) || "speaking".equals(phase))) {
            Log.i(TAG, "pipeline ignore final during turn (non-continuous) 「" + text + "」");
            return;
        }
        asrReopenCount.set(0);
        if (SentenceSplitter.validChars(text) < MIN_VALID_CHARS) {
            Log.i(TAG, "pipeline ignore short 「" + text + "」");
            // 噪声打断了 Agent 但没有有效内容：窗口计时需要重新走起来，否则 totalVoice 会一直留着
            rearmWindowIfIdle();
            return;
        }
        // 连续对话：没有先收到 partial 就直接来了 final，同样先打断当前轮
        if ("thinking".equals(phase) || "speaking".equals(phase)) {
            cancelTurn();
            setPhase("listening");
        }
        final int seq;
        final String total;
        final String current;
        synchronized (voiceLock) {
            cancelWindowLocked();
            cancelHoldLocked();
            appendVoice(totalVoice, text);
            appendVoice(currentVoice, text);
            seq = voiceSeq.incrementAndGet();
            total = totalVoice.toString();
            current = currentVoice.toString();
        }
        Log.i(TAG, "pipeline final 「" + text + "」 total=「" + total + "」 current=「" + current + "」 → judge");
        host.emitPipeline(phase, "partial", current);
        judge.judge(judgeUrl, token, total, current, finished -> onJudgeResult(seq, finished));
    }

    /** 语义判断结果。期间用户又开口 / 被唤醒 / 被打断（seq 变了）则结果作废，等下一次断句重新判断。 */
    private void onJudgeResult(int seq, boolean finished) {
        if (!enabled || seq != voiceSeq.get()) {
            Log.i(TAG, "pipeline judge result stale, drop");
            return;
        }
        host.emitPipeline(phase, "judge", finished ? "finished" : "unfinished");
        if (finished) {
            commitCurrent();
        } else {
            Log.i(TAG, "pipeline judge: not finished, keep listening");
            armHold(seq);
        }
    }

    /** 把 currentVoice 发给 Agent；totalVoice 原样保留，作为后续继续说话时的判断依据 */
    private void commitCurrent() {
        final String text;
        synchronized (voiceLock) {
            cancelHoldLocked();
            text = currentVoice.toString().trim();
            currentVoice.setLength(0);
        }
        if (!enabled || !"listening".equals(phase)) return;
        if (SentenceSplitter.validChars(text) < MIN_VALID_CHARS) return;
        Log.i(TAG, "pipeline commit → agent 「" + text + "」");
        startAgentTurn(text);
    }

    /** 判为「没说完」之后用户一直没再开口：兜底发送，避免误判时一直干等 */
    private void armHold(final int seq) {
        synchronized (voiceLock) {
            cancelHoldLocked();
            holdTask = timer.schedule(() -> {
                if (!enabled || seq != voiceSeq.get()) return;
                Log.i(TAG, "pipeline hold timeout, force commit");
                commitCurrent();
            }, HOLD_FALLBACK_MS, TimeUnit.MILLISECONDS);
        }
    }

    /** 用户有新语音：作废过期的判断与计时（但不清空文本） */
    private void markUserSpeaking() {
        synchronized (voiceLock) {
            voiceSeq.incrementAndGet();
            cancelWindowLocked();
            cancelHoldLocked();
        }
        judge.cancel();
    }

    /** Agent 开始回复（或本轮结束）后启动 5s 窗口计时：到点清空 totalVoice，一切回到初始状态 */
    private void armWindow(int forTurn) {
        synchronized (voiceLock) {
            if (windowArmedTurn == forTurn) return;
            cancelWindowLocked();
            windowArmedTurn = forTurn;
            windowTask = timer.schedule(() -> {
                synchronized (voiceLock) {
                    if (currentVoice.length() > 0) return; // 还有没发出去的内容，说明用户仍在这轮里
                    if (totalVoice.length() > 0) {
                        Log.i(TAG, "pipeline window expired, reset total_voice_text");
                    }
                    totalVoice.setLength(0);
                    windowTask = null;
                }
            }, WINDOW_MS, TimeUnit.MILLISECONDS);
        }
    }

    private void rearmWindowIfIdle() {
        synchronized (voiceLock) {
            if (totalVoice.length() == 0 || currentVoice.length() > 0 || agentRunning) return;
            if (windowTask != null && !windowTask.isDone()) return;
            windowArmedTurn = -1;
        }
        armWindow(turnId.get());
    }

    private void cancelWindowLocked() {
        if (windowTask != null) {
            windowTask.cancel(false);
            windowTask = null;
        }
        windowArmedTurn = -1;
    }

    private void cancelHoldLocked() {
        if (holdTask != null) {
            holdTask.cancel(false);
            holdTask = null;
        }
    }

    /** 全部清空：唤醒 / 停止 / 手动打断时调用 */
    private void resetVoiceState() {
        synchronized (voiceLock) {
            voiceSeq.incrementAndGet();
            cancelWindowLocked();
            cancelHoldLocked();
            totalVoice.setLength(0);
            currentVoice.setLength(0);
        }
        judge.cancel();
    }

    private boolean hasPendingVoice() {
        synchronized (voiceLock) {
            return currentVoice.length() > 0;
        }
    }

    private boolean hasWindowVoice() {
        synchronized (voiceLock) {
            return totalVoice.length() > 0;
        }
    }

    private static void appendVoice(StringBuilder sb, String text) {
        String t = text == null ? "" : text.trim();
        if (t.isEmpty()) return;
        if (sb.length() > 0) {
            char last = sb.charAt(sb.length() - 1);
            char first = t.charAt(0);
            // 中文直接拼接；英文 / 数字之间补空格
            if (isAsciiWord(last) && isAsciiWord(first)) sb.append(' ');
        }
        sb.append(t);
    }

    private static boolean isAsciiWord(char c) {
        return c < 128 && Character.isLetterOrDigit(c);
    }

    /**
     * 识别通道被服务端关掉（断句后 / 静默超时）。
     *  - 连续对话在思考、播报期间必须保持收音，否则说话打不断；
     *  - 语义判断「没说完」等用户继续说时，通道不能丢。
     * 稍等片刻重开，并限制次数避免网络异常时死循环。
     */
    void onAsrClosed() {
        if (!enabled) return;
        if (!shouldKeepAsr()) return;
        if (asrReopenCount.get() >= MAX_ASR_REOPEN) return;
        if (!asrReopenPending.compareAndSet(false, true)) return;
        asrReopenCount.incrementAndGet();
        final int myTurn = turnId.get();
        timer.schedule(() -> {
            asrReopenPending.set(false);
            if (!enabled || myTurn != turnId.get()) return;
            if (!shouldKeepAsr()) return;
            Log.i(TAG, "pipeline reopen asr (phase=" + phase + ")");
            host.openAsr();
        }, 600, TimeUnit.MILLISECONDS);
    }

    private boolean shouldKeepAsr() {
        if ("thinking".equals(phase) || "speaking".equals(phase)) return continuous;
        if ("listening".equals(phase)) return hasPendingVoice() || (continuous && hasWindowVoice());
        return false;
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
        resetVoiceState();
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
        resetVoiceState();
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
        asrReopenCount.set(0);
        asrReopenPending.set(false);
        agentRunning = true;
        // 新一轮发出后，5s 窗口要等 Agent 开始回复时才重新计时；totalVoice 保持不动
        synchronized (voiceLock) {
            cancelWindowLocked();
            cancelHoldLocked();
        }
        if (!continuous) {
            // 非连续：进入思考后立刻关识别/采集，避免思考与播报过程中继续收音导致打断
            // （唤醒词仍由原生唤醒引擎监听，可随时打断）
            host.closeAsr();
            host.endCapture();
        } else {
            // 连续：识别通道要在思考/播报期间保持，用户继续说话才能被听到并终止 Agent。
            // 已经开着就直接复用（不丢用户紧接着说的话），否则新开一路。
            host.beginCapture();
            host.ensureAsr();
        }
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
                // Agent 开始给出回复：从此刻起 5s 内用户继续说话，算同一轮对话的延续
                if (delta != null && !delta.isEmpty()) armWindow(myTurn);
                if (splitter != null) splitter.push(delta);
            }

            @Override
            public void onTurnDone() {
                if (myTurn != turnId.get()) return;
                agentRunning = false;
                armWindow(myTurn);
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
                agentRunning = false;
                host.emitPipeline(phase, "error", message);
                cancelTurn();
                armWindow(myTurn);
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
        if (agent != null) {
            agent.cancel();
            if (agentRunning) {
                // 只断开 SSE 后端不会停：显式发终止信号，Agent 才会真的中止这一轮运行
                Log.i(TAG, "pipeline send stop signal to agent");
                agent.stopRemote(stopUrl, token, userId);
            }
        }
        agentRunning = false;
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

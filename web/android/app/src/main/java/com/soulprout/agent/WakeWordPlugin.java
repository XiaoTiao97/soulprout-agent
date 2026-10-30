package com.soulprout.agent;

import android.Manifest;
import android.content.Context;
import android.content.res.AssetManager;
import android.media.AudioAttributes;
import android.media.AudioDeviceInfo;
import android.media.AudioFormat;
import android.media.AudioManager;
import android.media.AudioRecord;
import android.media.AudioTrack;
import android.media.MediaRecorder;
import android.media.audiofx.AcousticEchoCanceler;
import android.media.audiofx.NoiseSuppressor;
import android.os.Build;
import android.util.Log;
import android.view.WindowManager;
import android.webkit.WebView;

import com.getcapacitor.JSObject;
import com.getcapacitor.PermissionState;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import com.getcapacitor.annotation.Permission;
import com.getcapacitor.annotation.PermissionCallback;
import com.k2fsa.sherpa.onnx.FeatureConfig;
import com.k2fsa.sherpa.onnx.KeywordSpotter;
import com.k2fsa.sherpa.onnx.KeywordSpotterConfig;
import com.k2fsa.sherpa.onnx.OnlineModelConfig;
import com.k2fsa.sherpa.onnx.OnlineStream;
import com.k2fsa.sherpa.onnx.OnlineTransducerModelConfig;

import java.io.BufferedReader;
import java.io.ByteArrayOutputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * 离线唤醒词测试插件（最小版，仅前台可用）。
 *
 * 链路：AudioRecord(16k 单声道) -> sherpa-onnx 开放词表 KWS -> 命中后 "嘀" 一声 + 通知 JS。
 * 关键词由 JS 以「声母 韵母 @原词」格式传入，多个用 "/" 分隔，无需重新训练模型。
 *
 * 麦克风来源：
 *   source = "auto"（默认）：有蓝牙耳机就切到耳机麦克风，没有就用手机麦克风；
 *   source = "phone"：始终用手机自带麦克风。
 * 注意：蓝牙耳机平时只走 A2DP（只能放音乐、没有麦克风），要用耳机麦克风必须切到
 * 通话链路（SCO/HFP），此时耳机的音质会降到通话级别，这是蓝牙协议本身的限制。
 *
 * JS 事件：
 *   wake   { keyword, count, tsMs }
 *   status { running, elapsedSec, avgProcMs, loadPct, wakeCount, input, bluetooth }
 *   level  { peakDb, rmsDb, level(0-100) }   每 200ms 一次，供音量条使用
 *   error  { message }
 */
@CapacitorPlugin(
    name = "WakeWord",
    permissions = {
        @Permission(strings = { Manifest.permission.RECORD_AUDIO }, alias = "microphone"),
        // Android 12+（API 31）使用蓝牙设备需要运行时授权
        @Permission(strings = { Manifest.permission.BLUETOOTH_CONNECT }, alias = "bluetooth")
    }
)
public class WakeWordPlugin extends Plugin {
    private static final String TAG = "WakeWord";

    private static final int SAMPLE_RATE = 16000;
    /** 每次读取 100ms 音频 */
    private static final int CHUNK_SAMPLES = SAMPLE_RATE / 10;
    /** 命中后的冷却，避免同一次喊话重复触发 */
    private static final long COOLDOWN_MS = 1500;
    private static final long STATUS_INTERVAL_MS = 1000;
    private static final long LEVEL_INTERVAL_MS = 200;

    private static final String MODEL_DIR = "kws/";
    private static final String ENCODER = MODEL_DIR + "encoder-epoch-12-avg-2-chunk-16-left-64.int8.onnx";
    private static final String DECODER = MODEL_DIR + "decoder-epoch-12-avg-2-chunk-16-left-64.onnx";
    private static final String JOINER = MODEL_DIR + "joiner-epoch-12-avg-2-chunk-16-left-64.int8.onnx";
    private static final String TOKENS = MODEL_DIR + "tokens.txt";
    /** sherpa 要求创建时必须带一个非空关键词文件，实际关键词在每次 start 时通过 stream 传入 */
    private static final String DEFAULT_KEYWORDS = MODEL_DIR + "keywords.txt";

    private final Object lock = new Object();
    private KeywordSpotter spotter;
    private Set<String> validTokens;
    private Thread worker;
    private volatile boolean running = false;

    // ---- 待命（Standby）：采集 + 播报 ----
    /** 每包上送 200ms 音频（16k * 2 字节 * 0.2s） */
    private static final int CAPTURE_PACKET_BYTES = SAMPLE_RATE * 2 / 5;
    /** 播报结束后继续「捂耳朵」的时长，避开扬声器尾音 */
    private static final long POST_PLAY_MUTE_MS = 300;
    private static final int PLAY_SAMPLE_RATE_DEFAULT = 24000;

    /**
     * 采集模式：命中唤醒词或编排器 beginCapture 后置位。
     * PCM 送给原生识别通道（NativeAsrSession）。
     */
    private volatile boolean capturing = false;
    /** 由 configurePipeline 写入；唤醒后原生层自己建识别通道 */
    private volatile String asrUrl = null;
    private NativeAsrSession asrSession;
    private final Object asrLock = new Object();
    /** 全原生对话编排：Agent + TTS 不经 WebView，息屏也能跑完一轮 */
    private final StandbyOrchestrator orchestrator = new StandbyOrchestrator(new StandbyOrchestrator.Host() {
        @Override
        public void openAsr() {
            String url = orchestrator.getAsrUrl();
            if (url == null || url.isEmpty()) url = asrUrl;
            if (url != null && !url.isEmpty()) {
                asrUrl = url;
                openAsrSession(url);
            }
        }

        @Override
        public void ensureAsr() {
            NativeAsrSession s;
            synchronized (asrLock) {
                s = asrSession;
            }
            if (s != null && s.isOpen()) return;
            openAsr();
        }

        @Override
        public void closeAsr() {
            closeAsrSession();
        }

        @Override
        public void beginCapture() {
            capBuf.reset();
            capturing = true;
        }

        @Override
        public void endCapture() {
            capturing = false;
        }

        @Override
        public void thinkStart() {
            startThinkBed();
        }

        @Override
        public void thinkStop() {
            stopThinkBed();
        }

        @Override
        public void playStart(int sampleRate) {
            doPlayStart(sampleRate);
        }

        @Override
        public void playWrite(byte[] pcm) {
            doPlayWrite(pcm);
        }

        @Override
        public void playFinish() {
            doPlayFinish();
        }

        @Override
        public void playStop() {
            boolean was = playing;
            stopPlayback(true);
            if (was) emitPlayEnd(true);
        }

        @Override
        public void emitPipeline(String phase, String key, String value) {
            JSObject o = new JSObject();
            o.put("phase", phase);
            o.put("key", key);
            o.put("value", value != null ? value : "");
            // 界面更新尽力而为；冻住也不影响原生对话
            try {
                notifyListeners("pipeline", o);
            } catch (Throwable ignored) {
            }
        }
    });
    /** 正在播报：此时既不唤醒也不采集 */
    private volatile boolean playing = false;
    private volatile long muteUntilMs = 0;
    /** 从播报 / 采集切回待命时，需要先清空唤醒引擎的上下文（仅 worker 线程读写） */
    private boolean kwsDirty = false;
    private volatile boolean btMode = false;
    /**
     * 播报期间保持唤醒（语音打断）：录音源改用 VOICE_COMMUNICATION + 系统回声消除，
     * 播报时不再静音，命中唤醒词就地停掉播放。
     */
    private volatile boolean bargeIn = false;
    private AcousticEchoCanceler aec;
    private NoiseSuppressor ns;
    private final ByteArrayOutputStream capBuf = new ByteArrayOutputStream(CAPTURE_PACKET_BYTES * 2);

    private AudioTrack track;
    private int trackSampleRate = PLAY_SAMPLE_RATE_DEFAULT;
    private long trackFramesWritten = 0;
    /** 每次 playStart / playStop 递增，用来让排队中的旧任务作废 */
    private final AtomicInteger playGen = new AtomicInteger(0);
    private ExecutorService playExecutor;
    private final Object playLock = new Object();

    // 蓝牙耳机麦克风路由状态（仅 worker 线程读写）
    private int prevAudioMode = AudioManager.MODE_NORMAL;
    private boolean modeChanged = false;
    private boolean commDeviceSet = false;
    private boolean speakerphoneSet = false;
    private boolean scoStarted = false;

    // ------------------------------------------------------------------ JS API

    @PluginMethod
    public void start(PluginCall call) {
        if (getPermissionState("microphone") != PermissionState.GRANTED) {
            requestPermissionForAlias("microphone", call, "onMicPermission");
            return;
        }
        afterMicGranted(call);
    }

    @PermissionCallback
    private void onMicPermission(PluginCall call) {
        if (getPermissionState("microphone") == PermissionState.GRANTED) {
            afterMicGranted(call);
        } else {
            call.reject("麦克风权限被拒绝，请在系统设置中允许录音", "PERMISSION_DENIED");
        }
    }

    private static boolean wantsBluetooth(PluginCall call) {
        return !"phone".equals(call.getString("source", "auto"));
    }

    /** Android 12+ 要先拿到蓝牙权限才能用耳机麦克风；被拒绝就退回手机麦克风，不阻断唤醒 */
    private void afterMicGranted(PluginCall call) {
        if (wantsBluetooth(call)
            && Build.VERSION.SDK_INT >= Build.VERSION_CODES.S
            && getPermissionState("bluetooth") != PermissionState.GRANTED) {
            requestPermissionForAlias("bluetooth", call, "onBluetoothPermission");
            return;
        }
        doStart(call);
    }

    @PermissionCallback
    private void onBluetoothPermission(PluginCall call) {
        doStart(call);
    }

    @PluginMethod
    public void stop(PluginCall call) {
        try {
            orchestrator.stop();
        } catch (Throwable ignored) {
        }
        stopWorker();
        call.resolve();
    }

    @PluginMethod
    public void isRunning(PluginCall call) {
        JSObject ret = new JSObject();
        ret.put("running", running);
        call.resolve(ret);
    }

    @Override
    protected void handleOnDestroy() {
        haltThinkBed();
        stopPlayback(true);
        chimeExecutor.shutdownNow();
        synchronized (playLock) {
            if (playExecutor != null) {
                playExecutor.shutdownNow();
                playExecutor = null;
            }
        }
        stopWorker();
        synchronized (lock) {
            if (spotter != null) {
                spotter.release();
                spotter = null;
            }
        }
    }

    // ------------------------------------------------------------ 待命：采集 + 播报

    /** 供 StandbyPlugin / 通知栏「停止」联动：停掉录音与播报 */
    public void stopEngine() {
        try {
            orchestrator.stop();
        } catch (Throwable ignored) {
        }
        haltThinkBed();
        stopPlayback(true);
        stopWorker();
    }

    /**
     * 配置全原生对话管线（识别 / Agent / 合成 URL + 用户 token）。
     * 之后断句→回复→播报全部在原生完成，不依赖 WebView。
     */
    @PluginMethod
    public void configurePipeline(PluginCall call) {
        String asr = call.getString("asrUrl", "");
        String tts = call.getString("ttsUrl", "");
        String chat = call.getString("chatUrl", "");
        String token = call.getString("token", "");
        String userId = call.getString("userId", "");
        boolean continuous = Boolean.TRUE.equals(call.getBoolean("continuous", true));
        String voice = call.getString("voice", "female");
        int speechRate = call.getInt("speechRate", 0);
        String judge = call.getString("judgeUrl", "");
        String stop = call.getString("stopUrl", "");
        if (asr != null && !asr.trim().isEmpty()) asrUrl = asr.trim();
        orchestrator.configure(
            asrUrl,
            tts != null ? tts.trim() : "",
            chat != null ? chat.trim() : "",
            token != null ? token : "",
            userId != null ? userId : "",
            continuous,
            voice,
            speechRate,
            judge != null ? judge.trim() : "",
            stop != null ? stop.trim() : ""
        );
        Log.i("Yavis", "configurePipeline ok enabled=" + orchestrator.isEnabled());
        call.resolve();
    }

    @PluginMethod
    public void setPipelineContinuous(PluginCall call) {
        orchestrator.setContinuous(Boolean.TRUE.equals(call.getBoolean("continuous", true)));
        call.resolve();
    }

    @PluginMethod
    public void pipelineInterrupt(PluginCall call) {
        orchestrator.interrupt();
        call.resolve();
    }

    private void openAsrSession(String url) {
        closeAsrSession();
        NativeAsrSession session = new NativeAsrSession(new NativeAsrSession.Listener() {
            @Override
            public void onReady() {
                Log.i(TAG, "asr ready");
            }

            @Override
            public void onPartial(String text) {
                if (!orchestrator.isEnabled()) return;
                try {
                    orchestrator.onAsrPartial(text);
                } catch (Throwable e) {
                    Log.w(TAG, "orchestrator onAsrPartial", e);
                }
            }

            @Override
            public void onFinal(String text) {
                if (!orchestrator.isEnabled()) return;
                try {
                    orchestrator.onAsrFinal(text);
                } catch (Throwable e) {
                    Log.w(TAG, "orchestrator onAsrFinal", e);
                }
            }

            @Override
            public void onError(String message) {
                Log.w(TAG, "asr error " + message);
            }

            @Override
            public void onEnd() {
                notifyOrchestratorAsrClosed();
            }

            @Override
            public void onClose() {
                notifyOrchestratorAsrClosed();
            }
        });
        synchronized (asrLock) {
            asrSession = session;
        }
        session.connect(url);
        Log.i(TAG, "asr session opening");
    }

    private void notifyOrchestratorAsrClosed() {
        if (!orchestrator.isEnabled()) return;
        try {
            orchestrator.onAsrClosed();
        } catch (Throwable e) {
            Log.w(TAG, "orchestrator onAsrClosed", e);
        }
    }

    private void closeAsrSession() {
        NativeAsrSession session;
        synchronized (asrLock) {
            session = asrSession;
            asrSession = null;
        }
        if (session != null) session.close();
    }

    private void doPlayStart(int rate) {
        stopThinkBed();
        stopPlayback(false);
        int minBuf = AudioTrack.getMinBufferSize(rate, AudioFormat.CHANNEL_OUT_MONO, AudioFormat.ENCODING_PCM_16BIT);
        AudioAttributes attrs = new AudioAttributes.Builder()
            .setUsage((btMode || bargeIn) ? AudioAttributes.USAGE_VOICE_COMMUNICATION : AudioAttributes.USAGE_MEDIA)
            .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
            .build();
        AudioFormat fmt = new AudioFormat.Builder()
            .setEncoding(AudioFormat.ENCODING_PCM_16BIT)
            .setSampleRate(rate)
            .setChannelMask(AudioFormat.CHANNEL_OUT_MONO)
            .build();
        AudioTrack t = new AudioTrack(attrs, fmt, Math.max(minBuf, rate * 2),
            AudioTrack.MODE_STREAM, AudioManager.AUDIO_SESSION_ID_GENERATE);
        if (t.getState() != AudioTrack.STATE_INITIALIZED) {
            t.release();
            throw new IllegalStateException("播放器初始化失败");
        }
        synchronized (playLock) {
            track = t;
            trackSampleRate = rate;
            trackFramesWritten = 0;
            if (playExecutor == null || playExecutor.isShutdown()) {
                playExecutor = Executors.newSingleThreadExecutor();
            }
        }
        playGen.incrementAndGet();
        playing = true;
        t.play();
    }

    private void doPlayWrite(byte[] data) {
        final AudioTrack t;
        final ExecutorService ex;
        synchronized (playLock) {
            t = track;
            ex = playExecutor;
        }
        if (t == null || ex == null || data == null || data.length == 0) return;
        final int gen = playGen.get();
        ex.execute(() -> {
            if (gen != playGen.get()) return;
            try {
                int off = 0;
                while (off < data.length && gen == playGen.get()) {
                    int w = t.write(data, off, data.length - off);
                    if (w <= 0) break;
                    off += w;
                }
                synchronized (playLock) {
                    if (track == t) trackFramesWritten += off / 2;
                }
            } catch (Throwable e) {
                Log.w(TAG, "playWrite failed", e);
            }
        });
    }

    private void doPlayFinish() {
        final AudioTrack t;
        final ExecutorService ex;
        synchronized (playLock) {
            t = track;
            ex = playExecutor;
        }
        if (t == null || ex == null) {
            emitPlayEnd(false);
            return;
        }
        final int gen = playGen.get();
        ex.execute(() -> {
            long frames;
            int rate;
            synchronized (playLock) {
                frames = trackFramesWritten;
                rate = trackSampleRate;
            }
            long deadline = System.currentTimeMillis() + frames * 1000L / Math.max(1, rate) + 3000;
            try {
                while (gen == playGen.get() && System.currentTimeMillis() < deadline) {
                    if ((t.getPlaybackHeadPosition() & 0xFFFFFFFFL) >= frames) break;
                    Thread.sleep(40);
                }
            } catch (Throwable ignored) {
            }
            if (gen != playGen.get()) return;
            stopPlayback(false);
            emitPlayEnd(false);
        });
    }

    private void stopPlayback(boolean invalidate) {
        if (invalidate) playGen.incrementAndGet();
        AudioTrack t;
        synchronized (playLock) {
            t = track;
            track = null;
            trackFramesWritten = 0;
        }
        if (t != null) {
            try {
                t.pause();
                t.flush();
            } catch (Throwable ignored) {
            }
            try {
                t.release();
            } catch (Throwable ignored) {
            }
            // 语音打断模式要保证打断后立刻能收到用户的话，不能再「捂耳朵」
            if (!bargeIn) muteUntilMs = System.currentTimeMillis() + POST_PLAY_MUTE_MS;
        }
        playing = false;
    }

    private void emitPlayEnd(boolean interrupted) {
        if (orchestrator.isEnabled()) {
            try {
                orchestrator.onPlayEnd(interrupted);
            } catch (Throwable e) {
                Log.w(TAG, "orchestrator onPlayEnd", e);
            }
        }
        JSObject o = new JSObject();
        o.put("interrupted", interrupted);
        notifyJs("playEnd", o);
    }

    /**
     * 息屏后 WebView 定时器 / 事件循环会被系统挂起，notifyListeners 发出的事件会在 JS 里堆着不跑，
     * 表现就是「原生已经 asr final 了，但 Agent 完全没动静」，直到用户点亮屏幕才一次性回放。
     * 关键事件发出前先 resumeTimers，尽量把 JS 叫醒处理。
     */
    private void notifyJs(String event, JSObject data) {
        if (getActivity() == null) {
            notifyListeners(event, data);
            return;
        }
        getActivity().runOnUiThread(() -> {
            try {
                WebView wv = getBridge() != null ? getBridge().getWebView() : null;
                if (wv != null) wv.resumeTimers();
            } catch (Throwable e) {
                Log.w(TAG, "resumeTimers failed", e);
            }
            notifyListeners(event, data);
        });
    }

    /** 把 100ms 的 short PCM 追加进缓冲，凑满 200ms 就上送一包（worker 线程调用） */
    private void appendCapture(short[] pcm, int n) {
        byte[] bytes = new byte[n * 2];
        for (int i = 0; i < n; i++) {
            bytes[2 * i] = (byte) (pcm[i] & 0xFF);
            bytes[2 * i + 1] = (byte) ((pcm[i] >> 8) & 0xFF);
        }
        capBuf.write(bytes, 0, bytes.length);
        while (capBuf.size() >= CAPTURE_PACKET_BYTES) {
            byte[] all = capBuf.toByteArray();
            capBuf.reset();
            capBuf.write(all, CAPTURE_PACKET_BYTES, all.length - CAPTURE_PACKET_BYTES);
            byte[] packet = new byte[CAPTURE_PACKET_BYTES];
            System.arraycopy(all, 0, packet, 0, CAPTURE_PACKET_BYTES);
            // 原生识别通道优先：息屏时 PCM 不能再绕道 WebView
            NativeAsrSession session;
            synchronized (asrLock) {
                session = asrSession;
            }
            if (session != null && session.isOpen()) {
                session.sendPcm(packet);
            }
            // 识别通道未就绪时丢弃 PCM；对话不再经 WebView
        }
    }

    // ------------------------------------------------------------------ 内部实现

    private void doStart(final PluginCall call) {
        final String keywords = call.getString("keywords", "");
        if (keywords == null || keywords.trim().isEmpty()) {
            call.reject("keywords 不能为空", "INVALID_KEYWORDS");
            return;
        }

        stopWorker();

        // 预先合成提示音（48k 混响计算量不小，别等到第一次唤醒才算）
        chimeExecutor.execute(() -> {
            if (chimePcm == null) chimePcm = buildChime();
        });

        final boolean wantBt = wantsBluetooth(call);
        final boolean btPermitted = Build.VERSION.SDK_INT < Build.VERSION_CODES.S
            || getPermissionState("bluetooth") == PermissionState.GRANTED;
        final Thread t = new Thread(
            () -> runWorker(call, keywords.trim(), wantBt, btPermitted), "wake-word-worker");
        synchronized (lock) {
            worker = t;
        }
        t.start();
    }

    private void stopWorker() {
        Thread t;
        synchronized (lock) {
            t = worker;
            worker = null;
        }
        running = false;
        closeAsrSession();
        if (t != null) {
            try {
                t.join(2000);
            } catch (InterruptedException ignored) {
                Thread.currentThread().interrupt();
            }
        }
    }

    private void keepScreenOn(final boolean on) {
        if (getActivity() == null) return;
        getActivity().runOnUiThread(() -> {
            if (on) {
                getActivity().getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
            } else {
                getActivity().getWindow().clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
            }
        });
    }

    private void emitError(String message) {
        JSObject o = new JSObject();
        o.put("message", message);
        notifyListeners("error", o);
    }

    /** 读取 tokens.txt 第一列，用于校验关键词，避免非法 token 导致原生层崩溃 */
    private Set<String> loadValidTokens(AssetManager am) throws Exception {
        Set<String> set = new HashSet<>();
        try (BufferedReader br = new BufferedReader(new InputStreamReader(am.open(TOKENS), StandardCharsets.UTF_8))) {
            String line;
            while ((line = br.readLine()) != null) {
                line = line.trim();
                if (line.isEmpty()) continue;
                set.add(line.split("\\s+")[0]);
            }
        }
        return set;
    }

    /** 返回错误信息；null 表示全部合法 */
    private String validateKeywords(String keywords) {
        List<String> bad = new ArrayList<>();
        for (String raw : keywords.split("/")) {
            String line = raw.trim();
            if (line.isEmpty()) continue;
            int at = line.indexOf('@');
            if (at <= 0 || at == line.length() - 1) {
                return "关键词格式错误（缺少 @原词）: " + line;
            }
            String name = line.substring(at + 1);
            for (String tok : line.substring(0, at).trim().split("\\s+")) {
                if (tok.isEmpty() || tok.startsWith(":") || tok.startsWith("#")) continue;
                if (!validTokens.contains(tok)) {
                    bad.add(tok + "（来自「" + name + "」）");
                }
            }
        }
        if (!bad.isEmpty()) {
            return "模型不支持这些读音，请换个词或调整读音: " + bad;
        }
        return null;
    }

    private void ensureSpotter() throws Exception {
        synchronized (lock) {
            if (spotter != null) return;
            AssetManager am = getContext().getAssets();
            validTokens = loadValidTokens(am);

            OnlineTransducerModelConfig transducer = new OnlineTransducerModelConfig();
            transducer.setEncoder(ENCODER);
            transducer.setDecoder(DECODER);
            transducer.setJoiner(JOINER);

            OnlineModelConfig model = new OnlineModelConfig();
            model.setTransducer(transducer);
            model.setTokens(TOKENS);
            model.setNumThreads(1);
            model.setProvider("cpu");
            model.setModelType("zipformer2");
            model.setDebug(false);

            FeatureConfig feat = new FeatureConfig();
            feat.setSampleRate(SAMPLE_RATE);
            feat.setFeatureDim(80);

            KeywordSpotterConfig config = new KeywordSpotterConfig();
            config.setFeatConfig(feat);
            config.setModelConfig(model);
            // 搜索路径数：快速说话 / 口音导致音节粘连时，路径太少会把正确读法提前剪掉。
            // 实测 4 -> 16 对快读明显更稳，耗时几乎不变。
            config.setMaxActivePaths(16);
            config.setKeywordsFile(DEFAULT_KEYWORDS);
            // 全局默认值；每个词的 :score / #threshold 由 JS 写进关键词行里覆盖
            config.setKeywordsScore(1.0f);
            config.setKeywordsThreshold(0.25f);
            config.setNumTrailingBlanks(1);

            spotter = new KeywordSpotter(am, config);
        }
    }

    // ------------------------------------------------------------ 蓝牙耳机麦克风

    private AudioManager audioManager() {
        return (AudioManager) getContext().getSystemService(Context.AUDIO_SERVICE);
    }

    private static boolean isBluetoothInput(AudioDeviceInfo d) {
        int t = d.getType();
        if (t == AudioDeviceInfo.TYPE_BLUETOOTH_SCO) return true;
        return Build.VERSION.SDK_INT >= Build.VERSION_CODES.S && t == AudioDeviceInfo.TYPE_BLE_HEADSET;
    }

    /**
     * 请求把通话音频链路切到蓝牙耳机（耳机平时只走 A2DP，没有麦克风）。
     * 返回 true 只代表「已发出切换请求」，真正是否生效以 AudioRecord.getRoutedDevice() 为准。
     */
    @SuppressWarnings("deprecation")
    private boolean routeToBluetooth() {
        AudioManager am = audioManager();
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            AudioDeviceInfo target = null;
            for (AudioDeviceInfo d : am.getAvailableCommunicationDevices()) {
                if (isBluetoothInput(d)) {
                    target = d;
                    break;
                }
            }
            if (target == null) return false;
            prevAudioMode = am.getMode();
            am.setMode(AudioManager.MODE_IN_COMMUNICATION);
            modeChanged = true;
            if (!am.setCommunicationDevice(target)) {
                am.setMode(prevAudioMode);
                modeChanged = false;
                return false;
            }
            commDeviceSet = true;
            return true;
        }

        // Android 11 及以下：走传统 SCO
        boolean hasBt = false;
        for (AudioDeviceInfo d : am.getDevices(AudioManager.GET_DEVICES_OUTPUTS)) {
            int t = d.getType();
            if (t == AudioDeviceInfo.TYPE_BLUETOOTH_A2DP || t == AudioDeviceInfo.TYPE_BLUETOOTH_SCO) {
                hasBt = true;
                break;
            }
        }
        if (!hasBt || !am.isBluetoothScoAvailableOffCall()) return false;
        prevAudioMode = am.getMode();
        am.setMode(AudioManager.MODE_IN_COMMUNICATION);
        modeChanged = true;
        am.startBluetoothSco();
        am.setBluetoothScoOn(true);
        scoStarted = true;
        return true;
    }

    /** 是否已接了耳机（有线 / 蓝牙 / USB）：接了就尊重用户，不强制外放 */
    private boolean hasExternalOutput(AudioManager am) {
        for (AudioDeviceInfo d : am.getDevices(AudioManager.GET_DEVICES_OUTPUTS)) {
            switch (d.getType()) {
                case AudioDeviceInfo.TYPE_WIRED_HEADSET:
                case AudioDeviceInfo.TYPE_WIRED_HEADPHONES:
                case AudioDeviceInfo.TYPE_USB_HEADSET:
                case AudioDeviceInfo.TYPE_USB_DEVICE:
                case AudioDeviceInfo.TYPE_BLUETOOTH_A2DP:
                case AudioDeviceInfo.TYPE_BLUETOOTH_SCO:
                    return true;
                default:
                    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S
                        && d.getType() == AudioDeviceInfo.TYPE_BLE_HEADSET) {
                        return true;
                    }
            }
        }
        return false;
    }

    /**
     * 通话通道默认走听筒，声音很小。没接耳机时把通话输出切到手机扬声器（免提）。
     * 只影响通话用途的音频（本应用的播报），退出时由 releaseBluetooth 还原。
     */
    @SuppressWarnings("deprecation")
    private void routeToSpeaker() {
        try {
            AudioManager am = audioManager();
            if (hasExternalOutput(am)) {
                Log.i(TAG, "speaker route skipped: external output connected");
                return;
            }
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                for (AudioDeviceInfo d : am.getAvailableCommunicationDevices()) {
                    if (d.getType() == AudioDeviceInfo.TYPE_BUILTIN_SPEAKER) {
                        if (am.setCommunicationDevice(d)) {
                            commDeviceSet = true;
                            Log.i(TAG, "speaker route: communication device = builtin speaker");
                        }
                        return;
                    }
                }
            } else {
                am.setSpeakerphoneOn(true);
                speakerphoneSet = true;
                Log.i(TAG, "speaker route: speakerphone on");
            }
        } catch (Throwable e) {
            Log.w(TAG, "routeToSpeaker failed", e);
        }
    }

    @SuppressWarnings("deprecation")
    private void releaseBluetooth() {
        try {
            AudioManager am = audioManager();
            if (speakerphoneSet) {
                am.setSpeakerphoneOn(false);
                speakerphoneSet = false;
            }
            if (commDeviceSet && Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                am.clearCommunicationDevice();
            }
            commDeviceSet = false;
            if (scoStarted) {
                am.setBluetoothScoOn(false);
                am.stopBluetoothSco();
            }
            scoStarted = false;
            if (modeChanged) {
                am.setMode(prevAudioMode);
            }
            modeChanged = false;
        } catch (Throwable e) {
            Log.w(TAG, "releaseBluetooth failed", e);
        }
    }

    // ------------------------------------------------------------ 唤醒提示音

    private static final int CHIME_RATE = 48000;
    private byte[] chimePcm;
    private final ExecutorService chimeExecutor = Executors.newSingleThreadExecutor();

    /** 思考背景音。token 用来区分「正在启动」和「启动过程中又被要求停掉」。 */
    private volatile boolean thinkRun;
    private int thinkToken;
    private Thread thinkThread;
    private final Object thinkLock = new Object();

    /**
     * 唤醒提示音，音质向 Apple 系统音效靠拢：
     *  - 48kHz 采样（手机原生输出采样率，不经过系统重采样）
     *  - 每个音由两个只差约 1.5 音分的振荡器叠成（合唱效果），音色温润、有「活」的微颤，而不是死板的电子正弦
     *  - 和声：C4 与主音 G4 同时起（纯五度），C5 作为很轻的八度光泽；三个音重叠成一个音；起音为 75ms 以上的柔和渐起，没有拨弦式的瞬态
     *  - 混响用施罗德结构（四路带阻尼的梳状滤波 + 两级全通），尾音平滑细腻；
     *    不再用几次离散回声，那种会带来金属感、听起来廉价
     */
    private byte[] buildChime() {
        final int rate = CHIME_RATE;
        final double[] freqs = {261.63, 392.00, 523.25}; // C4, G4, C5
        final double[] starts = {0.0, 0.0, 0.0};
        final double[] gains = {0.85, 1.0, 0.14};
        final double[] attacks = {0.075, 0.075, 0.10};
        final double dryLen = 0.7;
        final double tail = 0.25;
        final int n = (int) (rate * (dryLen + tail));
        final int dryN = (int) (rate * dryLen);
        final double detune = 0.0005; // 约 0.9 音分

        double[] dry = new double[n];
        for (int i = 0; i < dryN; i++) {
            double t = (double) i / rate;
            double s = 0;
            for (int k = 0; k < freqs.length; k++) {
                double lt = t - starts[k];
                if (lt < 0) continue;
                double a = Math.min(1.0, lt / attacks[k]);
                double attack = a * a * (3 - 2 * a);
                double env = Math.exp(-lt * 3.2);
                double w = 2 * Math.PI * freqs[k] * lt;
                double w1 = w * (1 + detune);
                double w2 = w * (1 - detune);
                double tone = 0.5 * (Math.sin(w1) + Math.sin(w2))
                    + 0.28 * 0.5 * (Math.sin(2 * w1) + Math.sin(2 * w2)) * Math.exp(-lt * 3.5)
                    + 0.08 * 0.5 * (Math.sin(3 * w1) + Math.sin(3 * w2)) * Math.exp(-lt * 4.5);
                s += gains[k] * attack * env * tone;
            }
            // 末端淡出，保证送进混响的信号是干净收尾的
            int left = dryN - i;
            int dfade = (int) (0.05 * rate);
            if (left < dfade) {
                double f = (double) left / dfade;
                s *= f;
            }
            dry[i] = s;
        }

        // 施罗德混响：四路梳状（带高频阻尼） + 两级全通
        final double[] combMs = {29.7, 37.1, 41.1, 43.7};
        final double combG = 0.60;
        final double damp = 0.45;
        double[] wet = new double[n];
        for (double ms : combMs) {
            int d = (int) (ms * rate / 1000.0);
            double[] buf = new double[d];
            int idx = 0;
            double lp = 0;
            for (int i = 0; i < n; i++) {
                double y = buf[idx];
                lp = y * (1 - damp) + lp * damp;
                buf[idx] = dry[i] + lp * combG;
                idx = (idx + 1) % d;
                wet[i] += y * 0.25;
            }
        }
        final double[] apMs = {5.0, 1.7};
        for (double ms : apMs) {
            int d = Math.max(1, (int) (ms * rate / 1000.0));
            double[] buf = new double[d];
            int idx = 0;
            final double g = 0.5;
            for (int i = 0; i < n; i++) {
                double x = wet[i];
                double v = buf[idx];
                wet[i] = v - g * x;
                buf[idx] = x + g * v;
                idx = (idx + 1) % d;
            }
        }

        double[] mix = new double[n];
        double peak = 1e-9;
        for (int i = 0; i < n; i++) {
            double v = dry[i] * 1.0 + wet[i] * 0.28;
            mix[i] = v;
            peak = Math.max(peak, Math.abs(v));
        }

        final double target = 0.5; // 峰值（满量程的比例）
        final int fade = (int) (0.25 * rate);
        byte[] out = new byte[n * 2];
        for (int i = 0; i < n; i++) {
            double v = mix[i] / peak * target;
            int left = n - i;
            if (left < fade) {
                double f = (double) left / fade;
                v *= f * f * (3 - 2 * f);
            }
            int q = (int) Math.round(v * 32767);
            q = Math.max(-32768, Math.min(32767, q));
            out[2 * i] = (byte) (q & 0xFF);
            out[2 * i + 1] = (byte) ((q >> 8) & 0xFF);
        }
        return out;
    }

    /** 命中唤醒词后的提示音；独立线程播放，不阻塞录音循环 */
    private void playChime() {
        // 提示音走媒体音量（和原来的蜂鸣一致）；只有蓝牙耳机走通话链路时才必须用通话流
        final boolean comm = btMode;
        try {
            chimeExecutor.execute(() -> {
                AudioTrack t = null;
                try {
                    if (chimePcm == null) chimePcm = buildChime();
                    AudioAttributes attrs = new AudioAttributes.Builder()
                        .setUsage(comm ? AudioAttributes.USAGE_VOICE_COMMUNICATION : AudioAttributes.USAGE_MEDIA)
                        .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
                        .build();
                    AudioFormat fmt = new AudioFormat.Builder()
                        .setEncoding(AudioFormat.ENCODING_PCM_16BIT)
                        .setSampleRate(CHIME_RATE)
                        .setChannelMask(AudioFormat.CHANNEL_OUT_MONO)
                        .build();
                    t = new AudioTrack(attrs, fmt, chimePcm.length, AudioTrack.MODE_STATIC,
                        AudioManager.AUDIO_SESSION_ID_GENERATE);
                    // 注意：MODE_STATIC 的轨道在写入数据之前状态是 STATE_NO_STATIC_DATA，
                    // 不能在 write 之前判断 STATE_INITIALIZED，否则永远判失败而不出声
                    int w = t.write(chimePcm, 0, chimePcm.length);
                    if (t.getState() != AudioTrack.STATE_INITIALIZED) {
                        Log.w(TAG, "playChime: AudioTrack 不可用，state=" + t.getState() + " written=" + w);
                        return;
                    }
                    t.setVolume(1.0f);
                    t.play();
                    Log.i(TAG, "playChime: 写入 " + w + " 字节, 媒体流=" + !comm);
                    Thread.sleep(chimePcm.length / 2 * 1000L / CHIME_RATE + 60);
                } catch (Throwable e) {
                    Log.w(TAG, "playChime failed", e);
                } finally {
                    if (t != null) {
                        try {
                            t.release();
                        } catch (Throwable ignored) {
                        }
                    }
                }
            });
        } catch (Throwable e) {
            Log.w(TAG, "playChime rejected", e);
        }
    }

    // ------------------------------------------------------------ 思考背景音

    /**
     * 思考状态的持续背景音。音高固定、不滑动，在 C 大调上用四组纯五度慢慢交接：
     * C–G、E–B、D–A、G–D，大约 16 秒走一圈。同一时刻主要听到两个音。
     * 开头就是唤醒音那组 C、G，随后换和声；音量大约是提示音的九分之一。
     * 进来先淡入，离开思考后再淡出，没有起音的敲击。
     */
    private void startThinkBed() {
        int token;
        Thread old;
        synchronized (thinkLock) {
            if (thinkRun && thinkThread != null && thinkThread.isAlive()) return;
            token = ++thinkToken;
            thinkRun = false;
            old = thinkThread;
        }
        if (old != null) {
            try {
                old.join(1500);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }
        synchronized (thinkLock) {
            if (token != thinkToken) return;
            thinkRun = true;
            thinkThread = new Thread(this::runThinkBed, "think-bed");
            thinkThread.setDaemon(true);
            thinkThread.start();
        }
    }

    /** 让背景音开始淡出。播放线程自己收尾，这里不等。 */
    private void stopThinkBed() {
        synchronized (thinkLock) {
            thinkToken++;
            thinkRun = false;
        }
    }

    /** 停掉并等到播放线程退出。销毁和解散引擎时用，避免 AudioTrack 泄漏。 */
    private void haltThinkBed() {
        Thread t;
        synchronized (thinkLock) {
            thinkToken++;
            thinkRun = false;
            t = thinkThread;
        }
        if (t != null) {
            try {
                t.join(1500);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }
    }

    private void runThinkBed() {
        final int rate = CHIME_RATE;
        final int block = rate / 20;
        AudioTrack track = null;
        try {
            final boolean comm = btMode;
            int minBuf = AudioTrack.getMinBufferSize(
                rate, AudioFormat.CHANNEL_OUT_MONO, AudioFormat.ENCODING_PCM_16BIT);
            if (minBuf <= 0) {
                Log.w(TAG, "thinkBed: 缓冲大小不可用 " + minBuf);
                return;
            }
            AudioAttributes attrs = new AudioAttributes.Builder()
                .setUsage(comm ? AudioAttributes.USAGE_VOICE_COMMUNICATION : AudioAttributes.USAGE_MEDIA)
                .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
                .build();
            AudioFormat fmt = new AudioFormat.Builder()
                .setEncoding(AudioFormat.ENCODING_PCM_16BIT)
                .setSampleRate(rate)
                .setChannelMask(AudioFormat.CHANNEL_OUT_MONO)
                .build();
            int bufBytes = Math.max(minBuf, block * 2 * 2);
            track = new AudioTrack(attrs, fmt, bufBytes, AudioTrack.MODE_STREAM,
                AudioManager.AUDIO_SESSION_ID_GENERATE);
            if (track.getState() != AudioTrack.STATE_INITIALIZED) {
                Log.w(TAG, "thinkBed: AudioTrack 初始化失败");
                return;
            }
            track.play();
            Log.i(TAG, "thinkBed: 开始, 媒体流=" + !comm);

            // C4 E4 G4 B4 D4 A4 D5。音高固定，靠包络交接，不在音高上滑动。
            final double[] freqs = {261.63, 329.63, 392.00, 493.88, 293.66, 440.00, 587.33};
            final double[] gains = {0.72, 0.62, 0.90, 0.48, 0.58, 0.46, 0.20};
            final int[] bloomNote = {0, 2, 1, 3, 4, 5, 2, 6};
            final double[] bloomAt = {0, 0, 4, 4, 8, 8, 12, 12};
            final double loop = 16.0;
            final double half = 3.4;
            final double detune = 0.0005;
            // 两组五度叠满时加权和约 1.6，压到唤醒音峰值（0.5）的大约九分之一
            final double norm = 0.055 / 1.7;
            final double[] ph = new double[freqs.length * 2];
            final double[] noteEnv = new double[freqs.length];
            double sec = 0;
            double in = 0;
            double out = 1;
            final double inStep = 1.0 / (rate * 0.7);
            final double outStep = 1.0 / (rate * 0.45);
            boolean stopping = false;
            final short[] pcm = new short[block];

            while (true) {
                if (!thinkRun) stopping = true;
                boolean done = false;
                for (int i = 0; i < block; i++) {
                    if (!thinkRun) stopping = true;
                    if (in < 1) in = Math.min(1.0, in + inStep);
                    if (stopping) {
                        out -= outStep;
                        if (out <= 0) {
                            out = 0;
                            done = true;
                        }
                    }
                    for (int k = 0; k < noteEnv.length; k++) noteEnv[k] = 0;
                    for (int b = 0; b < bloomNote.length; b++) {
                        double dist = sec - bloomAt[b];
                        dist -= loop * Math.floor((dist + loop / 2) / loop);
                        dist = Math.abs(dist);
                        if (dist >= half) continue;
                        double x = dist / half;
                        double coss = Math.cos(x * Math.PI / 2);
                        double envN = coss * coss;
                        int ni = bloomNote[b];
                        if (envN > noteEnv[ni]) noteEnv[ni] = envN;
                    }
                    sec += 1.0 / rate;
                    if (sec >= loop) sec -= loop;
                    double env = (in * in * (3 - 2 * in)) * (out * out * (3 - 2 * out));
                    double s = 0;
                    for (int k = 0; k < freqs.length; k++) {
                        if (noteEnv[k] < 0.001) continue;
                        double d1 = 2 * Math.PI * freqs[k] * (1 + detune) / rate;
                        double d2 = 2 * Math.PI * freqs[k] * (1 - detune) / rate;
                        int i1 = k * 2;
                        int i2 = i1 + 1;
                        ph[i1] += d1;
                        ph[i2] += d2;
                        if (ph[i1] > 2 * Math.PI) ph[i1] -= 2 * Math.PI;
                        if (ph[i2] > 2 * Math.PI) ph[i2] -= 2 * Math.PI;
                        double a = Math.sin(ph[i1]);
                        double bsin = Math.sin(ph[i2]);
                        s += gains[k] * noteEnv[k] * (0.5 * (a + bsin)
                            + 0.08 * 0.5 * (Math.sin(ph[i1] * 2) + Math.sin(ph[i2] * 2)));
                    }
                    int q = (int) Math.round(s * env * norm * 32767);
                    if (q > 32767) q = 32767;
                    else if (q < -32768) q = -32768;
                    pcm[i] = (short) q;
                    if (done) {
                        for (int j = i + 1; j < block; j++) pcm[j] = 0;
                        break;
                    }
                }
                int off = 0;
                while (off < block) {
                    int wrote = track.write(pcm, off, block - off);
                    if (wrote < 0) {
                        Log.w(TAG, "thinkBed: write 失败 " + wrote);
                        done = true;
                        break;
                    }
                    if (wrote == 0) {
                        try {
                            Thread.sleep(5);
                        } catch (InterruptedException e) {
                            Thread.currentThread().interrupt();
                            done = true;
                            break;
                        }
                        continue;
                    }
                    off += wrote;
                }
                if (done) break;
            }
            try {
                Thread.sleep(bufBytes / 2 * 1000L / rate + 40);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
            Log.i(TAG, "thinkBed: 结束");
        } catch (Throwable e) {
            Log.w(TAG, "thinkBed failed", e);
        } finally {
            if (track != null) {
                try {
                    track.pause();
                    track.flush();
                    track.release();
                } catch (Throwable ignored) {
                }
            }
        }
    }

    /** 打开系统回声消除 / 降噪；返回 "on" 或 "on+ns" 或 "off:原因" */
    private String attachEffects(int sessionId) {
        String r;
        try {
            if (AcousticEchoCanceler.isAvailable()) {
                aec = AcousticEchoCanceler.create(sessionId);
                if (aec != null) {
                    aec.setEnabled(true);
                }
            }
            if (NoiseSuppressor.isAvailable()) {
                ns = NoiseSuppressor.create(sessionId);
                if (ns != null) {
                    ns.setEnabled(true);
                }
            }
        } catch (Throwable e) {
            Log.w(TAG, "attachEffects failed", e);
        }
        boolean aecOn = aec != null && aec.getEnabled();
        // 即使没有显式的 AEC 效果器，VOICE_COMMUNICATION 源在不少机型上也自带处理，这里只如实报告
        r = aecOn ? (ns != null ? "on+ns" : "on") : "off:效果器不可用";
        return r;
    }

    private void releaseEffects() {
        try {
            if (aec != null) aec.release();
        } catch (Throwable ignored) {
        }
        try {
            if (ns != null) ns.release();
        } catch (Throwable ignored) {
        }
        aec = null;
        ns = null;
    }

    /** 当前录音实际用的是哪个麦克风，给界面显示 */
    private String describeInput(AudioRecord recorder) {
        AudioDeviceInfo d = recorder.getRoutedDevice();
        if (d == null) return "未知";
        String kind;
        switch (d.getType()) {
            case AudioDeviceInfo.TYPE_BUILTIN_MIC:
                return "手机麦克风";
            case AudioDeviceInfo.TYPE_WIRED_HEADSET:
                kind = "有线耳机";
                break;
            case AudioDeviceInfo.TYPE_USB_DEVICE:
            case AudioDeviceInfo.TYPE_USB_HEADSET:
                kind = "USB 麦克风";
                break;
            default:
                kind = isBluetoothInput(d) ? "蓝牙耳机" : "其他设备(" + d.getType() + ")";
        }
        CharSequence name = d.getProductName();
        return (name == null || name.length() == 0) ? kind : kind + "（" + name + "）";
    }

    private boolean isRoutedToBluetooth(AudioRecord recorder) {
        AudioDeviceInfo d = recorder.getRoutedDevice();
        return d != null && isBluetoothInput(d);
    }

    private void runWorker(PluginCall call, String keywords, boolean wantBt, boolean btPermitted) {
        AudioRecord recorder = null;
        OnlineStream stream = null;
        boolean resolved = false;
        try {
            ensureSpotter();
            String err = validateKeywords(keywords);
            if (err != null) {
                call.reject(err, "INVALID_KEYWORDS");
                resolved = true;
                return;
            }

            final KeywordSpotter kws = spotter;
            stream = kws.createStream(keywords);

            String note = "";
            boolean btRequested = false;
            if (wantBt) {
                if (!btPermitted) {
                    note = "未授予蓝牙权限，已使用手机麦克风";
                } else {
                    btRequested = routeToBluetooth();
                    if (!btRequested) note = "没有检测到可用的蓝牙耳机麦克风，已使用手机麦克风";
                }
            }

            int minBuf = AudioRecord.getMinBufferSize(
                SAMPLE_RATE, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT);
            int bufBytes = Math.max(minBuf, SAMPLE_RATE * 2);
            // 走蓝牙通话链路时用 VOICE_COMMUNICATION，系统才会把录音路由到耳机
            bargeIn = Boolean.TRUE.equals(call.getBoolean("bargeIn", false));
            // 播报走通话通道时，默认外放（免提），否则声音从听筒出来很小
            if (bargeIn && !btRequested) routeToSpeaker();
            recorder = new AudioRecord(
                (btRequested || bargeIn) ? MediaRecorder.AudioSource.VOICE_COMMUNICATION
                            : MediaRecorder.AudioSource.VOICE_RECOGNITION,
                SAMPLE_RATE,
                AudioFormat.CHANNEL_IN_MONO,
                AudioFormat.ENCODING_PCM_16BIT,
                bufBytes);
            if (recorder.getState() != AudioRecord.STATE_INITIALIZED) {
                call.reject("麦克风初始化失败（可能被其他应用占用）", "MIC_INIT_FAILED");
                resolved = true;
                return;
            }
            if (btRequested) {
                for (AudioDeviceInfo d : audioManager().getDevices(AudioManager.GET_DEVICES_INPUTS)) {
                    if (isBluetoothInput(d)) {
                        recorder.setPreferredDevice(d);
                        break;
                    }
                }
            }
            String aecState = "";
            if (bargeIn) {
                aecState = attachEffects(recorder.getAudioSessionId());
                if (!aecState.startsWith("on")) {
                    note = (note.isEmpty() ? "" : note + "；") + "本机没有可用的回声消除，播报时喊唤醒词可能误触发或不灵";
                }
            }
            recorder.startRecording();

            // SCO 链路建立需要 1~2 秒，等它真正切过去（最多 3 秒）再汇报结果
            if (btRequested) {
                long deadline = System.currentTimeMillis() + 3000;
                while (!isRoutedToBluetooth(recorder) && System.currentTimeMillis() < deadline) {
                    Thread.sleep(100);
                }
                if (!isRoutedToBluetooth(recorder)) {
                    note = "蓝牙耳机麦克风没有接通（耳机可能不支持通话麦克风），正在使用: "
                        + describeInput(recorder);
                }
            }

            running = true;
            keepScreenOn(true);
            JSObject result = new JSObject();
            result.put("input", describeInput(recorder));
            result.put("bluetooth", isRoutedToBluetooth(recorder));
            result.put("note", note);
            result.put("bargeIn", bargeIn);
            result.put("aec", aecState);
            call.resolve(result);
            resolved = true;

            loop(kws, stream, recorder, btRequested);
        } catch (Throwable e) {
            Log.e(TAG, "worker error", e);
            if (!resolved) {
                call.reject("唤醒引擎启动失败: " + e.getMessage(), "START_FAILED");
            } else {
                emitError("唤醒引擎异常: " + e.getMessage());
            }
        } finally {
            running = false;
            capturing = false;
            releaseEffects();
            keepScreenOn(false);
            if (recorder != null) {
                try {
                    recorder.stop();
                } catch (Throwable ignored) {
                }
                recorder.release();
            }
            // 必须还原：否则停止后耳机会一直停留在通话模式，音乐音质很差
            releaseBluetooth();
            if (stream != null) {
                stream.release();
            }
            JSObject o = new JSObject();
            o.put("running", false);
            notifyListeners("status", o);
        }
    }

    private void loop(KeywordSpotter kws, OnlineStream stream, AudioRecord recorder, boolean btMode) {
        this.btMode = btMode;
        capturing = false;
        kwsDirty = false;
        capBuf.reset();
        final short[] pcm = new short[CHUNK_SAMPLES];
        final float[] full = new float[CHUNK_SAMPLES];
        final long startMs = System.currentTimeMillis();
        long lastStatusMs = startMs;
        long lastWakeMs = 0;
        int wakeCount = 0;

        // 统计窗口：用「模型处理耗时 / 音频时长」近似常驻 CPU 占用
        long winProcNs = 0;
        long winAudioNs = 0;
        int winChunks = 0;

        // 音量表：每 200ms 汇报一次这段时间内的峰值（分贝刻度，更接近人耳感受）
        long lastLevelMs = startMs;
        int lvlPeak = 0;
        double lvlSumSq = 0;
        long lvlCount = 0;

        while (running) {
            int n = recorder.read(pcm, 0, pcm.length);
            if (n < 0) {
                emitError("录音读取失败，错误码 " + n);
                break;
            }
            if (n == 0) continue;

            for (int i = 0; i < n; i++) {
                float v = pcm[i] / 32768f;
                full[i] = v;
                int a = Math.abs((int) pcm[i]);
                if (a > lvlPeak) lvlPeak = a;
                lvlSumSq += (double) v * v;
            }
            lvlCount += n;
            float[] samples = (n == full.length) ? full : Arrays.copyOf(full, n);

            long now = System.currentTimeMillis();
            // 半双工：播报期间（及结束后一小段）不听，避免把自己的声音当成唤醒词或用户说话
            boolean muted = (!bargeIn && playing) || now < muteUntilMs;
            String hit = null;

            if (muted) {
                kwsDirty = true;
                capBuf.reset();
            } else {
                // 采集模式：把 PCM 打包上送给 JS（识别由云端完成）。
                // 注意唤醒引擎在采集期间也要照常跑：连续对话时采集会一直开着，
                // 以前这里直接跳过唤醒，一旦 JS 侧识别通道卡住，唤醒词就彻底失效。
                if (capturing) {
                    appendCapture(pcm, n);
                } else {
                    capBuf.reset();
                }
                if (kwsDirty) {
                    // 刚从播报静音切回来：清掉唤醒引擎里残留的上下文
                    kws.reset(stream);
                    kwsDirty = false;
                }
                long t0 = System.nanoTime();
                stream.acceptWaveform(samples, SAMPLE_RATE);
                while (kws.isReady(stream)) {
                    kws.decode(stream);
                    String kw = kws.getResult(stream).getKeyword();
                    if (kw != null && !kw.isEmpty()) {
                        hit = kw;
                        kws.reset(stream);
                    }
                }
                winProcNs += System.nanoTime() - t0;
                winAudioNs += (long) n * 1_000_000_000L / SAMPLE_RATE;
                winChunks++;
            }

            if (hit != null && now - lastWakeMs >= COOLDOWN_MS) {
                lastWakeMs = now;
                wakeCount++;
                stopThinkBed();
                playChime();
                // 命中后立刻进入采集，并在原生层建识别通道——不等 JS / WebView。
                // 息屏时 WebView 可能要好几秒才醒，这段时间用户已经在说话，必须由原生接住。
                final boolean wasCapturing = capturing;
                capturing = true;
                capBuf.reset();
                if (orchestrator.isEnabled()) {
                    Log.i("Yavis", "wake → native pipeline keyword=" + hit);
                    try {
                        orchestrator.onWake(hit);
                    } catch (Throwable e) {
                        Log.w(TAG, "orchestrator onWake", e);
                    }
                } else if (asrUrl != null && !asrUrl.isEmpty()) {
                    Log.i("Yavis", "wake → open native ASR keyword=" + hit);
                    openAsrSession(asrUrl);
                } else {
                    Log.w("Yavis", "wake but asrUrl empty, cannot open ASR");
                }
                // 播报中被唤醒词打断：原生就地停掉播放，不等 JS 来回一趟，避免把扬声器尾音录进去
                boolean barged = false;
                if (playing) {
                    barged = true;
                    stopPlayback(true);
                    emitPlayEnd(true);
                }
                JSObject o = new JSObject();
                o.put("interrupted", barged);
                o.put("capturing", wasCapturing);
                o.put("keyword", hit);
                o.put("count", wakeCount);
                o.put("tsMs", now);
                notifyJs("wake", o);
            }

            if (now - lastLevelMs >= LEVEL_INTERVAL_MS) {
                // 满量程为 0 dB；-60 dB 以下按静音处理
                double peakDb = 20 * Math.log10(Math.max(lvlPeak, 1) / 32768.0);
                double rmsDb = 10 * Math.log10(Math.max(lvlCount == 0 ? 0 : lvlSumSq / lvlCount, 1e-12));
                JSObject lv = new JSObject();
                lv.put("peakDb", Math.round(peakDb));
                lv.put("rmsDb", Math.round(rmsDb));
                lv.put("level", (int) Math.max(0, Math.min(100, (peakDb + 60) / 50 * 100)));
                notifyListeners("level", lv);
                lastLevelMs = now;
                lvlPeak = 0;
                lvlSumSq = 0;
                lvlCount = 0;
            }

            if (now - lastStatusMs >= STATUS_INTERVAL_MS) {
                JSObject o = new JSObject();
                o.put("running", true);
                o.put("elapsedSec", (now - startMs) / 1000);
                o.put("avgProcMs", winChunks == 0 ? 0 : (winProcNs / 1e6) / winChunks);
                o.put("loadPct", winAudioNs == 0 ? 0 : (winProcNs * 100.0) / winAudioNs);
                o.put("wakeCount", wakeCount);
                o.put("input", describeInput(recorder));
                o.put("bluetooth", isRoutedToBluetooth(recorder));
                o.put("capturing", capturing);
                o.put("playing", playing);
                notifyListeners("status", o);
                lastStatusMs = now;
                winProcNs = 0;
                winAudioNs = 0;
                winChunks = 0;
            }
        }
    }
}

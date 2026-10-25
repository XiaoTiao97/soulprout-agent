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
import android.media.ToneGenerator;
import android.os.Build;
import android.util.Base64;
import android.util.Log;
import android.view.WindowManager;

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

    /** 采集模式：命中唤醒词或 JS 调 beginCapture 后置位，PCM 以 audio 事件上送 */
    private volatile boolean capturing = false;
    /** 正在播报：此时既不唤醒也不采集 */
    private volatile boolean playing = false;
    private volatile long muteUntilMs = 0;
    /** 从播报 / 采集切回待命时，需要先清空唤醒引擎的上下文（仅 worker 线程读写） */
    private boolean kwsDirty = false;
    private volatile boolean btMode = false;
    private final ByteArrayOutputStream capBuf = new ByteArrayOutputStream(CAPTURE_PACKET_BYTES * 2);
    private int captureSeq = 0;

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
        stopPlayback(true);
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
        stopPlayback(true);
        stopWorker();
    }

    /** 不经唤醒词直接进入采集（连续对话：播报结束后继续听用户说） */
    @PluginMethod
    public void beginCapture(PluginCall call) {
        capBuf.reset();
        captureSeq = 0;
        capturing = true;
        call.resolve();
    }

    /** 结束采集，回到唤醒词待命 */
    @PluginMethod
    public void endCapture(PluginCall call) {
        capturing = false;
        call.resolve();
    }

    @PluginMethod
    public void playStart(PluginCall call) {
        int rate = call.getInt("sampleRate", PLAY_SAMPLE_RATE_DEFAULT);
        stopPlayback(false);
        try {
            int minBuf = AudioTrack.getMinBufferSize(rate, AudioFormat.CHANNEL_OUT_MONO, AudioFormat.ENCODING_PCM_16BIT);
            AudioAttributes attrs = new AudioAttributes.Builder()
                // 耳机走通话链路时，播放也要走通话音量流，否则耳机里可能没声音
                .setUsage(btMode ? AudioAttributes.USAGE_VOICE_COMMUNICATION : AudioAttributes.USAGE_MEDIA)
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
                call.reject("播放器初始化失败", "PLAY_INIT_FAILED");
                return;
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
            call.resolve();
        } catch (Throwable e) {
            Log.e(TAG, "playStart failed", e);
            playing = false;
            call.reject("播放器启动失败: " + e.getMessage(), "PLAY_INIT_FAILED");
        }
    }

    /** pcm：base64 编码的 16bit 小端单声道，采样率同 playStart */
    @PluginMethod
    public void playWrite(PluginCall call) {
        String b64 = call.getString("pcm", "");
        final AudioTrack t;
        final ExecutorService ex;
        synchronized (playLock) {
            t = track;
            ex = playExecutor;
        }
        if (t == null || ex == null || b64 == null || b64.isEmpty()) {
            call.resolve();
            return;
        }
        final byte[] data = Base64.decode(b64, Base64.DEFAULT);
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
        call.resolve();
    }

    /** 文本都送完了：等已写入的音频播完，再发 playEnd */
    @PluginMethod
    public void playFinish(PluginCall call) {
        final AudioTrack t;
        final ExecutorService ex;
        synchronized (playLock) {
            t = track;
            ex = playExecutor;
        }
        call.resolve();
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
            long deadline = System.currentTimeMillis() + frames * 1000L / rate + 3000;
            try {
                while (gen == playGen.get() && System.currentTimeMillis() < deadline) {
                    // 头位置是无符号 32 位，这里按 int 比较足够（单次播报远小于 2^31 帧）
                    if ((t.getPlaybackHeadPosition() & 0xFFFFFFFFL) >= frames) break;
                    Thread.sleep(40);
                }
            } catch (Throwable ignored) {
            }
            if (gen != playGen.get()) return; // 已被 playStop 接管
            stopPlayback(false);
            emitPlayEnd(false);
        });
    }

    /** 立刻打断播报 */
    @PluginMethod
    public void playStop(PluginCall call) {
        boolean wasPlaying = playing;
        stopPlayback(true);
        call.resolve();
        if (wasPlaying) emitPlayEnd(true);
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
            muteUntilMs = System.currentTimeMillis() + POST_PLAY_MUTE_MS;
        }
        playing = false;
    }

    private void emitPlayEnd(boolean interrupted) {
        JSObject o = new JSObject();
        o.put("interrupted", interrupted);
        notifyListeners("playEnd", o);
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
            JSObject o = new JSObject();
            o.put("pcm", Base64.encodeToString(all, 0, CAPTURE_PACKET_BYTES, Base64.NO_WRAP));
            o.put("seq", captureSeq++);
            notifyListeners("audio", o);
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

    @SuppressWarnings("deprecation")
    private void releaseBluetooth() {
        try {
            AudioManager am = audioManager();
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
            recorder = new AudioRecord(
                btRequested ? MediaRecorder.AudioSource.VOICE_COMMUNICATION
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
        ToneGenerator tone = null;
        try {
            // 通话链路下提示音要走通话音量流，否则耳机里可能听不到
            tone = new ToneGenerator(btMode ? AudioManager.STREAM_VOICE_CALL : AudioManager.STREAM_MUSIC, 80);
        } catch (Throwable e) {
            Log.w(TAG, "ToneGenerator unavailable", e);
        }

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
            boolean muted = playing || now < muteUntilMs;
            String hit = null;

            if (muted) {
                kwsDirty = true;
                capBuf.reset();
            } else if (capturing) {
                // 采集模式：把 PCM 打包上送给 JS（识别由云端完成），此时不再跑唤醒
                kwsDirty = true;
                appendCapture(pcm, n);
            } else {
                capBuf.reset();
                if (kwsDirty) {
                    // 刚从播报 / 采集切回待命：清掉唤醒引擎里残留的上下文
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
                if (tone != null) {
                    tone.startTone(ToneGenerator.TONE_PROP_BEEP);
                }
                // 命中后立刻进入采集，后续音频直接上送，不丢「唤醒词 + 指令」连说的内容
                capturing = true;
                capBuf.reset();
                JSObject o = new JSObject();
                o.put("keyword", hit);
                o.put("count", wakeCount);
                o.put("tsMs", now);
                notifyListeners("wake", o);
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

        if (tone != null) {
            tone.release();
        }
    }
}

package com.soulprout.agent;

import java.util.regex.Pattern;

/**
 * 把 Agent 流式文本切成适合送去合成的句子（与 web sentenceSplitter.js 对齐）。
 */
final class SentenceSplitter {
    interface Listener {
        void onSentence(String sentence);
    }

    private static final Pattern STRONG_END = Pattern.compile("[。！？!?；;\\n]");
    private static final Pattern WEAK_END = Pattern.compile("[，,、：:]");
    private static final Pattern HAS_WORD = Pattern.compile("[\\p{L}\\p{N}]");
    private static final int FIRST_SOFT = 6;
    private static final int HARD = 60;

    private final Listener listener;
    private final StringBuilder buf = new StringBuilder();
    private boolean emittedAny = false;

    SentenceSplitter(Listener listener) {
        this.listener = listener;
    }

    void push(String delta) {
        if (delta == null || delta.isEmpty()) return;
        buf.append(delta);
        drain(false);
    }

    void flush() {
        drain(true);
    }

    void reset() {
        buf.setLength(0);
        emittedAny = false;
    }

    private boolean insideCode() {
        int n = 0;
        String s = buf.toString();
        for (int i = 0; i + 2 < s.length(); i++) {
            if (s.charAt(i) == '`' && s.charAt(i + 1) == '`' && s.charAt(i + 2) == '`') {
                n++;
                i += 2;
            }
        }
        return n % 2 == 1;
    }

    private void emit(String raw) {
        String clean = cleanForSpeech(raw);
        if (clean.isEmpty() || !HAS_WORD.matcher(clean).find()) return;
        emittedAny = true;
        listener.onSentence(clean);
    }

    private void drain(boolean finalPass) {
        if (!insideCode()) {
            String s = buf.toString().replaceAll("```[\\s\\S]*?```", " ");
            buf.setLength(0);
            buf.append(s);
        }
        while (buf.length() > 0 && !insideCode()) {
            int cut = -1;
            for (int i = 0; i < buf.length(); i++) {
                char ch = buf.charAt(i);
                if (STRONG_END.matcher(String.valueOf(ch)).matches()) {
                    int j = i + 1;
                    while (j < buf.length() && STRONG_END.matcher(String.valueOf(buf.charAt(j))).matches()) j++;
                    cut = j;
                    break;
                }
                int limit = emittedAny ? HARD : FIRST_SOFT;
                if (i + 1 >= limit && WEAK_END.matcher(String.valueOf(ch)).matches()) {
                    cut = i + 1;
                    break;
                }
            }
            if (cut < 0) break;
            emit(buf.substring(0, cut));
            buf.delete(0, cut);
        }
        if (finalPass) {
            String rest = buf.toString().trim();
            if (!rest.isEmpty() && !insideCode()) emit(rest);
            buf.setLength(0);
        }
    }

    static String cleanForSpeech(String text) {
        if (text == null) return "";
        String s = text;
        s = s.replaceAll("```[\\s\\S]*?```", "");
        s = s.replaceAll("`([^`]*)`", "$1");
        s = s.replaceAll("!\\[[^\\]]*\\]\\([^)]*\\)", "");
        s = s.replaceAll("\\[([^\\]]*)\\]\\([^)]*\\)", "$1");
        s = s.replaceAll("https?://\\S+", "");
        s = s.replaceAll("(?m)^\\s{0,3}#{1,6}\\s*", "");
        s = s.replaceAll("(?m)^\\s*[-*+]\\s+", "");
        s = s.replaceAll("(?m)^\\s*\\d+[.)]\\s+", "");
        s = s.replaceAll("[*_~>|#]", "");
        // 去掉常见 emoji 区段
        StringBuilder out = new StringBuilder();
        for (int i = 0; i < s.length(); ) {
            int cp = s.codePointAt(i);
            i += Character.charCount(cp);
            if (cp >= 0x1F300 && cp <= 0x1FAFF) continue;
            if (cp >= 0x2600 && cp <= 0x27BF) continue;
            out.appendCodePoint(cp);
        }
        return out.toString().replaceAll("[ \\t]+", " ").trim();
    }

    static int validChars(String text) {
        if (text == null) return 0;
        int n = 0;
        for (int i = 0; i < text.length(); ) {
            int cp = text.codePointAt(i);
            i += Character.charCount(cp);
            if (Character.isWhitespace(cp)) continue;
            int type = Character.getType(cp);
            if (type == Character.CONNECTOR_PUNCTUATION
                || type == Character.DASH_PUNCTUATION
                || type == Character.START_PUNCTUATION
                || type == Character.END_PUNCTUATION
                || type == Character.INITIAL_QUOTE_PUNCTUATION
                || type == Character.FINAL_QUOTE_PUNCTUATION
                || type == Character.OTHER_PUNCTUATION
                || type == Character.MATH_SYMBOL
                || type == Character.CURRENCY_SYMBOL
                || type == Character.MODIFIER_SYMBOL
                || type == Character.OTHER_SYMBOL) {
                continue;
            }
            n++;
        }
        return n;
    }
}

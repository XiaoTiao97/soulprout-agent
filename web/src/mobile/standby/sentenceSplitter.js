/**
 * 把 Agent 流式输出的文本切成适合送去合成的「句子」，并去掉朗读时不该出现的 Markdown 符号。
 * 目标：第一句尽早放出以降低首字延迟，之后按完整句子送，保证语气自然。
 */

const STRONG_END = /[。！？!?；;\n]/
const WEAK_END = /[，,、：:]/

/** 首句长到这个字数还没遇到句末标点，就在逗号处先放出去 */
const FIRST_SENTENCE_SOFT_LIMIT = 14
/** 任何一句超过这个字数都强制在弱标点处断开，避免一句话憋太久 */
const SENTENCE_HARD_LIMIT = 60

/** 朗读用的清洗：去代码块、链接地址、Markdown 标记、表情符号，保留文字内容 */
export function cleanForSpeech(text) {
  return text
    .replace(/```[\s\S]*?```/g, '')
    .replace(/`([^`]*)`/g, '$1')
    .replace(/!\[[^\]]*\]\([^)]*\)/g, '')
    .replace(/\[([^\]]*)\]\([^)]*\)/g, '$1')
    .replace(/https?:\/\/\S+/g, '')
    .replace(/^\s{0,3}#{1,6}\s*/gm, '')
    .replace(/^\s*[-*+]\s+/gm, '')
    .replace(/^\s*\d+[.)]\s+/gm, '')
    .replace(/[*_~>|#]/g, '')
    .replace(/[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]/gu, '')
    .replace(/[ \t]+/g, ' ')
    .trim()
}

export function createSentenceSplitter(onSentence) {
  let buf = ''
  let emittedAny = false
  /** 代码块内的内容不读：遇到奇数个 ``` 时先憋着，等闭合 */
  const insideCode = () => (buf.match(/```/g) || []).length % 2 === 1

  function emit(raw) {
    const clean = cleanForSpeech(raw)
    // 只剩标点 / 空白的片段没有朗读价值
    if (clean && /[\p{L}\p{N}]/u.test(clean)) {
      emittedAny = true
      onSentence(clean)
    }
  }

  function drain(final) {
    // 已闭合的代码块整段丢掉（朗读代码没有意义）；未闭合的先憋着
    if (!insideCode()) buf = buf.replace(/```[\s\S]*?```/g, ' ')
    while (buf && !insideCode()) {
      let cut = -1
      for (let i = 0; i < buf.length; i++) {
        const ch = buf[i]
        if (STRONG_END.test(ch)) {
          // 吞掉连续的结束标点，如「？！」「……」
          let j = i + 1
          while (j < buf.length && STRONG_END.test(buf[j])) j++
          cut = j
          break
        }
        const limit = emittedAny ? SENTENCE_HARD_LIMIT : FIRST_SENTENCE_SOFT_LIMIT
        if (i + 1 >= limit && WEAK_END.test(ch)) {
          cut = i + 1
          break
        }
      }
      // 半角句号 "." 不算句末（避免把 3.14 切开），中文句号 "。" 一律断开
      if (cut < 0) break
      emit(buf.slice(0, cut))
      buf = buf.slice(cut)
    }
    if (final && buf.trim() && !insideCode()) {
      emit(buf)
      buf = ''
    } else if (final) {
      buf = ''
    }
  }

  return {
    push(delta) {
      buf += delta
      drain(false)
    },
    /** 流结束：把剩余内容也放出去 */
    flush() {
      drain(true)
    },
    reset() {
      buf = ''
      emittedAny = false
    },
  }
}

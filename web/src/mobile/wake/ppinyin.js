/**
 * 把唤醒词转成 sherpa-onnx KWS 使用的 token。
 *
 * 中文与官方 `sherpa-onnx-cli text2token --tokens-type ppinyin` 一致
 * （pypinyin 的 to_initials / to_finals_tone，strict=False，y/w 当声母）。
 * 例：小章同学 -> "x iǎo zh āng t óng x ué @小章同学"
 * 英文按模型词表里的大写字母逐个拼：Yavis -> "Y A V I S @Yavis"
 *
 * 关键点：模型匹配的是「声音」，所以 小张 / 小章 会得到完全相同的 token。
 */
import { pinyin } from 'pinyin-pro'

// 双字母声母必须排在前面，保证 zh/ch/sh 优先匹配
const INITIALS = ['zh', 'ch', 'sh', 'b', 'p', 'm', 'f', 'd', 't', 'n', 'l', 'g', 'k', 'h', 'j', 'q', 'x', 'r', 'z', 'c', 's', 'y', 'w']

const HAN = /[\u4e00-\u9fff]/
const LAT = /[A-Za-z]/
const WAKE_WORD = /^[\u4e00-\u9fffA-Za-z ]+$/

/** 单个带调拼音音节 -> [声母?, 韵母] */
export function splitSyllable(syllable) {
  for (const ini of INITIALS) {
    if (syllable.startsWith(ini) && syllable.length > ini.length) {
      return [ini, syllable.slice(ini.length)]
    }
  }
  return [syllable]
}

export function normalizeWakeWord(text) {
  return (text || '').trim().replace(/\s+/g, ' ')
}

/**
 * 校验唤醒词是否可用，返回 { ok, reason }。
 * reason 对应界面文案。这里只做字符层面的检查；读音是否在模型词表里由原生层再校验一次。
 * 纯中文保持 2 到 8 个字。纯英文至少 4 个字母；中英放在同一句里时，汉字加字母至少 4 个。
 */
export function validateWakeWord(text) {
  const t = normalizeWakeWord(text)
  if (!t) return { ok: false, reason: 'empty' }
  if (!WAKE_WORD.test(t)) return { ok: false, reason: 'charset' }
  const han = (t.match(/[\u4e00-\u9fff]/g) || []).length
  const letters = (t.match(/[A-Za-z]/g) || []).length
  if (letters === 0) {
    if (han < 2) return { ok: false, reason: 'hanShort' }
    if (han > 8) return { ok: false, reason: 'hanLong' }
    return { ok: true, reason: '' }
  }
  // 纯英文太短会误唤醒；和汉字组成一句时，看总长度，整句都要说出来才会命中
  if ((han === 0 && letters < 4) || (han > 0 && han + letters < 4)) {
    return { ok: false, reason: 'letterShort' }
  }
  if (han + letters > 20) return { ok: false, reason: 'tooLong' }
  return { ok: true, reason: '' }
}

/**
 * 返回每个字的拼音（带声调符号），用于界面展示和多音字确认。
 * @returns {string[]} 例：['xiǎo','zhāng']
 */
export function toSyllables(text) {
  return pinyin(text.trim(), { toneType: 'symbol', type: 'array', v: false })
}

/**
 * 界面上的分块：汉字一块带拼音，连续的英文一块带大写字母序列。
 * @returns {{text: string, note: string}[]}
 */
export function wakeWordPieces(text) {
  const chars = [...normalizeWakeWord(text)]
  const pieces = []
  let i = 0
  while (i < chars.length) {
    if (chars[i] === ' ') {
      i++
      continue
    }
    if (HAN.test(chars[i])) {
      const ch = chars[i]
      pieces.push({ text: ch, note: toSyllables(ch)[0] || '' })
      i++
      continue
    }
    if (LAT.test(chars[i])) {
      let word = ''
      while (i < chars.length && LAT.test(chars[i])) {
        word += chars[i]
        i++
      }
      pieces.push({ text: word, note: [...word].map((c) => c.toUpperCase()).join(' ') })
      continue
    }
    i++
  }
  return pieces
}

/**
 * 生成一行 KWS 关键词。
 * 中文仍是声母 + 带调韵母；英文在这个模型里是逐个大写字母，例如 Yavis → `Y A V I S @Yavis`。
 * 小写字母会被当成中文韵母，所以英文必须大写。
 * @param {string} text 汉字、英文，或两者组成的一句
 * @param {{score?: number, threshold?: number, syllables?: string[]}} [opts]
 *        syllables 只在纯中文、且个数和字数一致时覆盖读音
 */
export function buildKeywordLine(text, opts = {}) {
  const word = normalizeWakeWord(text)
  const chars = [...word]
  const hanOnly = chars.length > 0 && chars.every((c) => HAN.test(c))
  const tokens = []
  if (hanOnly && opts.syllables && opts.syllables.length === chars.length) {
    for (const s of opts.syllables) tokens.push(...splitSyllable(s))
  } else {
    let i = 0
    while (i < chars.length) {
      if (chars[i] === ' ') {
        i++
        continue
      }
      if (HAN.test(chars[i])) {
        let han = ''
        while (i < chars.length && HAN.test(chars[i])) {
          han += chars[i]
          i++
        }
        for (const s of toSyllables(han)) tokens.push(...splitSyllable(s))
        continue
      }
      if (LAT.test(chars[i])) {
        while (i < chars.length && LAT.test(chars[i])) {
          tokens.push(chars[i].toUpperCase())
          i++
        }
        continue
      }
      i++
    }
  }
  let line = tokens.join(' ')
  if (opts.score) line += ` :${opts.score}`
  if (opts.threshold) line += ` #${opts.threshold}`
  return `${line} @${word}`
}

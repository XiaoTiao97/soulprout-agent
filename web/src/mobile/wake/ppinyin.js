/**
 * 把中文唤醒词转成 sherpa-onnx KWS 中文模型使用的「声母 + 韵母(带声调)」token。
 *
 * 规则与官方 `sherpa-onnx-cli text2token --tokens-type ppinyin` 保持一致
 * （pypinyin 的 to_initials / to_finals_tone，strict=False，y/w 当声母）。
 * 例：小章同学 -> "x iǎo zh āng t óng x ué @小章同学"
 *
 * 关键点：模型匹配的是「声音」，所以 小张 / 小章 会得到完全相同的 token。
 */
import { pinyin } from 'pinyin-pro'

// 双字母声母必须排在前面，保证 zh/ch/sh 优先匹配
const INITIALS = ['zh', 'ch', 'sh', 'b', 'p', 'm', 'f', 'd', 't', 'n', 'l', 'g', 'k', 'h', 'j', 'q', 'x', 'r', 'z', 'c', 's', 'y', 'w']

const CJK_ONLY = /^[\u4e00-\u9fff]+$/

/** 单个带调拼音音节 -> [声母?, 韵母] */
export function splitSyllable(syllable) {
  for (const ini of INITIALS) {
    if (syllable.startsWith(ini) && syllable.length > ini.length) {
      return [ini, syllable.slice(ini.length)]
    }
  }
  return [syllable]
}

/**
 * 校验唤醒词是否可用，返回 { ok, message }。
 * 这里只做「字符层面」的检查；音节是否在模型词表里由原生层再校验一次。
 */
export function validateWakeWord(text) {
  const t = (text || '').trim()
  if (!t) return { ok: false, message: '请输入唤醒词' }
  if (!CJK_ONLY.test(t)) return { ok: false, message: '唤醒词只能包含汉字（不要有空格、字母、数字、标点）' }
  if (t.length < 2) return { ok: false, message: '唤醒词至少 2 个字' }
  if (t.length > 8) return { ok: false, message: '唤醒词最多 8 个字' }
  return { ok: true, message: '' }
}

/**
 * 返回每个字的拼音（带声调符号），用于界面展示和多音字确认。
 * @returns {string[]} 例：['xiǎo','zhāng']
 */
export function toSyllables(text) {
  return pinyin(text.trim(), { toneType: 'symbol', type: 'array', v: false })
}

/**
 * 生成一行 KWS 关键词：`x iǎo zh āng @小章`，可附加 :score / #threshold。
 * @param {string} text 汉字唤醒词
 * @param {{score?: number, threshold?: number, syllables?: string[]}} [opts]
 *        syllables 可由界面覆盖（用户手动选读音时）
 */
export function buildKeywordLine(text, opts = {}) {
  const word = text.trim()
  const syllables = opts.syllables && opts.syllables.length ? opts.syllables : toSyllables(word)
  const tokens = []
  for (const s of syllables) tokens.push(...splitSyllable(s))
  let line = tokens.join(' ')
  if (opts.score) line += ` :${opts.score}`
  if (opts.threshold) line += ` #${opts.threshold}`
  return `${line} @${word}`
}

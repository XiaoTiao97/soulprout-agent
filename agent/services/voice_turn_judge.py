"""待命语音「这轮话说完了吗」的语义判断。

手机端原生层在 ASR 静默断句（默认 1300ms）后调用，由一个轻量大模型从语义层判断：
用户是真的说完了，还是只是中间停顿 / 思考 / 话说到一半。

返回固定结构 ``{"user_finished": bool}``。任何异常都按「说完了」处理（返回 None 由调用方兜底），
保证不会因为判断服务故障而让对话卡住。
"""

from __future__ import annotations

import json
import logging
import re
from typing import Optional

from openai import AsyncOpenAI

from agent.core.config import Config

logger = logging.getLogger(__name__)

config = Config()

# 模型来源与名称由 .env 的 VOICE_JUDGE_MODEL_SOURCE / VOICE_JUDGE_MODEL 指定（见 Config）
# 判断必须快：超过这个时间视为失败，由调用方按「说完了」处理
JUDGE_TIMEOUT_S = 4.0
# 防止异常长文本拖慢判断
MAX_TEXT_CHARS = 1200

_SYSTEM_PROMPT = """你是语音助手的「话轮结束判断器」。用户正在用语音和助手对话，语音识别在检测到约 1.3 秒静音后把已说内容交给你。
你要从语义层判断：用户这一轮话是已经说完了，还是只是中间停顿、思考、斟酌措辞、话说到一半。

输入包含两部分：
- total_voice_text：这一个对话窗口内用户按时间顺序说过的全部内容（可能包含已经发给助手的前半部分）。
- current_voice_text：其中尚未发给助手的最新内容，是你要重点判断的部分。

判断规则：
1. user_finished = true：当前内容已经表达了一个完整的意思（完整的问题、请求、指令、陈述，或「好的」「不用了」「谢谢」这类完整的简短回应）。
2. user_finished = false：明显还没说完，例如：
   - 句子停在连词、介词、助词、量词或半截结构上（「我想问一下那个」「如果明天下雨的话」「帮我查一下关于」「还有就是」）；
   - 只有语气词、口头禅或思考声（「嗯」「呃」「那个」「让我想想」「就是说」）；
   - 前面铺垫了背景或条件，但真正的问题 / 请求还没出现；
   - 与 total_voice_text 前文合起来看，意思明显尚未闭合。
3. 语音识别可能有错字、没有标点，不要因为措辞别扭或缺标点就判为没说完。
4. 拿不准时判为 true：误判为没说完会让用户干等，而误判为说完用户还可以继续补充。

只输出 JSON，不要任何解释：{"user_finished": true} 或 {"user_finished": false}"""

_RESPONSE_FORMAT_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "turn_judge",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {"user_finished": {"type": "boolean"}},
            "required": ["user_finished"],
            "additionalProperties": False,
        },
    },
}

_client: Optional[AsyncOpenAI] = None
# json_schema 不被支持时降级到 json_object，之后不再重复尝试
_use_json_schema = True


def _model_name() -> str:
    # 判断阶段固定关闭思考，兼容误填的 -thinking 后缀
    return config.voice_judge_model.removesuffix("-thinking")


def judge_configured() -> bool:
    source = config.voice_judge_model_source
    key = (getattr(config, f"{source}_key", None) or "").strip()
    return bool(key) and key != "sk-xxx" and bool(getattr(config, f"{source}_base_url", None)) and bool(_model_name())


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        # 复用连接，省掉每次判断的握手耗时
        source = config.voice_judge_model_source
        _client = AsyncOpenAI(
            api_key=getattr(config, f"{source}_key"),
            base_url=getattr(config, f"{source}_base_url"),
            timeout=JUDGE_TIMEOUT_S,
            max_retries=0,
        )
    return _client


def _clip(text: str) -> str:
    text = (text or "").strip()
    if len(text) <= MAX_TEXT_CHARS:
        return text
    return text[-MAX_TEXT_CHARS:]


def _parse(raw: str) -> Optional[bool]:
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{.*?\}", raw, re.S)
        if not m:
            return None
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
    if not isinstance(data, dict):
        return None
    value = data.get("user_finished")
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.lower() in ("true", "false"):
        return value.lower() == "true"
    return None


async def judge_user_finished(total_voice_text: str, current_voice_text: str) -> Optional[bool]:
    """True=说完了，False=还没说完，None=判断失败（调用方应按说完了处理）。"""
    global _use_json_schema
    if not judge_configured():
        return None
    total = _clip(total_voice_text)
    current = _clip(current_voice_text) or total
    if not current:
        return None

    user_prompt = f"total_voice_text：{total or current}\ncurrent_voice_text：{current}"
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
    client = _get_client()
    base = dict(
        model=_model_name(),
        messages=messages,
        temperature=0,
        max_tokens=32,
        extra_body={"thinking": {"type": "disabled"}},
    )
    try:
        if _use_json_schema:
            try:
                completion = await client.chat.completions.create(response_format=_RESPONSE_FORMAT_SCHEMA, **base)
            except Exception as e:
                status = getattr(e, "status_code", None)
                if status == 400:
                    logger.warning("[voice/judge] 模型不支持 json_schema，降级为 json_object: %s", e)
                    _use_json_schema = False
                    completion = await client.chat.completions.create(response_format={"type": "json_object"}, **base)
                else:
                    raise
        else:
            completion = await client.chat.completions.create(response_format={"type": "json_object"}, **base)
        result = _parse(completion.choices[0].message.content or "")
        logger.info("[voice/judge] finished=%s current=%r", result, current[-60:])
        return result
    except Exception as e:
        logger.warning("[voice/judge] 判断失败: %s", e)
        return None

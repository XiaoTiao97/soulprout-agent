"""阿里云 NLS 一句话识别 REST：/stream/v1/asr（内存处理，不落盘）。"""

import json
import time

import aiohttp

from agent.core.config import Config

config = Config()

NLS_META_HOST = "nls-meta.cn-shanghai.aliyuncs.com"
NLS_GATEWAY_HOST = "nls-gateway-cn-shanghai.aliyuncs.com"
SUCCESS_STATUS = 20000000
NLS_SAMPLE_RATE = 16000
ASR_MAX_DURATION_SEC = 60

_token: str | None = None
_token_expire_at: float = 0


def _token_error_hint(data: dict) -> str:
    code = data.get("ErrCode")
    if code == 40020503:
        return (
            "当前 AccessKey 没有「智能语音交互(NLS)」权限（错误码 40020503）。"
            "请在 RAM 控制台为该 AK 绑定系统策略 AliyunNLSFullAccess，"
            "并确认主账号已开通智能语音交互、项目里已启用「一句话识别」且 AppKey 正确。"
            "AK/SK 仅用于换取 Token；真正识别接口是 /stream/v1/asr，并未调错服务。"
        )
    return str(data.get("ErrMsg") or data)


def get_nls_token() -> str:
    """换取 X-NLS-Token，供一句话识别 REST 使用。"""
    global _token, _token_expire_at
    now = time.time()
    if _token and now < _token_expire_at - 300:
        return _token

    manual = (config.nls_token or "").strip()
    if manual:
        return manual

    ak = config.aliyun_access_key_id
    sk = config.aliyun_access_key_secret
    if not ak or not sk:
        raise RuntimeError("未配置 ALIYUN_ACCESS_KEY_ID / ALIYUN_ACCESS_KEY_SECRET")

    try:
        from aliyunsdkcore.client import AcsClient
        from aliyunsdkcore.request import CommonRequest
    except ImportError as e:
        raise RuntimeError("请安装依赖: pip install aliyun-python-sdk-core") from e

    client = AcsClient(ak, sk, "cn-shanghai")
    request = CommonRequest()
    request.set_method("POST")
    request.set_domain(NLS_META_HOST)
    request.set_version("2019-02-28")
    request.set_action_name("CreateToken")

    try:
        raw = client.do_action_with_exception(request)
    except Exception as e:
        raise RuntimeError(f"调用 NLS CreateToken 失败: {e}") from e

    data = json.loads(raw)
    if data.get("ErrCode"):
        raise RuntimeError(f"获取 NLS Token 失败: {_token_error_hint(data)}")

    token_info = data.get("Token") or {}
    token_id = token_info.get("Id")
    expire_time = token_info.get("ExpireTime")
    if not token_id:
        raise RuntimeError(f"获取 NLS Token 失败: {data}")

    _token = token_id
    _token_expire_at = float(expire_time) if expire_time else now + 3600
    return _token


def _wav_duration_sec(audio: bytes) -> float:
    if len(audio) < 44 or audio[:4] != b"RIFF":
        return 0
    byte_rate = int.from_bytes(audio[28:32], "little")
    data_size = int.from_bytes(audio[40:44], "little")
    if byte_rate <= 0:
        return 0
    return data_size / byte_rate


async def transcribe(audio: bytes, audio_format: str = "wav") -> str:
    appkey = config.nls_app_key
    if not appkey:
        raise RuntimeError("未配置 NLS_APP_KEY")

    if len(audio) > 3 * 1024 * 1024:
        raise ValueError("音频过大（超过 3MB）")

    duration = _wav_duration_sec(audio)
    if duration > 0 and duration > ASR_MAX_DURATION_SEC:
        raise ValueError(f"音频时长超过 {ASR_MAX_DURATION_SEC} 秒")

    token = get_nls_token()
    url = (
        f"https://{NLS_GATEWAY_HOST}/stream/v1/asr"
        f"?appkey={appkey}"
        f"&format={audio_format}"
        f"&sample_rate={NLS_SAMPLE_RATE}"
        "&enable_punctuation_prediction=true"
        "&enable_inverse_text_normalization=true"
    )
    headers = {
        "X-NLS-Token": token,
        "Content-Type": "application/octet-stream",
        "Content-Length": str(len(audio)),
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(url, data=audio, headers=headers, timeout=aiohttp.ClientTimeout(total=60)) as resp:
            raw = await resp.read()
    try:
        body = json.loads(raw)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"识别响应解析失败: {raw[:200]!r}") from e

    if body.get("status") != SUCCESS_STATUS:
        raise RuntimeError(body.get("message") or body.get("status_text") or str(body))
    result = (body.get("result") or "").strip()
    if not result:
        raise RuntimeError("未识别到有效文本")
    return result

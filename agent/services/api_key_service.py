"""用户自定义 API Key 与指定模型配置服务。

核心职责：
1. 独立封装存 Key、取 Key、删 Key 与模型偏好配置逻辑；
2. 内存中带容量上限与 TTL（10 分钟）的 LRU 缓存，避免每次请求重复解密，也防止无界堆积明文；
3. 删除或修改 Key 时立即失效内存缓存；
4. 提供 `apply_user_model_settings(config, user_id)`，在用户开启自定义 Key 时，将 `config` 上的
   soulprout / pro / flash 及其派生的 abstract / plan / compact / collapse 模型与对应供应商 Key
   无缝替换为用户自己的配置。
"""

from __future__ import annotations

import logging
import os
import re
import time
from collections import OrderedDict
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

from beanie.operators import Eq

from agent.core.config import Config
from agent.database.models.user import UserInfo
from agent.database.models.user_api_key import UserApiKey
from agent.utils.crypto_keys import (
    EnvelopePayload,
    decrypt_secret,
    encrypt_secret,
    mask_api_key,
)

logger = logging.getLogger(__name__)

# 内存缓存配置：默认最多缓存 2048 条 (user_id, model_source)，默认 TTL 600 秒（10 分钟），可通过环境变量覆盖
_CACHE_MAX_SIZE = int(os.getenv("API_KEY_CACHE_MAX_SIZE", "2048"))
_CACHE_TTL_SECONDS = float(os.getenv("API_KEY_CACHE_TTL_SECONDS", "600"))
_KEY_CACHE: "OrderedDict[Tuple[str, str], Tuple[str, float]]" = OrderedDict()

# 允许的 API Key 形状：12 ~ 256 个可见 ASCII 字符（不含空白），兼容 sk-、智谱 id.secret、方舟 UUID、千帆 bce-v3 等
_VALID_KEY_RE = re.compile(r"^[\x21-\x7E]{12,256}$")


def _cache_get(user_id: str, model_source: str) -> Optional[str]:
    cache_key = (str(user_id), str(model_source).lower())
    entry = _KEY_CACHE.get(cache_key)
    if not entry:
        return None
    secret, expire_at = entry
    if time.monotonic() > expire_at:
        _KEY_CACHE.pop(cache_key, None)
        return None
    _KEY_CACHE.move_to_end(cache_key)
    return secret


def _cache_put(user_id: str, model_source: str, secret: str) -> None:
    cache_key = (str(user_id), str(model_source).lower())
    _KEY_CACHE[cache_key] = (secret, time.monotonic() + _CACHE_TTL_SECONDS)
    _KEY_CACHE.move_to_end(cache_key)
    while len(_KEY_CACHE) > _CACHE_MAX_SIZE:
        _KEY_CACHE.popitem(last=False)


def _cache_evict(user_id: str, model_source: Optional[str] = None) -> None:
    uid = str(user_id)
    if model_source is not None:
        _KEY_CACHE.pop((uid, str(model_source).lower()), None)
        return
    to_remove = [k for k in _KEY_CACHE if k[0] == uid]
    for k in to_remove:
        _KEY_CACHE.pop(k, None)


def validate_api_key_shape(raw_key: str) -> Tuple[bool, str]:
    """服务端形状校验：过滤空串、占位符、空白字符与非法长度。"""
    key = (raw_key or "").strip()
    if not key:
        return False, "API Key 不能为空"
    if key.lower() in ("sk-xxx", "xxx", "your_api_key", "null", "undefined"):
        return False, "不能填写示例占位符，请输入真实的 API Key"
    if not _VALID_KEY_RE.match(key):
        return False, "API Key 格式不合法（长度需在 12~256 字符之间，且不含空格或中文字符）"
    return True, key


def get_catalog_providers(config: Optional[Config] = None) -> List[Dict[str, Any]]:
    """返回 .model.json 中定义的全部平台及模型清单（不论官方是否填写了默认 Key）。"""
    cfg = config or Config()
    catalog: List[Dict[str, Any]] = []
    for item in cfg.models_info_list or []:
        source = item.get("model_source")
        if not source:
            continue
        models = [m.get("name") for m in (item.get("models") or []) if m.get("name")]
        catalog.append({
            "model_source": source,
            "display_name": item.get("display_name") or source,
            "models": models,
        })
    return catalog


def is_valid_source_and_model(
    model_source: str,
    model_name: str,
    catalog: List[Dict[str, Any]],
) -> bool:
    for p in catalog:
        if p["model_source"] == model_source:
            return model_name in p["models"]
    return False


async def save_user_api_key(
    user_id: str,
    model_source: str,
    raw_api_key: str,
    config: Optional[Config] = None,
) -> Dict[str, Any]:
    """加密并保存用户某个平台的 API Key（存在则覆盖更新），绝不返回明文。"""
    uid = str(user_id).strip()
    source = (model_source or "").strip().lower()
    catalog = get_catalog_providers(config)
    valid_sources = {p["model_source"] for p in catalog}
    if source not in valid_sources:
        raise ValueError(f"不支持的模型平台：{model_source}")

    ok, cleaned_or_err = validate_api_key_shape(raw_api_key)
    if not ok:
        raise ValueError(cleaned_or_err)
    secret = cleaned_or_err

    envelope = encrypt_secret(secret, uid, source)
    hint = mask_api_key(secret)
    now = datetime.utcnow()

    existing = await UserApiKey.find_one(
        Eq(UserApiKey.user_id, uid),
        Eq(UserApiKey.model_source, source),
    )
    if existing:
        existing.key_hint = hint
        existing.kek_version = envelope.kek_version
        existing.dek_iv = envelope.dek_iv
        existing.dek_wrapped = envelope.dek_wrapped
        existing.key_iv = envelope.key_iv
        existing.key_cipher = envelope.key_cipher
        existing.updated_at = now
        await existing.save()
    else:
        doc = UserApiKey(
            user_id=uid,
            model_source=source,
            key_hint=hint,
            kek_version=envelope.kek_version,
            dek_iv=envelope.dek_iv,
            dek_wrapped=envelope.dek_wrapped,
            key_iv=envelope.key_iv,
            key_cipher=envelope.key_cipher,
            created_at=now,
            updated_at=now,
        )
        await doc.insert()

    # 立即更新缓存
    _cache_put(uid, source, secret)
    return {
        "model_source": source,
        "configured": True,
        "key_hint": hint,
        "updated_at": now.isoformat(),
    }


async def delete_user_api_key(user: UserInfo, model_source: str) -> Dict[str, Any]:
    """删除用户某平台的 API Key：立即清库 + 清内存缓存；若删除后无可用 Key 则自动关闭自定义模式。"""
    uid = str(user.user_id).strip()
    source = (model_source or "").strip().lower()

    # 立即清理内存缓存
    _cache_evict(uid, source)

    existing = await UserApiKey.find_one(
        Eq(UserApiKey.user_id, uid),
        Eq(UserApiKey.model_source, source),
    )
    if existing:
        await existing.delete()

    remaining_docs = await UserApiKey.find(Eq(UserApiKey.user_id, uid)).to_list()
    remaining_sources = {d.model_source for d in remaining_docs}

    auto_disabled = False
    user_changed = False

    # 如果被删的 source 正在被 3 个指定模型使用，清理对应槽位；若原本处于启用态，自动切回未启用或要求重选
    if user.custom_soulprout_source == source:
        user.custom_soulprout_source = None
        user.custom_soulprout_model = None
        user_changed = True
    if user.custom_pro_source == source:
        user.custom_pro_source = None
        user.custom_pro_model = None
        user_changed = True
    if user.custom_flash_source == source:
        user.custom_flash_source = None
        user.custom_flash_model = None
        user_changed = True

    if user.use_custom_key:
        if (
            not remaining_sources
            or not user.custom_soulprout_source
            or not user.custom_pro_source
            or not user.custom_flash_source
        ):
            user.use_custom_key = False
            auto_disabled = True
            user_changed = True

    if user_changed:
        await user.save()

    return {
        "deleted": True,
        "model_source": source,
        "auto_disabled": auto_disabled,
        "use_custom_key": bool(user.use_custom_key),
    }


async def get_user_api_key(user_id: str, model_source: str) -> Optional[str]:
    """获取并解密用户指定平台的 API Key（优先命中内存 TTL 缓存）。"""
    if not user_id or not model_source:
        return None
    uid = str(user_id).strip()
    source = str(model_source).strip().lower().removesuffix("_no_stream")

    cached = _cache_get(uid, source)
    if cached is not None:
        return cached

    doc = await UserApiKey.find_one(
        Eq(UserApiKey.user_id, uid),
        Eq(UserApiKey.model_source, source),
    )
    if not doc:
        return None

    try:
        payload = EnvelopePayload(
            kek_version=doc.kek_version or 1,
            dek_iv=doc.dek_iv,
            dek_wrapped=doc.dek_wrapped,
            key_iv=doc.key_iv,
            key_cipher=doc.key_cipher,
        )
        plain = decrypt_secret(payload, uid, source)
        _cache_put(uid, source, plain)
        return plain
    except Exception:
        logger.exception("[api_key_service] 解密用户 API Key 失败 user=%s source=%s", uid, source)
        return None


async def get_user_decrypted_keys_map(user_id: str) -> Dict[str, str]:
    """获取该用户已保存的所有平台解密 Key 映射 {model_source: plaintext_key}。"""
    uid = str(user_id or "").strip()
    if not uid:
        return {}
    docs = await UserApiKey.find(Eq(UserApiKey.user_id, uid)).to_list()
    result: Dict[str, str] = {}
    for doc in docs:
        source = doc.model_source
        cached = _cache_get(uid, source)
        if cached is not None:
            result[source] = cached
            continue
        try:
            payload = EnvelopePayload(
                kek_version=doc.kek_version or 1,
                dek_iv=doc.dek_iv,
                dek_wrapped=doc.dek_wrapped,
                key_iv=doc.key_iv,
                key_cipher=doc.key_cipher,
            )
            plain = decrypt_secret(payload, uid, source)
            _cache_put(uid, source, plain)
            result[source] = plain
        except Exception:
            logger.exception("[api_key_service] 解密用户 API Key 失败 user=%s source=%s", uid, source)
    return result


async def get_user_api_key_settings(
    user: UserInfo,
    config: Optional[Config] = None,
) -> Dict[str, Any]:
    """返回供前端设置界面渲染的脱敏配置信息（绝不包含任何明文 Key）。"""
    catalog = get_catalog_providers(config)
    docs = await UserApiKey.find(Eq(UserApiKey.user_id, user.user_id)).to_list()
    saved_map = {
        d.model_source: {
            "key_hint": d.key_hint,
            "updated_at": d.updated_at.isoformat() if d.updated_at else "",
        }
        for d in docs
    }

    providers = []
    for item in catalog:
        src = item["model_source"]
        saved = saved_map.get(src)
        providers.append({
            "model_source": src,
            "display_name": item["display_name"],
            "models": item["models"],
            "configured": bool(saved),
            "key_hint": saved["key_hint"] if saved else "",
            "updated_at": saved["updated_at"] if saved else "",
        })

    return {
        "success": True,
        "use_custom_key": bool(getattr(user, "use_custom_key", False)),
        "custom_soulprout_source": getattr(user, "custom_soulprout_source", None) or "",
        "custom_soulprout_model": getattr(user, "custom_soulprout_model", None) or "",
        "custom_pro_source": getattr(user, "custom_pro_source", None) or "",
        "custom_pro_model": getattr(user, "custom_pro_model", None) or "",
        "custom_flash_source": getattr(user, "custom_flash_source", None) or "",
        "custom_flash_model": getattr(user, "custom_flash_model", None) or "",
        "providers": providers,
    }


async def update_user_model_preferences(
    user: UserInfo,
    *,
    use_custom_key: bool,
    custom_soulprout_source: Optional[str],
    custom_soulprout_model: Optional[str],
    custom_pro_source: Optional[str],
    custom_pro_model: Optional[str],
    custom_flash_source: Optional[str],
    custom_flash_model: Optional[str],
    config: Optional[Config] = None,
) -> Dict[str, Any]:
    """保存用户的启用开关与 soulprout / pro / flash 三个指定模型配置。"""
    catalog = get_catalog_providers(config)
    docs = await UserApiKey.find(Eq(UserApiKey.user_id, user.user_id)).to_list()
    configured_sources: Set[str] = {d.model_source for d in docs}

    sp_src = (custom_soulprout_source or "").strip().lower() or None
    sp_mod = (custom_soulprout_model or "").strip() or None
    pro_src = (custom_pro_source or "").strip().lower() or None
    pro_mod = (custom_pro_model or "").strip() or None
    fl_src = (custom_flash_source or "").strip().lower() or None
    fl_mod = (custom_flash_model or "").strip() or None

    if use_custom_key:
        if not configured_sources:
            raise ValueError("启用自定义 API Key 前，请先至少填入并保存一个平台的 API Key")
        if not (sp_src and sp_mod and pro_src and pro_mod and fl_src and fl_mod):
            raise ValueError("启用自定义 API Key 时，必须完整指定灵芽（Soulprout）模型、Pro 模型和 Flash 模型")
        for label, src, mod in (
            ("灵芽（Soulprout）模型", sp_src, sp_mod),
            ("Pro 模型", pro_src, pro_mod),
            ("Flash 模型", fl_src, fl_mod),
        ):
            if src not in configured_sources:
                raise ValueError(f"{label}所选平台（{src}）尚未配置 API Key")
            if not is_valid_source_and_model(src, mod, catalog):
                raise ValueError(f"{label}（{src} / {mod}）不在系统支持的模型列表中")
    else:
        # 未开启时，若填写了部分模型也做合法性保存，方便下次直接开启
        for src, mod in ((sp_src, sp_mod), (pro_src, pro_mod), (fl_src, fl_mod)):
            if src and mod and not is_valid_source_and_model(src, mod, catalog):
                raise ValueError(f"模型（{src} / {mod}）不在系统支持的模型列表中")

    user.use_custom_key = bool(use_custom_key)
    user.custom_soulprout_source = sp_src
    user.custom_soulprout_model = sp_mod
    user.custom_pro_source = pro_src
    user.custom_pro_model = pro_mod
    user.custom_flash_source = fl_src
    user.custom_flash_model = fl_mod
    await user.save()

    return await get_user_api_key_settings(user, config)


async def get_effective_models_for_user(
    user: Optional[UserInfo],
    config: Optional[Config] = None,
) -> Dict[str, List[str]]:
    """
    供 `/message/models` 调用：
    - 若用户已登录且开启了 `use_custom_key`，仅返回该用户已配置 API Key 的平台及其模型列表；
    - 否则返回系统在 `.model.json` 中已配置默认 Key 的模型列表。
    """
    cfg = config or Config()
    if user and getattr(user, "use_custom_key", False):
        docs = await UserApiKey.find(Eq(UserApiKey.user_id, user.user_id)).to_list()
        configured_sources = {d.model_source for d in docs}
        if configured_sources:
            models_dict: Dict[str, List[str]] = {}
            for models_info in cfg.models_info_list:
                src = models_info.get("model_source")
                if src in configured_sources:
                    models_dict[src] = [
                        model.get("name") for model in (models_info.get("models") or [])
                    ]
            return models_dict

    models_dict = {}
    for models_info in cfg.models_info_list:
        if models_info.get("model_use") is True:
            models_dict[models_info.get("model_source")] = [
                model.get("name") for model in (models_info.get("models") or [])
            ]
    return models_dict


async def apply_user_model_settings(config: Config, user_id: Optional[str]) -> bool:
    """
    在对话运行前，根据 user_id 检查用户是否开启了自定义 API Key：
    - 若未开启：保留 config 中的官方默认模型与官方 Key（但保留 system_glm_key 供知识库解析使用）；
    - 若已开启：
      1. 将该用户配置的所有平台 Key 覆盖到 `config.<source>_key`，未配置的平台置为空串（严禁混用官方 Key）；
      2. 将 `soulprout` / `pro` / `flash` 及派生的 `abstract` / `skills_abstract` / `plan` / `compact` / `collapse`
         全部切换为用户指定的模型；
      3. 记录 `config.user_custom_key_enabled = True` 与 `config.user_configured_sources`。
    """
    # 始终保留一份平台官方 glm_key 供知识库解析（agents_box.py）使用
    config.system_glm_key = getattr(config, "glm_key", None)
    config.user_custom_key_enabled = False
    config.user_configured_sources = set()

    uid = str(user_id or "").strip()
    if not uid:
        return False

    user = await UserInfo.find_one(Eq(UserInfo.user_id, uid))
    if not user or not getattr(user, "use_custom_key", False):
        return False

    user_keys = await get_user_decrypted_keys_map(uid)
    if not user_keys:
        logger.warning("[api_key_service] 用户 %s 开启了 use_custom_key 但无有效 Key，回退官方配置", uid)
        return False

    config.user_custom_key_enabled = True
    config.user_configured_sources = set(user_keys.keys())

    # 覆盖各平台 Key：用户配了的用用户的，没配的清空（禁止在启用自定义模式下回退消耗官方 Key）
    for item in config.models_info_list or []:
        src = item.get("model_source")
        if not src:
            continue
        u_key = user_keys.get(src, "")
        setattr(config, f"{src}_key", u_key)
        item["model_use"] = bool(u_key)

    # 替换 soulprout / pro / flash 三个基准模型
    if user.custom_soulprout_source and user.custom_soulprout_model:
        config.soulprout_model_source = user.custom_soulprout_source
        config.soulprout_model = user.custom_soulprout_model

    if user.custom_pro_source and user.custom_pro_model:
        config.pro_model_source = user.custom_pro_source
        config.pro_model = user.custom_pro_model

    if user.custom_flash_source and user.custom_flash_model:
        config.flash_model_source = user.custom_flash_source
        config.flash_model = user.custom_flash_model

    # 同步所有派生模型（会话摘要、上下文压缩/折叠、行动蓝图）
    config.abstract_model_source = config.flash_model_source
    config.abstract_model = config.flash_model
    config.skills_abstract_model_source = config.flash_model_source
    config.skills_abstract_model = config.flash_model
    config.plan_model_source = config.pro_model_source
    config.plan_model = config.pro_model
    config.compact_model_source = config.flash_model_source
    config.compact_model = config.flash_model
    config.collapse_model_source = config.flash_model_source
    config.collapse_model = config.flash_model

    return True

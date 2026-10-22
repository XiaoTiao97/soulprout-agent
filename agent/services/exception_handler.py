"""运行时异常处理。请求被模型或历史数据卡住时，在这里修复并重试。后续同类异常也放在这个模块。"""

import base64
import re

from agent.tool.tools import SoulproutToolFunction

IMAGE_SKIP_TEXT = "[图片已跳过：当前模型只接受 png、jpeg、gif、webp，该图片格式无效或不受支持]"
ALLOWED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp"}


def data_url_media_type(url: str):
    """校验 data URL 的真实文件头。合法返回 media type，非法返回 None，非 data URL 返回空串（保持原样）。"""
    if not isinstance(url, str):
        return None
    if not url.startswith("data:"):
        return ""
    match = re.match(r"^data:[^,]*,(.*)$", url, re.DOTALL)
    if not match:
        return None
    try:
        raw = base64.b64decode(match.group(1), validate=False)
    except Exception:
        return None
    return SoulproutToolFunction._image_media_type(raw)


def content_has_image(content) -> bool:
    if not isinstance(content, list):
        return False
    return any(isinstance(part, dict) and part.get("type") in ("image_url", "image") for part in content)


def is_accepted_image(media_type, encoded) -> bool:
    """文件头与声明的类型都必须是 png / jpeg / gif / webp。"""
    if media_type not in ALLOWED_IMAGE_TYPES or not encoded:
        return False
    try:
        raw = base64.b64decode(encoded, validate=False)
    except Exception:
        return False
    return SoulproutToolFunction._image_media_type(raw) == media_type


def build_image_user_content(text, encoded, media_type):
    """构造可写入历史的图片消息。格式不合法时返回 None，不落库。"""
    if not is_accepted_image(media_type, encoded):
        print(f"[image] 跳过不受支持的图片，未写入历史：{media_type}")
        return None
    return [
        {"type": "text", "text": text},
        {"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{encoded}"}},
    ]


def rewrite_image_content(content, drop_invalid_only: bool):
    """把不受支持的图片部分换成文字。drop_invalid_only 为 False 时去掉全部图片（模型已拒绝时使用）。"""
    if not isinstance(content, list):
        return content, False
    changed = False
    parts = []
    for part in content:
        if not isinstance(part, dict) or part.get("type") not in ("image_url", "image"):
            parts.append(part)
            continue
        image_url = part.get("image_url")
        url = image_url.get("url") if isinstance(image_url, dict) else image_url
        media_type = data_url_media_type(url) if isinstance(url, str) else None
        if drop_invalid_only and media_type in ALLOWED_IMAGE_TYPES:
            normalized = url
            if isinstance(url, str) and url.startswith("data:") and not url.startswith(f"data:{media_type}"):
                payload = url.split(",", 1)[1]
                normalized = f"data:{media_type};base64,{payload}"
                changed = True
            parts.append({"type": "image_url", "image_url": {"url": normalized}})
            continue
        if drop_invalid_only and media_type == "":
            parts.append(part)
            continue
        parts.append({"type": "text", "text": IMAGE_SKIP_TEXT})
        changed = True
    if not changed:
        return content, False
    if not parts:
        return IMAGE_SKIP_TEXT, True
    return parts, True


async def sanitize_stored_images(history) -> None:
    """回放前清掉历史里的非法图片，并写回数据库，避免同一张坏图每次请求都 400。"""
    for item in history:
        new_content, changed = rewrite_image_content(item.content, drop_invalid_only=True)
        if not changed:
            continue
        item.content = new_content
        try:
            await item.save()
            print(f"[image] 已替换历史中的非法图片 message_id={item.id}")
        except Exception as e:
            print(f"[image] 写回非法图片消息失败 message_id={getattr(item, 'id', None)}: {e}")


def request_message_ids(history_ids, leading_synthetic: int):
    """请求数组前部是 system（以及子智能体插入的摘要），没有数据库 id。"""
    return [None] * leading_synthetic + list(history_ids or [])


async def drop_rejected_image(messages, error, request_ids, load_history) -> bool:
    """模型以 unsupported image 拒绝时，按报错下标去掉该条消息里的图片并写回。"""
    text = str(error)
    if "unsupported image" not in text.lower():
        return False
    found = re.search(r"messages\[(\d+)\]", text)
    if found:
        indexes = [int(found.group(1))]
    else:
        indexes = [i for i, message in enumerate(messages) if content_has_image(message.get("content"))]
    request_ids = request_ids or []
    changed = False
    for index in indexes:
        if index < 0 or index >= len(messages):
            continue
        new_content, did = rewrite_image_content(messages[index].get("content"), drop_invalid_only=False)
        if not did:
            continue
        messages[index]["content"] = new_content
        changed = True
        message_id = request_ids[index] if index < len(request_ids) else None
        if not message_id:
            continue
        history = await load_history()
        for item in history:
            if item.id == message_id:
                item.content = new_content
                await item.save()
                print(f"[image] 模型拒绝图片，已从历史移除 message_id={message_id}")
                break
    return changed

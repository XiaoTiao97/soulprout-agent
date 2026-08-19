from datetime import datetime
from typing import Optional

from agent.database.models.user_channel_binding import UserChannelBinding

_GATEWAY_CHANNELS = {"weixin", "feishu", "wecom", "xiaoai", "rokid"}
CHANNEL_LABELS = {
    "weixin": "微信",
    "feishu": "飞书",
    "wecom": "企业微信",
    "xiaoai": "小爱音箱",
    "rokid": "Rokid",
    "web": "网页",
}


async def upsert_channel_binding(user_id: str, channel: str, chat_id: str) -> None:
    channel = (channel or "").strip().lower()
    chat_id = (chat_id or "").strip()
    user_id = str(user_id or "").strip()
    if not user_id or channel not in _GATEWAY_CHANNELS or not chat_id:
        return
    row = await UserChannelBinding.find_one(
        UserChannelBinding.user_id == user_id,
        UserChannelBinding.channel == channel,
    )
    now = datetime.utcnow()
    if row:
        row.chat_id = chat_id
        row.updated_at = now
        await row.save()
        return
    await UserChannelBinding(
        user_id=user_id,
        channel=channel,
        chat_id=chat_id,
        updated_at=now,
    ).insert()


async def get_channel_chat_id(user_id: str, channel: str) -> Optional[str]:
    channel = (channel or "").strip().lower()
    row = await UserChannelBinding.find_one(
        UserChannelBinding.user_id == str(user_id or "").strip(),
        UserChannelBinding.channel == channel,
    )
    return (row.chat_id if row else None) or None

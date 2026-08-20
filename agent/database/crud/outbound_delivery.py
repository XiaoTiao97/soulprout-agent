from datetime import datetime
from typing import List, Optional
from uuid import uuid4

from agent.database.models.outbound_delivery import OutboundDelivery


async def enqueue_delivery(
    *,
    user_id: str,
    channel: str,
    content: str,
    chat_id: Optional[str] = None,
    task_id: Optional[str] = None,
) -> OutboundDelivery:
    item = OutboundDelivery(
        delivery_id=uuid4().hex[:16],
        user_id=user_id,
        task_id=task_id,
        channel=channel,
        chat_id=(chat_id or "").strip() or None,
        content=content,
        status="pending",
    )
    await item.insert()
    return item


async def list_pending_deliveries(user_id: str, limit: int = 50) -> List[OutboundDelivery]:
    return await OutboundDelivery.find(
        OutboundDelivery.user_id == user_id,
        OutboundDelivery.status == "pending",
    ).sort("+create_at").limit(limit).to_list()


async def list_pending_for_users(user_ids: list[str], limit: int = 200) -> List[OutboundDelivery]:
    if not user_ids:
        return []
    return await OutboundDelivery.find(
        {"user_id": {"$in": list(user_ids)}, "status": "pending"}
    ).sort("+create_at").limit(limit).to_list()


async def mark_delivery_sent(delivery_id: str) -> Optional[OutboundDelivery]:
    item = await OutboundDelivery.find_one(OutboundDelivery.delivery_id == delivery_id)
    if not item:
        return None
    item.status = "sent"
    item.sent_at = datetime.utcnow()
    await item.save()
    return item


def delivery_to_payload(item: OutboundDelivery) -> dict:
    return {
        "type": "deliver",
        "delivery_id": item.delivery_id,
        "task_id": item.task_id,
        "channel": item.channel,
        "chat_id": item.chat_id,
        "content": item.content,
    }

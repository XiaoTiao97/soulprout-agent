from datetime import datetime, timedelta, timezone
from typing import Iterable, List, Optional, Union
from uuid import uuid4

from agent.database.models.scheduled_task import ScheduledTask

ALLOWED_CHANNELS = {"web", "weixin", "feishu", "wecom", "xiaoai", "rokid"}
ALLOWED_SCHEDULE_TYPES = {"once", "daily", "weekly"}
WEEKDAY_LABELS = {1: "周一", 2: "周二", 3: "周三", 4: "周四", 5: "周五", 6: "周六", 7: "周日"}
_WEEKDAY_ALIASES = {
    "1": 1, "2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "7": 7,
    "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "日": 7, "天": 7,
    "周一": 1, "周二": 2, "周三": 3, "周四": 4, "周五": 5, "周六": 6, "周日": 7, "周天": 7,
    "星期一": 1, "星期二": 2, "星期三": 3, "星期四": 4, "星期五": 5, "星期六": 6, "星期日": 7, "星期天": 7,
    "mon": 1, "tue": 2, "wed": 3, "thu": 4, "fri": 5, "sat": 6, "sun": 7,
    "monday": 1, "tuesday": 2, "wednesday": 3, "thursday": 4, "friday": 5, "saturday": 6, "sunday": 7,
}
_TZ_OFFSETS = {
    "asia/shanghai": 8,
    "asia/chongqing": 8,
    "prc": 8,
    "cst": 8,
    "utc": 0,
    "gmt": 0,
}


def _tz_offset_hours(tz_name: str) -> int:
    key = (tz_name or "Asia/Shanghai").strip().lower()
    if key in _TZ_OFFSETS:
        return _TZ_OFFSETS[key]
    return 8


def _parse_local_run_at(run_at_local: str, tz_name: str) -> datetime:
    raw = (run_at_local or "").strip()
    if not raw:
        raise ValueError("run_at 不能为空")
    tz = _local_tz(tz_name)
    iso = raw.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(iso.replace(" ", "T") if "T" not in iso[:19] and " " in iso else iso)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=tz)
        return parsed
    except ValueError:
        pass
    raw_naive = raw.replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            naive = datetime.strptime(raw_naive, fmt)
            return naive.replace(tzinfo=tz)
        except ValueError:
            continue
    if len(raw) <= 8:
        try:
            clock = datetime.strptime(raw, "%H:%M:%S" if raw.count(":") == 2 else "%H:%M")
        except ValueError:
            clock = None
        if clock is not None:
            now_local = datetime.now(tz)
            return now_local.replace(
                hour=clock.hour, minute=clock.minute, second=clock.second, microsecond=0
            )
    raise ValueError("run_at 格式无效，请使用 YYYY-MM-DD HH:MM，例如 2026-08-20 08:00")


def _naive_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _to_utc_naive(local_dt: datetime) -> datetime:
    if local_dt.tzinfo is None:
        local_dt = local_dt.replace(tzinfo=timezone.utc)
    return local_dt.astimezone(timezone.utc).replace(tzinfo=None)


def _fill_notify_text(title: str, instruction: str, notify_text: str) -> str:
    text = (notify_text or "").strip()
    if text:
        return text
    instruction = (instruction or "").strip()
    if instruction:
        return instruction
    return (title or "").strip()


def _local_tz(tz_name: str) -> timezone:
    return timezone(timedelta(hours=_tz_offset_hours(tz_name)))


def parse_weekdays(raw) -> List[int]:
    if raw is None or raw == "":
        return []
    items: Iterable
    if isinstance(raw, (list, tuple, set)):
        items = raw
    else:
        items = str(raw).replace("，", ",").replace("、", ",").split(",")
    result = []
    for item in items:
        if isinstance(item, bool):
            continue
        if isinstance(item, int):
            value = item
        else:
            token = str(item).strip().lower()
            if not token:
                continue
            token = token.replace("星期", "周")
            value = _WEEKDAY_ALIASES.get(token)
            if value is None and token.startswith("周"):
                value = _WEEKDAY_ALIASES.get(token[1:])
            if value is None:
                raise ValueError(f"无法识别的星期：{item}，请使用 1-7（1=周一，7=周日）")
        if value < 1 or value > 7:
            raise ValueError("weekdays 仅支持 1-7（1=周一，7=周日）")
        if value not in result:
            result.append(value)
    result.sort()
    return result


def _compute_weekly_next_run_at(
    run_at_local: str,
    tz_name: str,
    weekdays: List[int],
    now: datetime,
) -> datetime:
    if not weekdays:
        raise ValueError("schedule_type=weekly 时必须填写 weekdays（1-7，可多选，1=周一）")
    weekday_set = set(weekdays)
    local_dt = _parse_local_run_at(run_at_local, tz_name)
    tz = _local_tz(tz_name)
    now_local = now.replace(tzinfo=timezone.utc).astimezone(tz)
    start = now_local.replace(
        hour=local_dt.hour,
        minute=local_dt.minute,
        second=0,
        microsecond=0,
    )
    for offset in range(0, 8):
        candidate = start + timedelta(days=offset)
        if candidate.isoweekday() not in weekday_set:
            continue
        next_utc = _to_utc_naive(candidate)
        if next_utc > now:
            return next_utc
    raise ValueError("无法计算 weekly 的下一次执行时间，请检查 weekdays")


def compute_next_run_at(
    run_at_local: str,
    tz_name: str,
    schedule_type: str,
    weekdays: Optional[List[int]] = None,
    now: Optional[datetime] = None,
) -> datetime:
    now = now or datetime.utcnow()
    if schedule_type == "weekly":
        return _compute_weekly_next_run_at(run_at_local, tz_name, weekdays or [], now)
    local_dt = _parse_local_run_at(run_at_local, tz_name)
    next_utc = _to_utc_naive(local_dt)
    if schedule_type == "once":
        if next_utc <= now:
            raise ValueError("指定时间已过，请改用未来时间")
        return next_utc
    while next_utc <= now:
        local_dt = local_dt + timedelta(days=1)
        next_utc = _to_utc_naive(local_dt)
    return next_utc


def task_to_dict(task: ScheduledTask) -> dict:
    weekdays = list(task.weekdays or [])
    return {
        "task_id": task.task_id,
        "title": task.title,
        "instruction": task.instruction,
        "notify_text": task.notify_text,
        "timezone": task.timezone,
        "schedule_type": task.schedule_type,
        "weekdays": weekdays,
        "weekdays_label": ",".join(WEEKDAY_LABELS[d] for d in weekdays if d in WEEKDAY_LABELS),
        "run_at_local": task.run_at_local,
        "next_run_at": task.next_run_at.isoformat() + "Z" if task.next_run_at else None,
        "channel": task.channel,
        "chat_id": task.chat_id,
        "conversation_id": task.conversation_id,
        "enabled": task.enabled,
        "status": task.status,
        "last_run_at": task.last_run_at.isoformat() + "Z" if task.last_run_at else None,
        "last_error": task.last_error,
        "create_at": task.create_at.isoformat() + "Z" if task.create_at else None,
        "updated_at": task.updated_at.isoformat() + "Z" if task.updated_at else None,
    }


def _normalize_weekdays_for_type(schedule_type: str, weekdays: Optional[List[int]]) -> List[int]:
    if schedule_type == "weekly":
        parsed = parse_weekdays(weekdays)
        if not parsed:
            raise ValueError("schedule_type=weekly 时必须填写 weekdays，例如 [1,3,5] 表示周一三五")
        return parsed
    return []


async def create_scheduled_task(
    *,
    user_id: str,
    title: str,
    run_at_local: str,
    instruction: str = "",
    notify_text: str = "",
    timezone_name: str = "Asia/Shanghai",
    schedule_type: str = "once",
    weekdays: Optional[List[int]] = None,
    channel: str = "web",
    chat_id: Optional[str] = None,
    conversation_id: Optional[str] = None,
) -> ScheduledTask:
    weekday_values = _normalize_weekdays_for_type(schedule_type, weekdays)
    next_run_at = compute_next_run_at(
        run_at_local, timezone_name, schedule_type, weekday_values
    )
    title_value = title.strip()
    instruction_value = (instruction or "").strip()
    notify_value = _fill_notify_text(title_value, instruction_value, notify_text)
    task = ScheduledTask(
        task_id=uuid4().hex[:16],
        user_id=user_id,
        title=title_value,
        instruction=instruction_value,
        notify_text=notify_value,
        timezone=(timezone_name or "Asia/Shanghai").strip() or "Asia/Shanghai",
        schedule_type=schedule_type,
        weekdays=weekday_values,
        run_at_local=run_at_local.strip().replace("T", " "),
        next_run_at=next_run_at,
        channel=channel,
        chat_id=(chat_id or "").strip() or None,
        conversation_id=conversation_id,
        enabled=True,
        status="pending",
    )
    await task.insert()
    return task


async def list_scheduled_tasks(user_id: str) -> list[ScheduledTask]:
    return await ScheduledTask.find(ScheduledTask.user_id == user_id).sort("+next_run_at").to_list()


async def get_scheduled_task(user_id: str, task_id: str) -> Optional[ScheduledTask]:
    return await ScheduledTask.find_one(
        ScheduledTask.user_id == user_id,
        ScheduledTask.task_id == task_id,
    )


async def update_scheduled_task(
    *,
    user_id: str,
    task_id: str,
    title: Optional[str] = None,
    instruction: Optional[str] = None,
    notify_text: Optional[str] = None,
    timezone_name: Optional[str] = None,
    schedule_type: Optional[str] = None,
    weekdays: Optional[Union[list, str]] = None,
    run_at_local: Optional[str] = None,
    channel: Optional[str] = None,
    chat_id: Optional[str] = None,
) -> ScheduledTask:
    task = await get_scheduled_task(user_id, task_id)
    if not task:
        raise ValueError("任务不存在，或无权操作")

    if title is not None:
        task.title = title.strip()
    if instruction is not None:
        task.instruction = instruction.strip()
    if notify_text is not None:
        task.notify_text = notify_text.strip()
    if timezone_name is not None:
        task.timezone = timezone_name.strip() or task.timezone
    if schedule_type is not None:
        task.schedule_type = schedule_type
    if weekdays is not None:
        task.weekdays = parse_weekdays(weekdays)
    if run_at_local is not None:
        task.run_at_local = run_at_local.strip().replace("T", " ")
    if channel is not None:
        task.channel = channel
    if chat_id is not None:
        task.chat_id = chat_id.strip() or None

    task.weekdays = _normalize_weekdays_for_type(task.schedule_type, task.weekdays)
    time_changed = any(
        v is not None for v in (run_at_local, timezone_name, schedule_type, weekdays)
    )
    if time_changed:
        task.next_run_at = compute_next_run_at(
            task.run_at_local, task.timezone, task.schedule_type, task.weekdays
        )

    if not task.title:
        raise ValueError("title 不能为空")
    if not (task.notify_text or "").strip():
        task.notify_text = _fill_notify_text(task.title, task.instruction or "", "")
    if not (task.instruction or task.notify_text):
        raise ValueError("instruction 与 notify_text 至少需要一项")

    task.updated_at = datetime.utcnow()
    await task.save()
    return task


async def set_scheduled_task_enabled(user_id: str, task_id: str, enabled: bool) -> ScheduledTask:
    task = await get_scheduled_task(user_id, task_id)
    if not task:
        raise ValueError("任务不存在，或无权操作")
    task.enabled = enabled
    if enabled:
        task.status = "pending"
        if task.next_run_at <= datetime.utcnow():
            task.next_run_at = compute_next_run_at(
                task.run_at_local, task.timezone, task.schedule_type, task.weekdays
            )
    else:
        task.status = "paused"
    task.updated_at = datetime.utcnow()
    await task.save()
    return task


async def delete_scheduled_task(user_id: str, task_id: str) -> bool:
    task = await get_scheduled_task(user_id, task_id)
    if not task:
        return False
    await task.delete()
    return True


async def backfill_empty_notify_text() -> int:
    """旧任务常把提醒写进 instruction，补上 notify_text 便于直接投递。"""
    tasks = await ScheduledTask.find(
        {"$or": [{"notify_text": ""}, {"notify_text": {"$exists": False}}]}
    ).to_list()
    updated = 0
    for task in tasks:
        filled = _fill_notify_text(task.title or "", task.instruction or "", task.notify_text or "")
        if not filled or filled == (task.notify_text or ""):
            continue
        task.notify_text = filled
        task.updated_at = datetime.utcnow()
        await task.save()
        updated += 1
    return updated


async def claim_due_tasks(limit: int = 10) -> list[ScheduledTask]:
    now = datetime.utcnow()
    pending = await ScheduledTask.find(
        {"enabled": True, "status": "pending"}
    ).sort("+next_run_at").to_list()
    claimed: list[ScheduledTask] = []
    for task in pending:
        next_run = _naive_utc(task.next_run_at)
        if next_run is None or next_run > now:
            continue
        task.status = "running"
        task.updated_at = now
        await task.save()
        claimed.append(task)
        if len(claimed) >= limit:
            break
    return claimed


async def recover_stale_running_tasks(timeout_minutes: int = 5) -> int:
    stale_before = datetime.utcnow() - timedelta(minutes=timeout_minutes)
    stuck = await ScheduledTask.find(
        ScheduledTask.status == "running",
        ScheduledTask.updated_at <= stale_before,
    ).to_list()
    for task in stuck:
        task.status = "pending"
        task.last_error = "执行超时，已重新排队"
        task.updated_at = datetime.utcnow()
        await task.save()
    return len(stuck)


async def finish_scheduled_task(task: ScheduledTask, *, error: Optional[str] = None) -> ScheduledTask:
    now = datetime.utcnow()
    task.last_run_at = now
    task.updated_at = now
    if error:
        task.last_error = str(error)[:2000]
        if task.schedule_type == "once":
            task.status = "failed"
        else:
            task.status = "pending"
            task.next_run_at = compute_next_run_at(
                task.run_at_local, task.timezone, task.schedule_type, task.weekdays, now=now
            )
    else:
        task.last_error = None
        if task.schedule_type == "once":
            task.status = "succeeded"
        else:
            task.status = "pending"
            task.next_run_at = compute_next_run_at(
                task.run_at_local, task.timezone, task.schedule_type, task.weekdays, now=now
            )
    await task.save()
    return task

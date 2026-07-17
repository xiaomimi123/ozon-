"""上架节奏调度：pace 三级回退 + active_hours 窗口 + plan_schedule 排 scheduled_at(§5.9)。"""
from datetime import datetime, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import PublishPace, ListingDraft

DEFAULT_PACE = {"min_interval_sec": 60, "max_interval_sec": 180, "daily_limit": 200,
                "active_hours": [9, 23], "wait_ozon_approval": True}

def _pace_to_dict(p: PublishPace) -> dict:
    return {"min_interval_sec": p.min_interval_sec, "max_interval_sec": p.max_interval_sec,
            "daily_limit": p.daily_limit, "active_hours": list(p.active_hours or [9, 23]),
            "wait_ozon_approval": p.wait_ozon_approval}

async def get_pace(session: AsyncSession, task_id: int) -> dict:
    row = (await session.execute(select(PublishPace).where(PublishPace.task_id == task_id))).scalar_one_or_none()
    if row:
        return _pace_to_dict(row)
    glob = (await session.execute(select(PublishPace).where(PublishPace.task_id.is_(None)))).scalars().first()
    if glob:
        return _pace_to_dict(glob)
    return dict(DEFAULT_PACE)

def next_active_window(dt: datetime, active_hours) -> datetime:
    start, end = active_hours[0], active_hours[1]
    if dt.hour < start:
        return dt.replace(hour=start, minute=0, second=0, microsecond=0)
    if dt.hour >= end:
        nxt = dt + timedelta(days=1)
        return nxt.replace(hour=start, minute=0, second=0, microsecond=0)
    return dt

async def plan_schedule(session: AsyncSession, task_id: int, pace: dict, *, now: datetime, rng) -> dict:
    drafts = (await session.execute(select(ListingDraft).where(
        ListingDraft.task_id == task_id, ListingDraft.status == "confirmed",
        ListingDraft.scheduled_at.is_(None)).order_by(ListingDraft.id))).scalars().all()
    ah = list(pace.get("active_hours", [9, 23]))
    daily_limit = int(pace.get("daily_limit", 200))
    mn, mx = int(pace.get("min_interval_sec", 60)), int(pace.get("max_interval_sec", 180))
    per_day: dict = {}
    cursor = now
    n = 0
    for d in drafts:
        cursor = cursor + timedelta(seconds=rng.randint(mn, mx))
        cursor = next_active_window(cursor, ah)
        while per_day.get(cursor.date(), 0) >= daily_limit:
            nxt = cursor + timedelta(days=1)
            cursor = nxt.replace(hour=ah[0], minute=0, second=0, microsecond=0)
        d.scheduled_at = cursor
        d.status = "scheduled"
        per_day[cursor.date()] = per_day.get(cursor.date(), 0) + 1
        n += 1
    return {"scheduled": n}

"""上架排期/tick/监控 API。"""
import random
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
import app.core.db as dbmod
from app.core.db import get_session
from app.api.deps import require_role, get_current_user
from app.models import CollectTask, ListingDraft, User
from app.services.publish_scheduler import get_pace, plan_schedule
from app.workers.publisher import tick_publish
from app.services.ozon_seller.resolve import resolve_seller

router = APIRouter(prefix="/publish", tags=["publish"])

async def _task_or_404(s: AsyncSession, task_id: int) -> CollectTask:
    t = (await s.execute(select(CollectTask).where(CollectTask.id == task_id))).scalar_one_or_none()
    if not t:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "任务不存在")
    return t

@router.post("/schedule")
async def publish_schedule(task_id: int, s: AsyncSession = Depends(get_session), _: User = Depends(require_role("operator"))):
    await _task_or_404(s, task_id)
    pace = await get_pace(s, task_id)
    r = await plan_schedule(s, task_id, pace, now=datetime.now(timezone.utc), rng=random.Random())
    await s.commit()
    return r

@router.post("/tick")
async def publish_tick(task_id: int, sync: bool = False, s: AsyncSession = Depends(get_session), _: User = Depends(require_role("publisher"))):
    await _task_or_404(s, task_id)
    if sync:
        return await tick_publish(dbmod.async_session, task_id, seller=await resolve_seller(s), now=datetime.now(timezone.utc))
    from arq import create_pool
    from arq.connections import RedisSettings
    from app.core.config import settings
    pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    try:
        await pool.enqueue_job("run_publish_tick")
    finally:
        await pool.aclose()
    return {"status": "queued"}

@router.get("/monitor")
async def publish_monitor(task_id: int, s: AsyncSession = Depends(get_session), _: User = Depends(get_current_user)):
    rows = (await s.execute(select(ListingDraft.status, func.count()).where(
        ListingDraft.task_id == task_id).group_by(ListingDraft.status))).all()
    counts = {st: c for st, c in rows}
    nxt = (await s.execute(select(func.min(ListingDraft.scheduled_at)).where(
        ListingDraft.task_id == task_id, ListingDraft.status == "scheduled"))).scalar_one_or_none()
    pace = await get_pace(s, task_id)
    return {"counts": counts, "next_scheduled_at": nxt.isoformat() if nxt else None, "pace": pace}

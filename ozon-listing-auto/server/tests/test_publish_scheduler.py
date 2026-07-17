import random
import pytest
from datetime import datetime, timezone
from sqlalchemy import select
from app.services.publish_scheduler import plan_schedule, next_active_window, get_pace, DEFAULT_PACE
from app.models import CollectTask, OzonProduct, SupplyCandidate, ListingDraft, PublishPace

def test_next_active_window():
    ah = [9, 23]
    # 时段内不变
    d = datetime(2026, 7, 18, 10, 0, tzinfo=timezone.utc)
    assert next_active_window(d, ah).hour == 10
    # 时段前(6点)→当日 9点
    d2 = datetime(2026, 7, 18, 6, 0, tzinfo=timezone.utc)
    r2 = next_active_window(d2, ah); assert r2.hour == 9 and r2.day == 18
    # 时段后(23点+)→次日 9点
    d3 = datetime(2026, 7, 18, 23, 30, tzinfo=timezone.utc)
    r3 = next_active_window(d3, ah); assert r3.hour == 9 and r3.day == 19

async def _seed(db_session, n=3):
    t = CollectTask(name="t", entry_type="keyword", entry_value="x", provider="mock", source_platforms=["ali1688"])
    db_session.add(t); await db_session.flush()
    p = OzonProduct(task_id=t.id, sku="OZSKU1", title="phone")
    db_session.add(p); await db_session.flush()
    for i in range(n):
        c = SupplyCandidate(task_id=t.id, ozon_product_id=p.id, platform="ali1688", offer_id=f"A{i}", status="adopted")
        db_session.add(c); await db_session.flush()
        db_session.add(ListingDraft(task_id=t.id, ozon_product_id=p.id, candidate_id=c.id, mode="follow",
                                    target_ozon_sku="OZSKU1", price=100, status="confirmed"))
    await db_session.commit()
    return t.id

@pytest.mark.asyncio
async def test_plan_schedule_spaces_and_advances(db_session):
    tid = await _seed(db_session, n=3)
    now = datetime(2026, 7, 18, 10, 0, tzinfo=timezone.utc)
    rng = random.Random(42)
    r = await plan_schedule(db_session, tid, DEFAULT_PACE, now=now, rng=rng)
    await db_session.commit()
    assert r["scheduled"] == 3
    drafts = (await db_session.execute(select(ListingDraft).where(ListingDraft.task_id == tid).order_by(ListingDraft.scheduled_at))).scalars().all()
    assert all(d.status == "scheduled" and d.scheduled_at is not None for d in drafts)
    # 递增且都晚于 now
    times = [d.scheduled_at for d in drafts]
    assert times[0] > now and times == sorted(times)

@pytest.mark.asyncio
async def test_plan_schedule_zero_daily_limit_no_hang(db_session):
    tid = await _seed(db_session, n=2)
    now = datetime(2026, 7, 18, 10, 0, tzinfo=timezone.utc)
    rng = random.Random(1)
    pace = {**DEFAULT_PACE, "daily_limit": 0}   # 0 不应死循环
    r = await plan_schedule(db_session, tid, pace, now=now, rng=rng)
    await db_session.commit()
    assert r["scheduled"] == 2   # 正常排期, 不 hang

@pytest.mark.asyncio
async def test_plan_schedule_daily_limit_across_batches(db_session):
    tid = await _seed(db_session, n=2)   # 2 confirmed drafts
    now = datetime(2026, 7, 18, 10, 0, tzinfo=timezone.utc)
    pace = {**DEFAULT_PACE, "daily_limit": 1, "min_interval_sec": 1, "max_interval_sec": 1, "active_hours": [0, 24]}
    # 第一次: 1 条排到今天, 1 条应被 daily_limit=1 顶到次日
    r1 = await plan_schedule(db_session, tid, pace, now=now, rng=random.Random(1))
    await db_session.commit()
    assert r1["scheduled"] == 2
    from sqlalchemy import select as _sel
    from app.models import ListingDraft as _LD
    days = sorted({d.scheduled_at.date() for d in (await db_session.execute(_sel(_LD).where(_LD.task_id == tid))).scalars().all()})
    assert len(days) == 2   # daily_limit=1 → 两条分到两天(而非同一天)

@pytest.mark.asyncio
async def test_get_pace_fallback(db_session):
    tid = await _seed(db_session, n=1)
    # 无 pace → DEFAULT
    p0 = await get_pace(db_session, tid)
    assert p0["daily_limit"] == 200
    # 全局 pace
    db_session.add(PublishPace(task_id=None, daily_limit=99)); await db_session.commit()
    p1 = await get_pace(db_session, tid)
    assert p1["daily_limit"] == 99
    # 任务 pace 覆盖
    db_session.add(PublishPace(task_id=tid, daily_limit=5)); await db_session.commit()
    p2 = await get_pace(db_session, tid)
    assert p2["daily_limit"] == 5

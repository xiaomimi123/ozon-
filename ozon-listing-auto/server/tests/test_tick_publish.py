import pytest
from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
from app.workers.publisher import tick_publish
from app.services.ozon_seller.mock import MockOzonSeller
from app.core.crypto import encrypt
from app.models import CollectTask, OzonProduct, SupplyCandidate, ListingDraft, Shop, PublishPace

async def _seed(sm, *, wait_approval=True, sched_offset_sec=-10):
    async with sm() as s:
        t = CollectTask(name="t", entry_type="keyword", entry_value="x", provider="mock", source_platforms=["ali1688"])
        s.add(t); await s.flush()
        s.add(PublishPace(task_id=t.id, wait_ozon_approval=wait_approval, min_interval_sec=1, max_interval_sec=1))
        p = OzonProduct(task_id=t.id, sku="OZSKU1", title="phone", barcode="460")
        s.add(p); await s.flush()
        shop = Shop(name="店", client_id="C", api_key_encrypted=encrypt("K"))
        s.add(shop); await s.flush()
        now = datetime(2026, 7, 18, 12, 0, tzinfo=timezone.utc)
        c = SupplyCandidate(task_id=t.id, ozon_product_id=p.id, platform="ali1688", offer_id="A0", status="adopted")
        s.add(c); await s.flush()
        s.add(ListingDraft(task_id=t.id, ozon_product_id=p.id, candidate_id=c.id, shop_id=shop.id, mode="follow",
                           target_ozon_sku="OZSKU1", barcode="460", price=100, stock_qty=5, status="scheduled",
                           scheduled_at=now + timedelta(seconds=sched_offset_sec)))
        await s.commit()
        return t.id, now

@pytest.mark.asyncio
async def test_tick_publishes_due_draft_pending_review_when_wait(engine):
    sm = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    tid, now = await _seed(sm, wait_approval=True)
    r = await tick_publish(sm, tid, seller=MockOzonSeller(), now=now)
    async with sm() as s:
        d = (await s.execute(select(ListingDraft).where(ListingDraft.task_id == tid))).scalar_one()
    assert r["pending_review"] == 1 and r["published"] == 0
    assert d.status == "pending_review" and d.ozon_result["ozon_product_id"] == "OZ-A0"

@pytest.mark.asyncio
async def test_tick_no_wait_publishes_directly(engine):
    sm = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    tid, now = await _seed(sm, wait_approval=False)
    r = await tick_publish(sm, tid, seller=MockOzonSeller(), now=now)
    async with sm() as s:
        d = (await s.execute(select(ListingDraft).where(ListingDraft.task_id == tid))).scalar_one()
    assert r["published"] == 1 and d.status == "published"

@pytest.mark.asyncio
async def test_tick_not_due_skips(engine):
    sm = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    tid, now = await _seed(sm, wait_approval=False, sched_offset_sec=+3600)  # 未来
    r = await tick_publish(sm, tid, seller=MockOzonSeller(), now=now)
    assert r["published"] == 0

@pytest.mark.asyncio
async def test_tick_approval_gate_blocks_next(engine):
    # 已有一条 pending_review(注入 seller pending) → 不推下一条
    sm = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    tid, now = await _seed(sm, wait_approval=True)
    # 先把已有草稿置 pending_review 并给个 ozon id
    async with sm() as s:
        d = (await s.execute(select(ListingDraft).where(ListingDraft.task_id == tid))).scalar_one()
        d.status = "pending_review"; d.ozon_result = {"ozon_product_id": "OZ-A0", "status": "pending_review"}
        await s.commit()
    r = await tick_publish(sm, tid, seller=MockOzonSeller(pending_ids={"OZ-A0"}), now=now)
    assert r["waiting"] is True and r["published"] == 0
    # seller 返回 approved 时, 该条转 published
    r2 = await tick_publish(sm, tid, seller=MockOzonSeller(), now=now)
    async with sm() as s:
        d = (await s.execute(select(ListingDraft).where(ListingDraft.task_id == tid))).scalar_one()
    assert d.status == "published"

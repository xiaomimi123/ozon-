import pytest
from sqlalchemy import select
from app.services.listing_builder import build_follow_drafts
from app.services.pricing import DEFAULT_PRICING
from app.models import CollectTask, OzonProduct, SupplyCandidate, ListingDraft

async def _seed(db_session):
    t = CollectTask(name="t", entry_type="keyword", entry_value="x", provider="mock", source_platforms=["ali1688"])
    db_session.add(t); await db_session.flush()
    p = OzonProduct(task_id=t.id, sku="OZSKU1", title="phone", barcode="460", weight=0.3)
    db_session.add(p); await db_session.flush()
    # 一个已采用(adopted), 一个未采用(candidate)
    db_session.add(SupplyCandidate(task_id=t.id, ozon_product_id=p.id, platform="ali1688", offer_id="A1",
                                   price=15.0, status="adopted"))
    db_session.add(SupplyCandidate(task_id=t.id, ozon_product_id=p.id, platform="ali1688", offer_id="A2",
                                   price=20.0, status="candidate"))
    await db_session.commit()
    return t.id, p.id

@pytest.mark.asyncio
async def test_build_only_adopted(db_session):
    tid, pid = await _seed(db_session)
    r = await build_follow_drafts(db_session, tid, params=DEFAULT_PRICING, shop_id=None)
    await db_session.commit()
    assert r["built"] == 1                              # 仅 adopted 生成草稿
    drafts = (await db_session.execute(select(ListingDraft).where(ListingDraft.task_id == tid))).scalars().all()
    assert len(drafts) == 1
    d = drafts[0]
    assert d.mode == "follow" and d.target_ozon_sku == "OZSKU1" and d.barcode == "460"
    assert float(d.price) > 0 and float(d.cost) > 0 and d.status == "draft"
    # 幂等: 再次 build 不新增
    r2 = await build_follow_drafts(db_session, tid, params=DEFAULT_PRICING)
    await db_session.commit()
    assert r2["built"] == 0

@pytest.mark.asyncio
async def test_build_below_min_flagged(db_session):
    tid, pid = await _seed(db_session)
    params = {**DEFAULT_PRICING, "min_price": 1e9}
    r = await build_follow_drafts(db_session, tid, params=params)
    await db_session.commit()
    d = (await db_session.execute(select(ListingDraft).where(ListingDraft.task_id == tid))).scalar_one()
    assert d.status == "below_min"
    assert r["blocked"] == 1

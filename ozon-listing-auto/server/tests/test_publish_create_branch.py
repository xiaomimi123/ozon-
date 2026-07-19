import pytest
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
from app.core.db import Base
from app.models import CollectTask, OzonProduct, SupplyCandidate, ListingDraft
from app.services.ozon_seller.factory import get_ozon_seller
from app.workers.publisher import run_publish_core, confirm_draft


@pytest.fixture
def sf(engine):
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def _seed_create_confirmed(s):
    t = CollectTask(name="k", entry_type="keyword", entry_value="k", listing_mode="create", source_platforms=[]); s.add(t); await s.flush()
    o = OzonProduct(task_id=t.id, sku="S"); s.add(o); await s.flush()
    c = SupplyCandidate(task_id=t.id, ozon_product_id=o.id, platform="ali1688", offer_id="A1", title="童鞋")
    s.add(c); await s.flush()
    d = ListingDraft(task_id=t.id, candidate_id=c.id, mode="create", title="T", description="d",
                     category_id=17028930, attributes={"1": "v"}, images=["/static/images/x.png"],
                     price=1000.0, stock_qty=3, status="confirmed")
    s.add(d); await s.commit()
    return t.id, d.id


@pytest.mark.asyncio
async def test_run_publish_core_create_branch_calls_create_product(sf):
    async with sf() as s:
        tid, did = await _seed_create_confirmed(s)
    res = await run_publish_core(sf, tid, seller=get_ozon_seller("mock"))
    assert res["published"] == 1
    async with sf() as s:
        d = (await s.execute(select(ListingDraft).where(ListingDraft.id == did))).scalar_one()
        assert d.status == "published" and d.ozon_result["ozon_product_id"] == "OZC-A1"


@pytest.mark.asyncio
async def test_confirm_draft_create_gate_requires_category_and_images(db_session):
    t = CollectTask(name="k", entry_type="keyword", entry_value="k", listing_mode="create", source_platforms=[]); db_session.add(t); await db_session.flush()
    c = SupplyCandidate(task_id=t.id, ozon_product_id=None, platform="ali1688", offer_id="A1")
    # ozon_product_id 需非空 fk? SupplyCandidate.ozon_product_id 非空 → 造一个 OzonProduct
    o = OzonProduct(task_id=t.id, sku="S"); db_session.add(o); await db_session.flush()
    c.ozon_product_id = o.id; db_session.add(c); await db_session.flush()
    d = ListingDraft(task_id=t.id, candidate_id=c.id, mode="create", status="draft",
                     category_id=None, images=None); db_session.add(d); await db_session.commit()
    r = await confirm_draft(db_session, d.id)
    assert d.status == "draft" and "error" in r      # 缺类目/图 → 不确认
    d.category_id = 1; d.images = ["/static/images/x.png"]
    r2 = await confirm_draft(db_session, d.id)
    assert d.status == "draft" and "error" in r2     # 类目/图已补, 但缺类型/尺寸 → 仍不确认
    d.type_id = 1; d.depth = 100; d.width = 80; d.height = 50; d.weight = 250
    r3 = await confirm_draft(db_session, d.id)
    assert d.status == "confirmed" and "error" not in r3

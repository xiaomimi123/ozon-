import pytest
from sqlalchemy import select
from app.models import CollectTask, OzonProduct, SupplyCandidate, ListingDraft, ProductImage
from app.services.ozon_seller.factory import get_ozon_seller
from app.services.listing_builder import build_create_drafts
from app.services.llm.factory import get_llm
from app.services.category_tree import get_category_tree


@pytest.mark.asyncio
async def test_mock_create_product_deterministic():
    seller = get_ozon_seller("mock")
    r = await seller.create_product(client_id="c", api_key="k", offer_id="A1", title="T", description="d",
                                    category_id=17028930, attributes={"1": "v"},
                                    images=["/static/images/x.png"], price=1000.0, stock=5, barcode="B")
    assert r.ok and r.ozon_product_id == "OZC-A1" and r.status == "imported"


async def _create_task_with_adopted(s, with_image=True):
    t = CollectTask(name="k", entry_type="keyword", entry_value="k", listing_mode="create", source_platforms=[]); s.add(t); await s.flush()
    o = OzonProduct(task_id=t.id, sku="S", weight=0.5); s.add(o); await s.flush()
    c = SupplyCandidate(task_id=t.id, ozon_product_id=o.id, platform="ali1688", offer_id="A1",
                        title="童鞋", price=30.0, status="adopted"); s.add(c); await s.flush()
    if with_image:
        s.add(ProductImage(task_id=t.id, candidate_id=c.id, op="whitebg", provider="local",
                           result_url="/static/images/w.png", sort=0, status="approved"))
    await s.commit()
    return t, c


@pytest.mark.asyncio
async def test_build_create_drafts_makes_draft_with_category_price_images(db_session):
    t, c = await _create_task_with_adopted(db_session, with_image=True)
    res = await build_create_drafts(db_session, t.id, llm=get_llm("mock"), tree=get_category_tree("mock"))
    await db_session.commit()
    assert res["built"] == 1
    d = (await db_session.execute(select(ListingDraft).where(ListingDraft.task_id == t.id))).scalar_one()
    assert d.mode == "create" and d.category_id is not None and d.price is not None
    assert d.images == ["/static/images/w.png"]


@pytest.mark.asyncio
async def test_build_create_drafts_idempotent_and_no_image(db_session):
    t, c = await _create_task_with_adopted(db_session, with_image=False)
    r1 = await build_create_drafts(db_session, t.id, llm=get_llm("mock"), tree=get_category_tree("mock"))
    await db_session.commit()
    r2 = await build_create_drafts(db_session, t.id, llm=get_llm("mock"), tree=get_category_tree("mock"))
    await db_session.commit()
    assert r1["built"] == 1 and r2["built"] == 0 and r2["skipped"] == 1
    d = (await db_session.execute(select(ListingDraft).where(ListingDraft.task_id == t.id))).scalar_one()
    assert d.images in ([], None)   # 无 approved 图 → 空，待补

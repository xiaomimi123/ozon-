import pytest
from sqlalchemy import select
from app.models import CollectTask, OzonProduct, SupplyCandidate, ListingDraft, CategoryMap
from app.services.category_tree import get_category_tree
from app.services.category_map import suggest_category, confirm_category
from app.services.llm.factory import get_llm


async def _cand(s, title="童鞋 保暖"):
    t = CollectTask(name="k", entry_type="keyword", entry_value="k", listing_mode="create", source_platforms=[])
    s.add(t); await s.flush()
    o = OzonProduct(task_id=t.id, sku="S"); s.add(o); await s.flush()
    c = SupplyCandidate(task_id=t.id, ozon_product_id=o.id, platform="ali1688", offer_id="A", title=title)
    s.add(c); await s.flush()
    return t, c


@pytest.mark.asyncio
async def test_mock_tree_children():
    tree = get_category_tree("mock")
    roots = await tree.list_children(parent_id=None)
    assert roots and all({"id", "name", "path"} <= set(n) for n in roots)


@pytest.mark.asyncio
async def test_suggest_uses_memory_when_confirmed_hit(db_session):
    _, c = await _cand(db_session)
    from app.services.category_map import _signature
    db_session.add(CategoryMap(signature=_signature(c), source_hint=c.title, ozon_category_id=999,
                               ozon_category_path="X/Y", attributes={"a": "b"}, confirmed=True))
    await db_session.commit()
    res = await suggest_category(db_session, c, llm=get_llm("mock"), tree=get_category_tree("mock"))
    assert res["source"] == "memory" and res["category_id"] == 999
    hit = (await db_session.execute(select(CategoryMap).where(CategoryMap.ozon_category_id == 999))).scalar_one()
    assert hit.usage_count == 1     # 命中 +1


@pytest.mark.asyncio
async def test_suggest_falls_back_when_llm_empty(db_session):
    _, c = await _cand(db_session)
    res = await suggest_category(db_session, c, llm=get_llm("mock"), tree=get_category_tree("mock"))
    assert res["source"] in ("llm", "fallback") and res["category_id"] is not None


@pytest.mark.asyncio
async def test_confirm_writes_memory_and_draft(db_session):
    _, c = await _cand(db_session)
    d = ListingDraft(task_id=c.task_id, candidate_id=c.id, mode="create", status="draft"); db_session.add(d)
    await db_session.commit()
    r = await confirm_category(db_session, d.id, category_id=17028922, attributes={"1": "v"},
                               path="Обувь", signature="童鞋")
    await db_session.commit()
    assert r["category_id"] == 17028922
    got = (await db_session.execute(select(ListingDraft).where(ListingDraft.id == d.id))).scalar_one()
    assert got.category_id == 17028922 and got.attributes == {"1": "v"}
    cm = (await db_session.execute(select(CategoryMap).where(CategoryMap.signature == "童鞋"))).scalar_one()
    assert cm.confirmed is True and cm.ozon_category_id == 17028922

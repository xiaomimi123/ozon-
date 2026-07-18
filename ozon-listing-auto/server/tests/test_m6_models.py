import pytest
from sqlalchemy import select
from app.models import ProductImage, CategoryMap, ListingDraft, CollectTask, SupplyCandidate, OzonProduct

@pytest.mark.asyncio
async def test_product_image_and_category_map_and_create_draft(db_session):
    task = CollectTask(name="t", entry_type="keyword", entry_value="k", provider="mock",
                       listing_mode="create", source_platforms=[])
    db_session.add(task); await db_session.flush()
    oz = OzonProduct(task_id=task.id, sku="S1")
    db_session.add(oz); await db_session.flush()
    cand = SupplyCandidate(task_id=task.id, ozon_product_id=oz.id, platform="ali1688", offer_id="A1", title="童鞋")
    db_session.add(cand); await db_session.flush()
    img = ProductImage(task_id=task.id, candidate_id=cand.id, source_url="http://x/a.jpg",
                       op="whitebg", provider="local", result_url="/static/images/a.png", sort=0)
    cm = CategoryMap(signature="童鞋", source_hint="童鞋", ozon_category_id=17028922,
                     ozon_category_path="Обувь/Детская", attributes={"1": "v"}, confirmed=True)
    # 自建草稿：ozon_product_id 可空
    draft = ListingDraft(task_id=task.id, candidate_id=cand.id, mode="create",
                         title="Kids Shoes", description="desc", category_id=17028922,
                         attributes={"1": "v"}, images=["/static/images/a.png"], status="draft")
    db_session.add_all([img, cm, draft]); await db_session.commit()
    assert img.status == "pending"          # 默认值
    assert cm.usage_count == 0 and cm.confirmed is True
    got = (await db_session.execute(select(ListingDraft).where(ListingDraft.mode == "create"))).scalar_one()
    assert got.ozon_product_id is None and got.category_id == 17028922 and got.images == ["/static/images/a.png"]

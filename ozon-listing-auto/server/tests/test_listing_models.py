import pytest
from sqlalchemy import select
from app.models import Shop, ListingDraft, CollectTask, OzonProduct, SupplyCandidate

@pytest.mark.asyncio
async def test_shop_and_draft(db_session):
    t = CollectTask(name="t", entry_type="keyword", entry_value="x", provider="mock", source_platforms=["ali1688"])
    db_session.add(t); await db_session.flush()
    p = OzonProduct(task_id=t.id, sku="OZSKU1", title="phone", barcode="4600000000001")
    db_session.add(p); await db_session.flush()
    c = SupplyCandidate(task_id=t.id, ozon_product_id=p.id, platform="ali1688", offer_id="A1", status="adopted")
    db_session.add(c); await db_session.flush()
    shop = Shop(name="测试店", client_id="CID", api_key_encrypted=b"x")
    db_session.add(shop); await db_session.flush()
    d = ListingDraft(task_id=t.id, ozon_product_id=p.id, candidate_id=c.id, shop_id=shop.id,
                     target_ozon_sku="OZSKU1", barcode="4600000000001", price=1290.00, cost=20.0, margin=0.2)
    db_session.add(d); await db_session.commit()
    assert shop.is_active is True and shop.is_sandbox is True
    got = (await db_session.execute(select(ListingDraft).where(ListingDraft.candidate_id == c.id))).scalar_one()
    assert got.status == "draft" and got.mode == "follow" and got.currency == "RUB"
    assert float(got.price) == 1290.00
    assert p.barcode == "4600000000001"

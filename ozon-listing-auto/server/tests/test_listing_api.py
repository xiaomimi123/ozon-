"""上架 API 测试：build/drafts/confirm/publish(mock, sync)全流程。"""
import pytest
from sqlalchemy import select
from app.core.security import hash_password
from app.models import User, CollectTask, OzonProduct, SupplyCandidate, Shop, ListingDraft
from app.core.crypto import encrypt

async def _seed_login(client, db_session, role="publisher"):
    db_session.add(User(username="u", password_hash=hash_password("p"), role=role))
    t = CollectTask(name="t", entry_type="keyword", entry_value="x", provider="mock", source_platforms=["ali1688"],
                    review_config={"listing_review_required": True})
    db_session.add(t); await db_session.flush()
    p = OzonProduct(task_id=t.id, sku="OZSKU1", title="phone", barcode="460")
    db_session.add(p); await db_session.flush()
    db_session.add(SupplyCandidate(task_id=t.id, ozon_product_id=p.id, platform="ali1688", offer_id="A1",
                                   price=15.0, status="adopted", score_total=90.0))
    shop = Shop(name="店", client_id="C", api_key_encrypted=encrypt("K"))
    db_session.add(shop); await db_session.commit()
    tok = (await client.post("/auth/login", data={"username": "u", "password": "p"})).json()["access_token"]
    return t.id, shop.id, {"Authorization": f"Bearer {tok}"}

@pytest.mark.asyncio
async def test_build_confirm_publish_flow(client, db_session):
    tid, sid, h = await _seed_login(client, db_session, role="admin")
    b = await client.post(f"/listing/build?task_id={tid}&shop_id={sid}", headers=h)
    assert b.status_code == 200 and b.json()["built"] == 1
    drafts = await client.get(f"/listing/drafts?task_id={tid}", headers=h)
    assert drafts.json()[0]["status"] == "draft" and drafts.json()[0]["price"] is not None
    did = drafts.json()[0]["id"]
    c = await client.post(f"/listing/{did}/confirm", headers=h)
    assert c.json()["status"] == "confirmed"
    pub = await client.post(f"/listing/publish?task_id={tid}&sync=true", headers=h)
    assert pub.status_code == 200 and pub.json()["published"] == 1
    d2 = await client.get(f"/listing/drafts?task_id={tid}&status=published", headers=h)
    assert d2.json()[0]["ozon_result"]["ozon_product_id"] == "OZ-A1"

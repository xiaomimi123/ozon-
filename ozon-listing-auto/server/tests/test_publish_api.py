import pytest
from sqlalchemy import select
from app.core.security import hash_password
from app.models import User, CollectTask, OzonProduct, SupplyCandidate, ListingDraft, Shop
from app.core.crypto import encrypt

async def _seed_login(client, db_session):
    db_session.add(User(username="u", password_hash=hash_password("p"), role="admin"))
    t = CollectTask(name="t", entry_type="keyword", entry_value="x", provider="mock", source_platforms=["ali1688"],
                    review_config={"listing_review_required": True})
    db_session.add(t); await db_session.flush()
    p = OzonProduct(task_id=t.id, sku="OZSKU1", title="phone", barcode="460")
    db_session.add(p); await db_session.flush()
    c = SupplyCandidate(task_id=t.id, ozon_product_id=p.id, platform="ali1688", offer_id="A0", status="adopted")
    db_session.add(c); await db_session.flush()
    shop = Shop(name="店", client_id="C", api_key_encrypted=encrypt("K"))
    db_session.add(shop); await db_session.flush()
    db_session.add(ListingDraft(task_id=t.id, ozon_product_id=p.id, candidate_id=c.id, shop_id=shop.id, mode="follow",
                                target_ozon_sku="OZSKU1", barcode="460", price=100, stock_qty=5, status="confirmed"))
    await db_session.commit()
    tok = (await client.post("/auth/login", data={"username":"u","password":"p"})).json()["access_token"]
    return t.id, {"Authorization": f"Bearer {tok}"}

@pytest.mark.asyncio
async def test_schedule_then_tick_then_monitor(client, db_session):
    tid, h = await _seed_login(client, db_session)
    # 排期(pace 默认 wait_approval=True; 用 pace 关掉等审核以便直接 published)
    # min/max_interval_sec=0 + active_hours=[0,24] → scheduled_at≈schedule时的now, tick时的now更晚→到期, 免 sleep
    await client.put(f"/pace?task_id={tid}", json={"min_interval_sec":0,"max_interval_sec":0,"daily_limit":200,"active_hours":[0,24],"wait_ozon_approval":False}, headers=h)
    sch = await client.post(f"/publish/schedule?task_id={tid}", headers=h)
    assert sch.status_code == 200 and sch.json()["scheduled"] == 1
    d = (await db_session.execute(select(ListingDraft).where(ListingDraft.task_id==tid))).scalar_one()
    await db_session.refresh(d)
    assert d.status == "scheduled" and d.scheduled_at is not None
    tick = await client.post(f"/publish/tick?task_id={tid}&sync=true", headers=h)
    assert tick.status_code == 200 and tick.json()["published"] == 1
    mon = await client.get(f"/publish/monitor?task_id={tid}", headers=h)
    assert mon.json()["counts"]["published"] == 1

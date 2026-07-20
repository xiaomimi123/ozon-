import pytest
from sqlalchemy import select, func
from app.core.security import hash_password
from app.models import User, CollectTask, OzonProduct, SupplyCandidate, ImportCapture
from app.services import settings_store

_PAYLOAD = {"data": {"offerList": [
    {"offerId": 111, "subject": "连衣裙", "priceInfo": {"price": "18.5"}, "imageUrl": "http://i/1.jpg",
     "detailUrl": "http://d/111", "company": {"name": "甲厂"}},
    {"offerId": 222, "subject": "碎花裙", "priceInfo": {"price": "9.9"}, "imageUrl": "http://i/2.jpg",
     "detailUrl": "http://d/222", "company": {"name": "乙厂"}},
]}}

async def _setup(db_session):
    db_session.add(User(username="adm", password_hash=hash_password("p"), role="admin"))
    await settings_store.set_value(db_session, "sources", "import_token", "TK", is_secret=True)
    t = CollectTask(name="t", entry_type="keyword", entry_value="x", provider="mock", source_platforms=["ali1688"])
    db_session.add(t); await db_session.flush()
    p = OzonProduct(task_id=t.id, sku="S1", title="phone")
    db_session.add(p); await db_session.commit()
    return t.id, p.id

@pytest.mark.asyncio
async def test_image_search_ingest_and_idempotent(client, db_session):
    tid, pid = await _setup(db_session)
    body = {"task_id": tid, "ozon_product_id": pid, "payload": _PAYLOAD}
    r = await client.post("/import/image-search", json=body, headers={"X-Import-Token": "TK"})
    assert r.status_code == 200 and r.json()["inserted"] == 2 and r.json()["captured"] == 2
    n = (await db_session.execute(select(func.count()).select_from(SupplyCandidate).where(
        SupplyCandidate.ozon_product_id == pid, SupplyCandidate.task_id == tid))).scalar_one()
    assert n == 2
    await client.post("/import/image-search", json=body, headers={"X-Import-Token": "TK"})  # 再来一次
    n2 = (await db_session.execute(select(func.count()).select_from(SupplyCandidate).where(
        SupplyCandidate.ozon_product_id == pid))).scalar_one()
    assert n2 == 2  # 幂等去重
    caps = (await db_session.execute(select(func.count()).select_from(ImportCapture))).scalar_one()
    assert caps == 2  # 每次存 capture

@pytest.mark.asyncio
async def test_bad_token(client, db_session):
    tid, pid = await _setup(db_session)
    r = await client.post("/import/image-search", json={"task_id": tid, "ozon_product_id": pid, "payload": _PAYLOAD},
                          headers={"X-Import-Token": "WRONG"})
    assert r.status_code == 401

@pytest.mark.asyncio
async def test_product_not_in_task(client, db_session):
    tid, pid = await _setup(db_session)
    r = await client.post("/import/image-search", json={"task_id": tid, "ozon_product_id": 999999, "payload": _PAYLOAD},
                          headers={"X-Import-Token": "TK"})
    assert r.status_code == 404

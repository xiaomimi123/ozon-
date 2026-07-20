"""ingest / 列表 / 原始记录 API：token 正确入库+去重; token 错 401; 解析0条也存capture"""
import pytest
from sqlalchemy import select, func
from app.core.security import hash_password
from app.models import User, ImportCapture, ImportedProduct
from app.services import settings_store


async def _admin(client, db_session):
    db_session.add(User(username="adm", password_hash=hash_password("p"), role="admin"))
    await settings_store.set_value(db_session, "sources", "import_token", "T0KEN", is_secret=True)
    await db_session.commit()
    tok = (await client.post("/auth/login", data={"username": "adm", "password": "p"})).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


_PAYLOAD = {"data": {"offerList": [
    {"offerId": 111, "subject": "裙", "priceInfo": {"price": "18.5"}, "imageUrl": "u", "company": {"name": "甲"}},
]}}


@pytest.mark.asyncio
async def test_ingest_and_dedup(client, db_session):
    h = await _admin(client, db_session)
    r = await client.post("/import/offers?keyword=裙", json=_PAYLOAD, headers={"X-Import-Token": "T0KEN"})
    assert r.status_code == 200 and r.json()["parsed"] == 1
    # 再来一次相同 offer_id → 不重复
    await client.post("/import/offers", json=_PAYLOAD, headers={"X-Import-Token": "T0KEN"})
    n = (await db_session.execute(select(func.count()).select_from(ImportedProduct))).scalar_one()
    assert n == 1
    caps = (await db_session.execute(select(func.count()).select_from(ImportCapture))).scalar_one()
    assert caps == 2  # 每次都存 capture
    lst = await client.get("/import/offers", headers=h)
    assert lst.status_code == 200 and len(lst.json()) == 1


@pytest.mark.asyncio
async def test_ingest_bad_token(client, db_session):
    await _admin(client, db_session)
    r = await client.post("/import/offers", json=_PAYLOAD, headers={"X-Import-Token": "WRONG"})
    assert r.status_code == 401

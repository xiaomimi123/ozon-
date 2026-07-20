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


@pytest.mark.asyncio
async def test_ingest_zero_parsed_still_captures(client, db_session):
    """空 offerList → 解析 0 条但仍记 capture, 不落 ImportedProduct"""
    await _admin(client, db_session)
    caps_before = (await db_session.execute(select(func.count()).select_from(ImportCapture))).scalar_one()
    prods_before = (await db_session.execute(select(func.count()).select_from(ImportedProduct))).scalar_one()
    r = await client.post("/import/offers", json={"data": {"offerList": []}}, headers={"X-Import-Token": "T0KEN"})
    assert r.status_code == 200 and r.json()["captured"] == 0 and r.json()["parsed"] == 0
    caps_after = (await db_session.execute(select(func.count()).select_from(ImportCapture))).scalar_one()
    prods_after = (await db_session.execute(select(func.count()).select_from(ImportedProduct))).scalar_one()
    assert caps_after == caps_before + 1
    assert prods_after == prods_before


# onebound 风格响应: items.item[] + num_iid/title/price/pic_url/seller_nick/detail_url/volume
_ONEBOUND_PAYLOAD = {"items": {"item": [
    {"num_iid": 222, "title": "T恤", "price": "29.9", "pic_url": "http://img",
     "seller_nick": "潮流店", "detail_url": "http://detail", "volume": "88"},
]}}


@pytest.mark.asyncio
async def test_ingest_uses_configured_field_paths(client, db_session):
    """字段路径覆盖成非默认(onebound)结构后 ingest → 解析走覆盖路径, 而非内置默认路径。
    改 get_source_conf 前: 覆盖不透传 → 仍用默认 data.offerList/offerId 等 → 该 payload 解析不出任何行 → 本测试 FAIL。
    改后: 8 个 import_1688_*_path 全部透传 → 按 items.item/num_iid/... 解析出 1 行 → PASS。"""
    await _admin(client, db_session)
    overrides = {
        "import_1688_list_path": "items.item",
        "import_1688_offer_id_path": "num_iid",
        "import_1688_title_path": "title",
        "import_1688_price_path": "price",
        "import_1688_image_path": "pic_url",
        "import_1688_shop_path": "seller_nick",
        "import_1688_detail_url_path": "detail_url",
        "import_1688_sales_path": "volume",
    }
    for k, v in overrides.items():
        await settings_store.set_value(db_session, "sources", k, v, is_secret=False)
    await db_session.commit()

    r = await client.post("/import/offers", json=_ONEBOUND_PAYLOAD, headers={"X-Import-Token": "T0KEN"})
    assert r.status_code == 200 and r.json()["captured"] == 1 and r.json()["parsed"] == 1

    row = (await db_session.execute(select(ImportedProduct).where(
        ImportedProduct.platform == "ali1688", ImportedProduct.offer_id == "222"))).scalar_one()
    assert row.title == "T恤"
    assert float(row.price) == 29.9
    assert row.image_url == "http://img"
    assert row.shop_name == "潮流店"
    assert row.detail_url == "http://detail"
    assert row.sales == 88

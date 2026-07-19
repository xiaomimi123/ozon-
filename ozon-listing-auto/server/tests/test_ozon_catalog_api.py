"""Ozon 类目/属性 API 端点测试：无真实店铺时走样例, 返回非空 list。"""
import pytest
from app.core.security import hash_password
from app.models import User


async def _admin_headers(client, db_session):
    db_session.add(User(username="u1", password_hash=hash_password("p"), role="admin"))
    await db_session.commit()
    tok = (await client.post("/auth/login", data={"username": "u1", "password": "p"})).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


@pytest.mark.asyncio
async def test_types_sample_without_shop(client, db_session):
    h = await _admin_headers(client, db_session)
    r = await client.get("/ozon-catalog/types", headers=h)
    assert r.status_code == 200 and isinstance(r.json(), list) and r.json()


@pytest.mark.asyncio
async def test_attributes_sample_without_shop(client, db_session):
    h = await _admin_headers(client, db_session)
    r = await client.get("/ozon-catalog/attributes?category_id=17028922&type_id=93080", headers=h)
    assert r.status_code == 200 and isinstance(r.json(), list) and r.json()


@pytest.mark.asyncio
async def test_attribute_values_sample_without_shop(client, db_session):
    h = await _admin_headers(client, db_session)
    r = await client.get(
        "/ozon-catalog/attribute-values?category_id=17028922&type_id=93080&attribute_id=85", headers=h
    )
    assert r.status_code == 200 and isinstance(r.json(), list) and r.json()

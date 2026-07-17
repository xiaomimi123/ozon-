import pytest
from app.core.security import hash_password
from app.models import User

async def _admin(client, db_session):
    db_session.add(User(username="a", password_hash=hash_password("p"), role="admin"))
    await db_session.commit()
    tok = (await client.post("/auth/login", data={"username": "a", "password": "p"})).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}

@pytest.mark.asyncio
async def test_create_list_shop_no_key_leak(client, db_session):
    h = await _admin(client, db_session)
    r = await client.post("/shops", json={"name": "测试店", "client_id": "CID", "api_key": "SECRETKEY", "is_sandbox": True}, headers=h)
    assert r.status_code == 201
    assert "api_key" not in r.json() and "SECRETKEY" not in str(r.json())
    lst = await client.get("/shops", headers=h)
    assert lst.status_code == 200 and lst.json()[0]["client_id"] == "CID"
    assert "api_key" not in str(lst.json())

@pytest.mark.asyncio
async def test_shop_requires_admin(client, db_session):
    from app.core.security import hash_password
    from app.models import User
    db_session.add(User(username="op", password_hash=hash_password("p"), role="operator"))
    await db_session.commit()
    tok = (await client.post("/auth/login", data={"username": "op", "password": "p"})).json()["access_token"]
    r = await client.post("/shops", json={"name": "x", "client_id": "c", "api_key": "k"},
                          headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 403

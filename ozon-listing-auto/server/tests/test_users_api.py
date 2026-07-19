import pytest
from app.core.security import hash_password
from app.models import User


async def _login(client, db_session, username="admin", pw="p", role="admin"):
    db_session.add(User(username=username, password_hash=hash_password(pw), role=role))
    await db_session.commit()
    tok = (await client.post("/auth/login", data={"username": username, "password": pw})).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


@pytest.mark.asyncio
async def test_user_crud_and_no_password_leak(client, db_session):
    h = await _login(client, db_session)
    r = await client.post("/users", headers=h, json={"username": "op1", "password": "pw123", "role": "operator"})
    assert r.status_code == 200 and "password_hash" not in r.json() and r.json()["role"] == "operator"
    uid = r.json()["id"]
    lst = (await client.get("/users", headers=h)).json()
    assert any(u["username"] == "op1" for u in lst) and all("password_hash" not in u for u in lst)
    # 改角色/停用
    assert (await client.put(f"/users/{uid}", headers=h, json={"role": "reviewer", "is_active": False})).json()["role"] == "reviewer"
    # 重置密码 → 新密码可登录
    await client.post(f"/users/{uid}/password", headers=h, json={"password": "newpw"})
    await client.put(f"/users/{uid}", headers=h, json={"is_active": True})
    assert (await client.post("/auth/login", data={"username": "op1", "password": "newpw"})).status_code == 200
    # 删
    assert (await client.delete(f"/users/{uid}", headers=h)).status_code == 200


@pytest.mark.asyncio
async def test_duplicate_username_400(client, db_session):
    h = await _login(client, db_session)
    await client.post("/users", headers=h, json={"username": "dup", "password": "x", "role": "operator"})
    assert (await client.post("/users", headers=h, json={"username": "dup", "password": "y", "role": "operator"})).status_code == 400


@pytest.mark.asyncio
async def test_cannot_lock_out_last_admin(client, db_session):
    h = await _login(client, db_session)   # 唯一 admin
    me = (await client.get("/auth/me", headers=h)).json()
    # 停用自己 / 删自己 / 降级自己 → 400
    assert (await client.put(f"/users/{me['id']}", headers=h, json={"is_active": False})).status_code == 400
    assert (await client.put(f"/users/{me['id']}", headers=h, json={"role": "operator"})).status_code == 400
    assert (await client.delete(f"/users/{me['id']}", headers=h)).status_code == 400


@pytest.mark.asyncio
async def test_non_admin_403(client, db_session):
    h = await _login(client, db_session, username="op", pw="p", role="operator")
    assert (await client.get("/users", headers=h)).status_code == 403

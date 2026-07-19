"""账号池 CRUD API 测试：验证 credentials 加密存储、响应脱敏、admin 权限校验。"""
import json
from datetime import datetime, timezone, timedelta
import pytest
from app.core.security import hash_password
from app.core.crypto import encrypt
from app.models import User, SourceAccount

async def _admin(client, db_session):
    db_session.add(User(username="a", password_hash=hash_password("p"), role="admin"))
    await db_session.commit()
    tok = (await client.post("/auth/login", data={"username":"a","password":"p"})).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}

@pytest.mark.asyncio
async def test_create_list_account_no_credential_leak(client, db_session):
    h = await _admin(client, db_session)
    r = await client.post("/accounts", json={"platform":"ali1688","label":"号1","credentials":{"cookie":"secret"}}, headers=h)
    assert r.status_code == 201
    assert "credentials" not in r.json() and "secret" not in str(r.json())
    lst = await client.get("/accounts?platform=ali1688", headers=h)
    assert lst.status_code == 200 and lst.json()[0]["platform"] == "ali1688"
    assert lst.json()[0]["status"] == "active"

@pytest.mark.asyncio
async def test_account_requires_admin(client, db_session):
    from app.core.security import hash_password
    from app.models import User
    db_session.add(User(username="op", password_hash=hash_password("p"), role="operator"))
    await db_session.commit()
    tok = (await client.post("/auth/login", data={"username":"op","password":"p"})).json()["access_token"]
    r = await client.post("/accounts", json={"platform":"ali1688","credentials":{"cookie":"x"}},
                          headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 403

@pytest.mark.asyncio
async def test_put_status_active_clears_cooldown(client, db_session):
    h = await _admin(client, db_session)
    acc = SourceAccount(platform="ali1688", label="a",
                        credentials_encrypted=encrypt(json.dumps({"cookie": "c"})),
                        status="cooldown", cooldown_until=datetime.now(timezone.utc) + timedelta(minutes=30))
    db_session.add(acc); await db_session.commit()
    r = await client.put(f"/accounts/{acc.id}", json={"status": "active"}, headers=h)
    assert r.status_code == 200 and r.json()["status"] == "active"
    await db_session.refresh(acc)
    assert acc.cooldown_until is None

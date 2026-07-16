import pytest
from app.core.security import hash_password
from app.models import User

async def _seed_admin(db_session):
    u = User(username="admin", password_hash=hash_password("pass123"), role="admin")
    db_session.add(u); await db_session.commit()

@pytest.mark.asyncio
async def test_login_and_me(client, db_session):
    await _seed_admin(db_session)
    r = await client.post("/auth/login", data={"username": "admin", "password": "pass123"})
    assert r.status_code == 200
    token = r.json()["access_token"]
    assert r.json()["role"] == "admin"
    me = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200 and me.json()["username"] == "admin"

@pytest.mark.asyncio
async def test_login_bad_password(client, db_session):
    await _seed_admin(db_session)
    r = await client.post("/auth/login", data={"username": "admin", "password": "wrong"})
    assert r.status_code == 401

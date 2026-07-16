import pytest
from app.services.settings_store import set_value, get_value, get_category

@pytest.mark.asyncio
async def test_settings_store_roundtrip(db_session):
    await set_value(db_session, "llm", "api_key", "sk-123", is_secret=True, updated_by=None)
    await db_session.commit()
    assert await get_value(db_session, "llm", "api_key") == "sk-123"
    cat = await get_category(db_session, "llm")
    assert cat["api_key"] == "sk-123"

@pytest.mark.asyncio
async def test_settings_api_masks_secret(client, db_session):
    from app.core.security import hash_password
    from app.models import User
    db_session.add(User(username="admin", password_hash=hash_password("p"), role="admin"))
    await db_session.commit()
    tok = (await client.post("/auth/login", data={"username": "admin", "password": "p"})).json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    await client.put("/settings/llm", json={"api_key": "sk-xyz"}, headers=h)
    r = await client.get("/settings/llm", headers=h)
    assert r.status_code == 200 and r.json()["api_key"] == "***"

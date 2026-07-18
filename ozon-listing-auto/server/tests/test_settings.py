import pytest
from app.services.settings_store import set_value, get_value, get_category

@pytest.mark.asyncio
async def test_settings_store_roundtrip(db_session):
    await set_value(db_session, "misc", "api_key", "sk-123", is_secret=True, updated_by=None)
    await db_session.commit()
    assert await get_value(db_session, "misc", "api_key") == "sk-123"
    cat = await get_category(db_session, "misc")
    assert cat["api_key"] == "sk-123"

@pytest.mark.asyncio
async def test_settings_api_masks_secret(client, db_session):
    # "misc" 是未被任何专属 router 占用的类目名：/settings/imagegen、/settings/crawler、
    # /settings/system、/settings/llm 均已注册专属 router 抢占具体路径，
    # 通配 /settings/{category} 只覆盖到这些之外的类目，故此处不能再用 "llm" 举例。
    from app.core.security import hash_password
    from app.models import User
    db_session.add(User(username="admin", password_hash=hash_password("p"), role="admin"))
    await db_session.commit()
    tok = (await client.post("/auth/login", data={"username": "admin", "password": "p"})).json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    await client.put("/settings/misc", json={"api_key": "sk-xyz"}, headers=h)
    r = await client.get("/settings/misc", headers=h)
    assert r.status_code == 200 and r.json()["api_key"] == "***"

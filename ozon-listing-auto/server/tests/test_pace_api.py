import pytest
from app.core.security import hash_password
from app.models import User

async def _login(client, db_session, role="operator"):
    db_session.add(User(username="u", password_hash=hash_password("p"), role=role))
    await db_session.commit()
    tok = (await client.post("/auth/login", data={"username":"u","password":"p"})).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}

@pytest.mark.asyncio
async def test_pace_get_default_then_put(client, db_session):
    from app.models import CollectTask
    h = await _login(client, db_session)
    db_session.add(CollectTask(id=1, name="t", entry_type="keyword", entry_value="x", provider="mock", source_platforms=[]))
    await db_session.commit()
    g = await client.get("/pace?task_id=1", headers=h)
    assert g.status_code == 200 and g.json()["daily_limit"] == 200   # 默认
    r = await client.put("/pace?task_id=1", json={"min_interval_sec":30,"max_interval_sec":90,"daily_limit":50,"active_hours":[8,22],"wait_ozon_approval":False}, headers=h)
    assert r.status_code == 200
    g2 = await client.get("/pace?task_id=1", headers=h)
    assert g2.json()["daily_limit"] == 50 and g2.json()["active_hours"] == [8,22] and g2.json()["wait_ozon_approval"] is False

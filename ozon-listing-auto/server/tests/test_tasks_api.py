"""任务 API 测试：创建/列表/详情与角色校验。"""
import pytest
from app.core.security import hash_password
from app.models import User

async def _login(client, db_session, role="operator"):
    db_session.add(User(username="u", password_hash=hash_password("p"), role=role))
    await db_session.commit()
    tok = (await client.post("/auth/login", data={"username": "u", "password": "p"})).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}

@pytest.mark.asyncio
async def test_create_and_list_task(client, db_session):
    h = await _login(client, db_session)
    body = {"name": "手机选品", "listing_mode": "follow", "entry_type": "keyword",
            "entry_value": "phone", "provider": "mock", "source_platforms": ["ali1688"],
            "review_config": {"source_review_required": True}}
    r = await client.post("/tasks", json=body, headers=h)
    assert r.status_code == 201
    tid = r.json()["id"]
    assert r.json()["listing_mode"] == "follow" and r.json()["status"] == "pending"
    lst = await client.get("/tasks", headers=h)
    assert any(t["id"] == tid for t in lst.json())

@pytest.mark.asyncio
async def test_create_task_requires_operator(client, db_session):
    h = await _login(client, db_session, role="reviewer")
    r = await client.post("/tasks", json={"name":"x","entry_type":"keyword","entry_value":"y"}, headers=h)
    assert r.status_code == 403

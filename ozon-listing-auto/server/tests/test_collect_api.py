"""采集启动(同步/入队)/暂停 API 测试。"""
import pytest
from sqlalchemy import select, func
from app.core.security import hash_password
from app.models import User, CollectTask, OzonProduct

async def _login(client, db_session):
    db_session.add(User(username="op", password_hash=hash_password("p"), role="operator"))
    await db_session.commit()
    tok = (await client.post("/auth/login", data={"username":"op","password":"p"})).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}

@pytest.mark.asyncio
async def test_start_collect_sync(client, db_session):
    h = await _login(client, db_session)
    db_session.add(CollectTask(name="t", entry_type="keyword", entry_value="x", provider="mock", source_platforms=[]))
    await db_session.commit()
    tid = (await db_session.execute(select(CollectTask.id))).scalar_one()
    r = await client.post(f"/collect/start?task_id={tid}&sync=true", headers=h)
    assert r.status_code == 200 and r.json()["status"] == "done"
    cnt = (await db_session.execute(select(func.count()).select_from(OzonProduct).where(OzonProduct.task_id==tid))).scalar_one()
    assert cnt > 0

@pytest.mark.asyncio
async def test_pause_collect(client, db_session):
    h = await _login(client, db_session)
    db_session.add(CollectTask(name="t", entry_type="keyword", entry_value="x", provider="mock", source_platforms=[]))
    await db_session.commit()
    tid = (await db_session.execute(select(CollectTask.id))).scalar_one()
    r = await client.post(f"/collect/pause?task_id={tid}", headers=h)
    assert r.status_code == 200
    task = (await db_session.execute(select(CollectTask).where(CollectTask.id==tid))).scalar_one()
    await db_session.refresh(task)
    assert task.status == "paused"

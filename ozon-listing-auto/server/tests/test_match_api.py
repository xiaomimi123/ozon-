import pytest
from sqlalchemy import select, func
from app.core.security import hash_password
from app.models import User, CollectTask, OzonProduct, SourceAccount, SupplyCandidate
from app.core.crypto import encrypt
import json

async def _seed_and_login(client, db_session):
    db_session.add(User(username="op", password_hash=hash_password("p"), role="operator"))
    t = CollectTask(name="t", entry_type="keyword", entry_value="x", provider="mock", source_platforms=["ali1688","pinduoduo"])
    db_session.add(t); await db_session.flush()
    db_session.add(OzonProduct(task_id=t.id, sku="S0", title="p0", main_image_url="https://img/oz.jpg"))
    for plat in ["ali1688","pinduoduo"]:
        db_session.add(SourceAccount(platform=plat, credentials_encrypted=encrypt(json.dumps({"cookie":"c"})), min_interval_sec=0))
    await db_session.commit()
    tok = (await client.post("/auth/login", data={"username":"op","password":"p"})).json()["access_token"]
    return t.id, {"Authorization": f"Bearer {tok}"}

@pytest.mark.asyncio
async def test_match_start_sync_produces_candidates(client, db_session):
    tid, h = await _seed_and_login(client, db_session)
    r = await client.post(f"/match/start?task_id={tid}&sync=true", headers=h)
    assert r.status_code == 200 and r.json()["status"] == "done"
    cands = await client.get(f"/candidates?task_id={tid}", headers=h)
    assert cands.json()["total"] > 0
    platforms = {c["platform"] for c in cands.json()["items"]}
    assert platforms == {"ali1688","pinduoduo"}

@pytest.mark.asyncio
async def test_candidates_only_representative_filter(client, db_session):
    tid, h = await _seed_and_login(client, db_session)
    await client.post(f"/match/start?task_id={tid}&sync=true", headers=h)
    reps = await client.get(f"/candidates?task_id={tid}&only_representative=true", headers=h)
    assert all(c["is_representative"] for c in reps.json()["items"])

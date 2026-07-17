import pytest
from sqlalchemy import select
from app.core.security import hash_password
from app.models import User, CollectTask, OzonProduct, SupplyCandidate, ReviewDecision

async def _seed_login(client, db_session):
    db_session.add(User(username="rv", password_hash=hash_password("p"), role="reviewer"))
    t = CollectTask(name="t", entry_type="keyword", entry_value="x", provider="mock", source_platforms=["ali1688"])
    db_session.add(t); await db_session.flush()
    p = OzonProduct(task_id=t.id, sku="S0", title="耳机")
    db_session.add(p); await db_session.flush()
    c = SupplyCandidate(task_id=t.id, ozon_product_id=p.id, platform="ali1688", offer_id="A1", score_total=88.0, tier="auto")
    db_session.add(c); await db_session.commit()
    tok = (await client.post("/auth/login", data={"username": "rv", "password": "p"})).json()["access_token"]
    return t.id, c.id, {"Authorization": f"Bearer {tok}"}

@pytest.mark.asyncio
async def test_review_queue_and_decide(client, db_session):
    tid, cid, h = await _seed_login(client, db_session)
    q = await client.get(f"/review/queue?task_id={tid}", headers=h)
    assert q.status_code == 200 and q.json()["total"] == 1
    assert q.json()["items"][0]["candidates"][0]["tier"] == "auto"
    r = await client.post(f"/review/{cid}", json={"decision": "adopt", "note": "ok"}, headers=h)
    assert r.status_code == 200 and r.json()["status"] == "adopted"
    rd = (await db_session.execute(select(ReviewDecision).where(ReviewDecision.candidate_id == cid))).scalar_one()
    assert rd.decision == "adopt"

@pytest.mark.asyncio
async def test_auto_adopt_missing_task_404(client, db_session):
    # auto-adopt requires the "operator" role (reviewer would 403 before reaching
    # the 404 check), so seed a dedicated operator user for this test.
    db_session.add(User(username="op", password_hash=hash_password("p"), role="operator"))
    await db_session.commit()
    tok = (await client.post("/auth/login", data={"username": "op", "password": "p"})).json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    r = await client.post("/review/auto-adopt?task_id=999999", headers=h)
    assert r.status_code == 404

@pytest.mark.asyncio
async def test_decide_missing_candidate_404(client, db_session):
    tid, cid, h = await _seed_login(client, db_session)
    r = await client.post("/review/999999", json={"decision": "adopt"}, headers=h)
    assert r.status_code == 404

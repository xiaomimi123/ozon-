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

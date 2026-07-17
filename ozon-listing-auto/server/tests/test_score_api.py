import pytest
from sqlalchemy import select
from app.core.security import hash_password
from app.models import User, CollectTask, OzonProduct, SupplyCandidate
from app.services.embedding.mock import MockEmbedder

async def _seed_login(client, db_session, role="operator"):
    db_session.add(User(username="u", password_hash=hash_password("p"), role=role))
    t = CollectTask(name="t", entry_type="keyword", entry_value="x", provider="mock", source_platforms=["ali1688"])
    db_session.add(t); await db_session.flush()
    p = OzonProduct(task_id=t.id, sku="S0", title="耳机", main_image_url="https://img/o.jpg", attributes={})
    db_session.add(p); await db_session.flush()
    db_session.add(SupplyCandidate(task_id=t.id, ozon_product_id=p.id, platform="ali1688", offer_id="A1",
                                   title="耳机", price=9.9, image_url="https://img/o.jpg",
                                   embedding=await MockEmbedder().embed_image("https://img/o.jpg")))
    await db_session.commit()
    tok = (await client.post("/auth/login", data={"username": "u", "password": "p"})).json()["access_token"]
    return t.id, {"Authorization": f"Bearer {tok}"}

@pytest.mark.asyncio
async def test_score_start_sync(client, db_session):
    tid, h = await _seed_login(client, db_session)
    r = await client.post(f"/score/start?task_id={tid}&sync=true", headers=h)
    assert r.status_code == 200 and r.json()["status"] == "done"
    cand = (await db_session.execute(select(SupplyCandidate).where(SupplyCandidate.task_id == tid))).scalar_one()
    await db_session.refresh(cand)
    assert cand.score_total is not None and cand.tier is not None

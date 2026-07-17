import pytest
from sqlalchemy import select
from app.models import ReviewDecision, SupplyCandidate, OzonProduct, CollectTask, User


@pytest.mark.asyncio
async def test_score_columns_and_review_decision(db_session):
    t = CollectTask(name="t", entry_type="keyword", entry_value="x", provider="mock", source_platforms=["ali1688"])
    db_session.add(t); await db_session.flush()
    p = OzonProduct(task_id=t.id, sku="S1", title="phone", embedding=[0.1]*512)
    db_session.add(p); await db_session.flush()
    c = SupplyCandidate(task_id=t.id, ozon_product_id=p.id, platform="ali1688", offer_id="A1",
                        score_image=90.0, score_total=88.5, tier="auto", score_detail={"k": 1})
    db_session.add(c); await db_session.flush()
    u = User(username="rv", password_hash="x", role="reviewer")
    db_session.add(u); await db_session.flush()
    d = ReviewDecision(task_id=t.id, ozon_product_id=p.id, candidate_id=c.id, reviewer_id=u.id, decision="adopt")
    db_session.add(d); await db_session.commit()
    assert t.score_status == "pending"
    assert len(p.embedding) == 512
    got = (await db_session.execute(select(SupplyCandidate).where(SupplyCandidate.offer_id == "A1"))).scalar_one()
    assert got.tier == "auto" and got.score_total == 88.5
    rd = (await db_session.execute(select(ReviewDecision).where(ReviewDecision.candidate_id == c.id))).scalar_one()
    assert rd.decision == "adopt"

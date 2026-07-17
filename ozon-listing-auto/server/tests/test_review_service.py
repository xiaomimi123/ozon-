"""审核服务测试：review_config 自动采用 / 审核队列聚合 / 采用拒绝决策。"""
import pytest
from sqlalchemy import select, func
from app.services.review import apply_auto_adopt, get_review_queue, decide
from app.models import CollectTask, OzonProduct, SupplyCandidate, ReviewDecision, User

async def _seed(db_session, review_config):
    t = CollectTask(name="t", entry_type="keyword", entry_value="x", provider="mock",
                    source_platforms=["ali1688"], review_config=review_config)
    db_session.add(t); await db_session.flush()
    p = OzonProduct(task_id=t.id, sku="S0", title="phone")
    db_session.add(p); await db_session.flush()
    c1 = SupplyCandidate(task_id=t.id, ozon_product_id=p.id, platform="ali1688", offer_id="A1", score_total=90.0, tier="auto")
    c2 = SupplyCandidate(task_id=t.id, ozon_product_id=p.id, platform="pinduoduo", offer_id="P1", score_total=60.0, tier="rejected")
    db_session.add_all([c1, c2]); await db_session.commit()
    return t.id, p.id, c1.id, c2.id

@pytest.mark.asyncio
async def test_auto_adopt_when_review_off(db_session):
    tid, pid, c1, c2 = await _seed(db_session, {"source_review_required": False, "source_score_min": 85})
    r = await apply_auto_adopt(db_session, tid)
    await db_session.commit()
    assert r["auto_adopted"] == 1                        # 仅 c1(>=85)
    cand1 = (await db_session.execute(select(SupplyCandidate).where(SupplyCandidate.id == c1))).scalar_one()
    assert cand1.status == "auto_adopted"
    rd = (await db_session.execute(select(ReviewDecision).where(ReviewDecision.candidate_id == c1))).scalar_one()
    assert rd.decision == "auto_adopt" and rd.reviewer_id is None
    # c1 已自动采用 → 审核队列不含其(但 c2 仍是 candidate)
    q = await get_review_queue(db_session, tid)
    prod_item = q["items"][0]
    cand_ids = [c["id"] for c in prod_item["candidates"]]
    assert c1 not in cand_ids and c2 in cand_ids

@pytest.mark.asyncio
async def test_decide_adopt_reject(db_session):
    tid, pid, c1, c2 = await _seed(db_session, {"source_review_required": True, "source_score_min": None})
    u = User(username="rv", password_hash="x", role="reviewer"); db_session.add(u); await db_session.flush()
    await decide(db_session, c1, u.id, "adopt", note="好")
    await decide(db_session, c2, u.id, "reject")
    await db_session.commit()
    cand1 = (await db_session.execute(select(SupplyCandidate).where(SupplyCandidate.id == c1))).scalar_one()
    cand2 = (await db_session.execute(select(SupplyCandidate).where(SupplyCandidate.id == c2))).scalar_one()
    assert cand1.status == "adopted" and cand2.status == "rejected"
    cnt = (await db_session.execute(select(func.count()).select_from(ReviewDecision).where(ReviewDecision.task_id == tid))).scalar_one()
    assert cnt == 2

"""货源匹配 ORM 模型测试：source_accounts / supply_candidates / collect_tasks.match_* 建表与读写。"""
import pytest
from sqlalchemy import select

from app.models import SourceAccount, SupplyCandidate, CollectTask, OzonProduct


@pytest.mark.asyncio
async def test_create_account_and_candidate(db_session):
    t = CollectTask(name="t", entry_type="keyword", entry_value="x", provider="mock", source_platforms=["ali1688"])
    db_session.add(t); await db_session.flush()
    p = OzonProduct(task_id=t.id, sku="SKU1", title="phone")
    db_session.add(p); await db_session.flush()
    acc = SourceAccount(platform="ali1688", credentials_encrypted=b"x", daily_limit=100)
    db_session.add(acc); await db_session.flush()
    c = SupplyCandidate(task_id=t.id, ozon_product_id=p.id, platform="ali1688", offer_id="A1",
                        title="cand", price=9.9, embedding=[0.1] * 512, supplier_info={"repurchase_rate": 0.45})
    db_session.add(c); await db_session.commit()
    assert t.match_status == "pending"
    assert acc.status == "active" and acc.min_interval_sec == 6
    got = (await db_session.execute(select(SupplyCandidate).where(SupplyCandidate.offer_id == "A1"))).scalar_one()
    assert got.is_representative is True and got.supplier_info["repurchase_rate"] == 0.45
    assert len(got.embedding) == 512

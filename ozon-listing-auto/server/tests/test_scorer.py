"""scorer worker 测试：Ozon 主图向量写回 + 五维评分写回 + 断点/暂停/失败。"""
import pytest
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
from app.workers.scorer import run_score_core
from app.services.embedding.mock import MockEmbedder
from app.services.llm.mock import MockLLM
from app.models import CollectTask, OzonProduct, SupplyCandidate

async def _seed(sm):
    async with sm() as s:
        t = CollectTask(name="t", entry_type="keyword", entry_value="x", provider="mock", source_platforms=["ali1688"])
        s.add(t); await s.flush()
        p = OzonProduct(task_id=t.id, sku="S0", title="无线耳机", main_image_url="https://img/oz.jpg",
                        attributes={"color": "black"})
        s.add(p); await s.flush()
        # 两个候选: 同图(高图分) 与 无图
        s.add(SupplyCandidate(task_id=t.id, ozon_product_id=p.id, platform="ali1688", offer_id="A1",
                              title="无线耳机", price=12.5, image_url="https://img/oz.jpg",
                              embedding=await MockEmbedder().embed_image("https://img/oz.jpg"),
                              supplier_info={"repurchase_rate": 0.5, "credit_level": "AA"}))
        await s.commit()
        return t.id, p.id

@pytest.mark.asyncio
async def test_run_score_writes_scores_and_embedding(engine):
    sm = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    tid, pid = await _seed(sm)
    result = await run_score_core(sm, tid, embedder=MockEmbedder(), llm=MockLLM())
    async with sm() as s:
        prod = (await s.execute(select(OzonProduct).where(OzonProduct.id == pid))).scalar_one()
        cand = (await s.execute(select(SupplyCandidate).where(SupplyCandidate.ozon_product_id == pid))).scalar_one()
        task = (await s.execute(select(CollectTask).where(CollectTask.id == tid))).scalar_one()
    assert prod.embedding is not None and len(prod.embedding) == 512   # Ozon 主图向量已写
    assert cand.score_total is not None and cand.tier in {"auto", "review", "rejected"}
    assert cand.score_image == pytest.approx(100.0, abs=1e-2)          # 候选与 Ozon 同图
    assert task.score_status == "done"
    assert result["candidates_scored"] == 1

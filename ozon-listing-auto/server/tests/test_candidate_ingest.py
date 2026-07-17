import pytest
from sqlalchemy import select, func
from app.services.candidate_ingest import cluster_by_similarity, dedup_and_upsert
from app.services.sources.base import SupplyCandidateDTO
from app.services.embedding.mock import MockEmbedder
from app.models import SupplyCandidate, CollectTask, OzonProduct

@pytest.mark.asyncio
async def test_cluster_groups_near_duplicates():
    e = MockEmbedder()
    va = await e.embed_image("https://img/x.jpg")
    vb = await e.embed_image("https://img/x.jpg")   # 同图 → 同向量
    vc = await e.embed_image("https://img/y.jpg")   # 不同图
    groups = cluster_by_similarity([va, vb, vc], threshold=0.92)
    assert groups[0] == groups[1]        # 同图同簇
    assert groups[2] != groups[0]        # 不同图不同簇

async def _seed(db_session):
    t = CollectTask(name="t", entry_type="keyword", entry_value="x", provider="mock", source_platforms=["ali1688","pinduoduo"])
    db_session.add(t); await db_session.flush()
    p = OzonProduct(task_id=t.id, sku="S1", title="phone", main_image_url="https://img/oz.jpg")
    db_session.add(p); await db_session.commit()
    return t.id, p.id

@pytest.mark.asyncio
async def test_dedup_and_upsert_cross_platform(db_session):
    tid, pid = await _seed(db_session)
    dtos = [
        SupplyCandidateDTO(platform="ali1688", offer_id="AL-1", image_url="https://img/same.jpg"),
        SupplyCandidateDTO(platform="pinduoduo", offer_id="PDD-1", image_url="https://img/same.jpg"),  # 同款跨平台
        SupplyCandidateDTO(platform="ali1688", offer_id="AL-2", image_url="https://img/other.jpg"),    # 不同款
    ]
    r = await dedup_and_upsert(db_session, tid, pid, dtos, MockEmbedder(), threshold=0.92)
    await db_session.commit()
    rows = (await db_session.execute(select(SupplyCandidate).where(SupplyCandidate.ozon_product_id == pid))).scalars().all()
    assert r["inserted"] == 3                              # 三条都入库(不删, 只标去重)
    reps = [x for x in rows if x.is_representative]
    # 同款跨平台折叠为一簇(一个代表), 不同款单独一簇 → 共 2 簇, 2 个代表
    assert len({x.dedup_group for x in rows}) == 2
    assert len(reps) == 2
    # 幂等: 再来一次不新增
    r2 = await dedup_and_upsert(db_session, tid, pid, dtos, MockEmbedder(), threshold=0.92)
    await db_session.commit()
    assert r2["inserted"] == 0 and r2["skipped"] == 3

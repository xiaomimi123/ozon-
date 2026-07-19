"""matcher worker 测试：双平台候选产出、断点续传。"""
import json
from datetime import datetime, timezone

import pytest
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from app.workers.matcher import run_match_core
from app.services.sources.mock import MockSourceProvider
from app.services.embedding.mock import MockEmbedder
from app.models import CollectTask, OzonProduct, SupplyCandidate, SourceAccount
from app.core.crypto import encrypt


def _provider_factory(platform):        # mock 工厂: 按平台返回 mock provider
    return MockSourceProvider(platform=platform)


def _now():
    return datetime(2026, 7, 17, 12, 0, 0, tzinfo=timezone.utc)


async def _seed(sm, n_products=3):
    async with sm() as s:
        t = CollectTask(name="t", entry_type="keyword", entry_value="x", provider="mock",
                        source_platforms=["ali1688", "pinduoduo"])
        s.add(t); await s.flush()
        for i in range(n_products):
            s.add(OzonProduct(task_id=t.id, sku=f"S{i}", title=f"p{i}", main_image_url=f"https://img/oz{i}.jpg"))
        # 每平台一个账号(min_interval 0 便于连续取)
        for plat in ["ali1688", "pinduoduo"]:
            s.add(SourceAccount(platform=plat, credentials_encrypted=encrypt(json.dumps({"cookie": "c"})),
                                min_interval_sec=0, daily_limit=1000))
        await s.commit()
        return t.id


@pytest.mark.asyncio
async def test_run_match_produces_dual_platform_candidates(engine):
    sm = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    tid = await _seed(sm, n_products=3)
    result = await run_match_core(sm, tid, embedder=MockEmbedder(), now_fn=_now, provider_factory=_provider_factory)
    async with sm() as s:
        rows = (await s.execute(select(SupplyCandidate).where(SupplyCandidate.task_id == tid))).scalars().all()
        task = (await s.execute(select(CollectTask).where(CollectTask.id == tid))).scalar_one()
    platforms = {r.platform for r in rows}
    assert platforms == {"ali1688", "pinduoduo"}       # 双平台候选
    assert task.match_status == "done"
    assert result["products"] == 3


@pytest.mark.asyncio
async def test_run_match_resume(engine):
    sm = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    tid = await _seed(sm, n_products=3)
    await run_match_core(sm, tid, embedder=MockEmbedder(), now_fn=_now, provider_factory=_provider_factory, max_products=1)
    async with sm() as s:
        c1 = (await s.execute(select(func.count()).select_from(SupplyCandidate).where(SupplyCandidate.task_id == tid))).scalar_one()
        task = (await s.execute(select(CollectTask).where(CollectTask.id == tid))).scalar_one()
        assert task.match_cursor is not None
    await run_match_core(sm, tid, embedder=MockEmbedder(), now_fn=_now, provider_factory=_provider_factory)  # 续跑
    async with sm() as s:
        task = (await s.execute(select(CollectTask).where(CollectTask.id == tid))).scalar_one()
        total = (await s.execute(select(func.count()).select_from(SupplyCandidate).where(SupplyCandidate.task_id == tid))).scalar_one()
    assert task.match_status == "done"
    # 3 商品全处理(幂等, 不重复插入)
    assert total >= c1


@pytest.mark.asyncio
async def test_run_match_platform_failure_isolated(engine):
    sm = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    tid = await _seed(sm, n_products=2)   # 复用现有 _seed helper (seeds ali1688+pinduoduo accounts)

    class BoomProvider:
        def __init__(self, platform): self.platform = platform
        async def image_search(self, *a, **k): raise RuntimeError("平台故障")
        async def keyword_search(self, *a, **k): raise RuntimeError("平台故障")
        async def fetch_detail(self, *a, **k): raise RuntimeError("平台故障")

    def pf(platform):
        return MockSourceProvider(platform="ali1688") if platform == "ali1688" else BoomProvider(platform)

    result = await run_match_core(sm, tid, embedder=MockEmbedder(), now_fn=_now, provider_factory=pf)
    async with sm() as s:
        task = (await s.execute(select(CollectTask).where(CollectTask.id == tid))).scalar_one()
        rows = (await s.execute(select(SupplyCandidate).where(SupplyCandidate.task_id == tid))).scalars().all()
        pdd_acc = (await s.execute(select(SourceAccount).where(SourceAccount.platform == "pinduoduo"))).scalar_one()
    assert task.match_status == "done"                     # 单平台故障不中断主流程(降级)
    assert {r.platform for r in rows} == {"ali1688"}       # 仅 1688 候选
    assert pdd_acc.status == "cooldown"                    # 风控换号: report_risk 生效


class _FakeDefaultProvider:
    """build_source_provider 默认路径下返回的假 provider：按平台带回极小候选集。"""
    def __init__(self, platform):
        self.platform = platform

    async def image_search(self, *a, **k):
        from app.services.sources.base import SupplyCandidateDTO
        return [SupplyCandidateDTO(platform=self.platform, offer_id=f"{self.platform}-1",
                                   title="x", image_url=f"https://img/{self.platform}-1.jpg")]

    async def keyword_search(self, *a, **k):
        return []

    async def fetch_detail(self, *a, **k):
        return None


@pytest.mark.asyncio
async def test_run_match_default_path_uses_build_source_provider(engine, monkeypatch):
    """provider_factory=None(默认路径)：应经 app.services.sources.factory.build_source_provider
    按平台构造真实/配置驱动 provider，而非测试专用的 mock 工厂——这是生产/ARQ 实际会走的分支。"""
    sm = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    tid = await _seed(sm, n_products=1)

    calls: list[str] = []

    async def fake_build_source_provider(session_factory, platform):
        calls.append(platform)
        return _FakeDefaultProvider(platform)

    import app.services.sources.factory as factory_mod
    monkeypatch.setattr(factory_mod, "build_source_provider", fake_build_source_provider)

    result = await run_match_core(sm, tid, embedder=MockEmbedder(), now_fn=_now, provider_factory=None)

    async with sm() as s:
        task = (await s.execute(select(CollectTask).where(CollectTask.id == tid))).scalar_one()
        rows = (await s.execute(select(SupplyCandidate).where(SupplyCandidate.task_id == tid))).scalars().all()
    assert set(calls) == {"ali1688", "pinduoduo"}           # 默认分支确实经 build_source_provider 按平台构造
    assert task.match_status == "done"
    assert result["products"] == 1
    assert {r.platform for r in rows} == {"ali1688", "pinduoduo"}

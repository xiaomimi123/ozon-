"""采集 worker 核心逻辑测试：逐页采集/跨页去重/断点续传/幂等收敛。"""
import pytest
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
from app.workers.collector import run_collect_core
from app.models import CollectTask, OzonProduct
from app.services.ingest import dedup
from app.services.ozon_market.mock import OzonMockProvider


def _expected_total():
    """全量 fixtures 去重后的期望入库总数。"""
    all_items = OzonMockProvider(page_size=1000)._all
    return len(dedup(all_items))


@pytest.mark.asyncio
async def test_run_collect_mock(engine):
    sm = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with sm() as s:
        t = CollectTask(name="t", entry_type="keyword", entry_value="phone", provider="mock", source_platforms=[])
        s.add(t); await s.commit(); tid = t.id
    result = await run_collect_core(sm, tid)
    async with sm() as s:
        count = (await s.execute(select(func.count()).select_from(OzonProduct).where(OzonProduct.task_id == tid))).scalar_one()
        task = (await s.execute(select(CollectTask).where(CollectTask.id == tid))).scalar_one()
    expected = _expected_total()
    assert count == expected                 # 12 条 mock 全量去重后的期望总数(动态计算)
    assert result["inserted"] == expected
    assert task.status == "done"
    assert task.stats["inserted"] == expected


@pytest.mark.asyncio
async def test_run_collect_resume_after_pause(engine):
    sm = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with sm() as s:
        t = CollectTask(name="t", entry_type="keyword", entry_value="x", provider="mock", source_platforms=[])
        s.add(t); await s.commit(); tid = t.id
    await run_collect_core(sm, tid, max_pages=1)     # 只采第 1 页后停
    async with sm() as s:
        c1 = (await s.execute(select(func.count()).select_from(OzonProduct).where(OzonProduct.task_id == tid))).scalar_one()
        task = (await s.execute(select(CollectTask).where(CollectTask.id == tid))).scalar_one()
        assert task.cursor["page"] == 1
    first_page = await OzonMockProvider()._page(1)
    assert c1 == len(dedup(first_page))              # 第 1 页页内去重后的入库数(动态计算)
    await run_collect_core(sm, tid)                  # 从 cursor 续跑
    async with sm() as s:
        c2 = (await s.execute(select(func.count()).select_from(OzonProduct).where(OzonProduct.task_id == tid))).scalar_one()
    assert c2 == _expected_total()                   # 幂等: 跨页去重后总数收敛到全量去重长度

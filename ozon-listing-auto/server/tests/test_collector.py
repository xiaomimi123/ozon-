"""采集 worker 核心逻辑测试：逐页采集/跨页去重/断点续传/幂等收敛。"""
import pytest
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
from app.workers.collector import run_collect_core
from app.models import CollectTask, OzonProduct
from app.services.ingest import dedup
from app.services.ozon_market.mock import OzonMockProvider
from app.services.ozon_market.composer import CrawlerBlockedError


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


@pytest.mark.asyncio
async def test_run_collect_paused_stops_then_resumes(engine):
    sm = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with sm() as s:
        t = CollectTask(name="t", entry_type="keyword", entry_value="x", provider="mock", source_platforms=[])
        s.add(t); await s.commit(); tid = t.id

    # 采集过程中，用独立 session 把任务置为 paused（模拟外部暂停）
    async def pause_cb(msg):
        async with sm() as s2:
            task = (await s2.execute(select(CollectTask).where(CollectTask.id == tid))).scalar_one()
            task.status = "paused"
            await s2.commit()

    await run_collect_core(sm, tid, progress_cb=pause_cb)

    async with sm() as s:
        task = (await s.execute(select(CollectTask).where(CollectTask.id == tid))).scalar_one()
    # 外部暂停被检测到：状态停在 paused，未推进到 done；cursor 保留以便续跑
    assert task.status == "paused"
    assert task.cursor is not None and task.cursor.get("page", 0) >= 1

    # 续跑到完成：幂等收敛到全量去重条数，且统计跨续跑累计
    await run_collect_core(sm, tid)
    async with sm() as s:
        task = (await s.execute(select(CollectTask).where(CollectTask.id == tid))).scalar_one()
        rows = (await s.execute(select(func.count()).select_from(OzonProduct).where(OzonProduct.task_id == tid))).scalar_one()
    assert task.status == "done"
    assert rows == _expected_total()
    assert task.stats["inserted"] == _expected_total()


@pytest.mark.asyncio
async def test_run_collect_marks_failed_on_provider_error(engine, monkeypatch):
    """provider 连续失败时任务应标记 failed（不卡在 running），且 run_collect_core 不抛出异常（spec §4.2.6）。"""
    sm = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with sm() as s:
        t = CollectTask(name="t", entry_type="keyword", entry_value="x", provider="mock", source_platforms=[])
        s.add(t); await s.commit(); tid = t.id

    class BoomProvider:
        name = "mock"
        async def search_by_keyword(self, kw, page):
            raise RuntimeError("boom")
        async def list_by_category(self, u, page):
            raise RuntimeError("boom")
        async def list_by_seller(self, sid, page):
            raise RuntimeError("boom")

    monkeypatch.setattr("app.services.ozon_market.factory.get_provider", lambda name: BoomProvider())

    result = await run_collect_core(sm, tid)   # 不应抛出
    assert result["pages"] == 0
    async with sm() as s:
        task = (await s.execute(select(CollectTask).where(CollectTask.id == tid))).scalar_one()
    assert task.status == "failed"


@pytest.mark.asyncio
async def test_run_collect_marks_failed_on_crawler_blocked(engine, monkeypatch):
    """provider 抛 CrawlerBlockedError（反爬拦截）时任务应标记 failed 并把可操作提示写入 stats.error（不是静默失败）。"""
    sm = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with sm() as s:
        t = CollectTask(name="t", entry_type="keyword", entry_value="x", provider="mock", source_platforms=[])
        s.add(t); await s.commit(); tid = t.id

    class BlockedProvider:
        name = "mock"
        async def search_by_keyword(self, kw, page):
            raise CrawlerBlockedError("疑似反爬/cookie 失效")
        async def list_by_category(self, u, page):
            raise CrawlerBlockedError("疑似反爬/cookie 失效")
        async def list_by_seller(self, sid, page):
            raise CrawlerBlockedError("疑似反爬/cookie 失效")

    monkeypatch.setattr("app.services.ozon_market.factory.get_provider", lambda name: BlockedProvider())

    result = await run_collect_core(sm, tid)   # 不应抛出
    assert result["pages"] == 0
    assert "疑似反爬" in result["error"]
    async with sm() as s:
        task = (await s.execute(select(CollectTask).where(CollectTask.id == tid))).scalar_one()
    assert task.status == "failed"
    assert "疑似反爬" in task.stats["error"]

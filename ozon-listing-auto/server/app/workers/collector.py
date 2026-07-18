"""采集 worker 核心逻辑：逐页拉取→跨页去重→upsert→写游标/统计/状态，支持暂停与断点续传。"""
import asyncio
import random

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.logging import get_logger
from app.services.ozon_market.factory import build_ozon_provider
from app.services.ozon_market.composer import CrawlerBlockedError
from app.services.ingest import dedup, upsert_products
from app.models import CollectTask


async def run_collect_core(session_factory: async_sessionmaker, task_id: int, *,
                            max_pages: int | None = None, jitter: bool = False, progress_cb=None) -> dict:
    """纯函数核心：按任务配置逐页采集并入库，遇 paused 状态即停，可从游标续跑。"""
    log = get_logger(task_id=task_id)
    async with session_factory() as s:
        task = (await s.execute(select(CollectTask).where(CollectTask.id == task_id))).scalar_one()
        provider = await build_ozon_provider(s, task.provider)
        entry_type, entry_value = task.entry_type, task.entry_value
        start_page = (task.cursor or {}).get("page", 0) + 1
        prior_stats = task.stats or {}
        task.status = "running"; await s.commit()

    seen_sku: set[str] = set(); seen_phash: set[str] = set()

    # 续跑（start_page > 1）时先预载该任务已入库的 sku/phash，保证跨页去重在暂停/续跑之间保持一致。
    if start_page > 1:
        from app.models import OzonProduct
        async with session_factory() as s:
            rows = (await s.execute(
                select(OzonProduct.sku, OzonProduct.phash).where(OzonProduct.task_id == task_id)
            )).all()
        for sku, phash in rows:
            seen_sku.add(sku)
            if phash:
                seen_phash.add(phash)

    total_inserted = prior_stats.get("inserted", 0)
    total_skipped = prior_stats.get("skipped", 0)
    page = start_page
    pages_done = 0
    while True:
        if max_pages is not None and pages_done >= max_pages:
            break
        try:
            # 拉一页
            if entry_type == "seller":
                batch = await provider.list_by_seller(entry_value, page)
            elif entry_type == "category":
                batch = await provider.list_by_category(entry_value, page)
            else:
                batch = await provider.search_by_keyword(entry_value, page)
            if not batch:
                async with session_factory() as s:
                    task = (await s.execute(select(CollectTask).where(CollectTask.id == task_id))).scalar_one()
                    task.status = "done"
                    task.stats = {"inserted": total_inserted, "skipped": total_skipped, "pages": pages_done}
                    await s.commit()
                break
            # 跨页去重：过滤本页/之前页已见的 sku/phash
            fresh = []
            for d in dedup(batch):
                if d.sku in seen_sku or (d.phash and d.phash in seen_phash):
                    continue
                seen_sku.add(d.sku)
                if d.phash:
                    seen_phash.add(d.phash)
                fresh.append(d)
            async with session_factory() as s:
                r = await upsert_products(s, task_id, fresh)
                task = (await s.execute(select(CollectTask).where(CollectTask.id == task_id))).scalar_one()
                total_inserted += r["inserted"]; total_skipped += r["skipped"]
                task.cursor = {"page": page}
                task.stats = {"inserted": total_inserted, "skipped": total_skipped, "pages": pages_done + 1}
                # 若外部把状态置为 paused，则停止
                paused = task.status == "paused"
                await s.commit()
        except CrawlerBlockedError as exc:
            async with session_factory() as s:
                task = (await s.execute(select(CollectTask).where(CollectTask.id == task_id))).scalar_one()
                task.status = "failed"
                task.stats = {**(task.stats or {}), "error": str(exc)}
                await s.commit()
            log.error("crawler_blocked", error=str(exc))
            return {"inserted": total_inserted, "skipped": total_skipped, "pages": pages_done, "error": str(exc)}
        except Exception as exc:
            # 连续失败标 failed 并留日志（spec §4.2.6）：保留已提交的 cursor/stats 以便人工排查后续跑
            log.error("collect_failed", page=page, error=str(exc))
            async with session_factory() as s:
                task = (await s.execute(select(CollectTask).where(CollectTask.id == task_id))).scalar_one()
                task.status = "failed"
                await s.commit()
            break
        pages_done += 1
        log.info("collect_page", page=page, inserted=r["inserted"], skipped=r["skipped"])
        if progress_cb:
            await progress_cb({"task_id": task_id, "page": page, "inserted": total_inserted, "skipped": total_skipped})
        if paused:
            break
        page += 1
        if jitter:
            await asyncio.sleep(random.uniform(0.5, 1.5))
    return {"inserted": total_inserted, "skipped": total_skipped, "pages": pages_done}


async def run_collect(ctx, task_id: int) -> dict:
    """ARQ 任务入口：包装 run_collect_core，使用真实 DB session 工厂并开启抓取间隔抖动。"""
    from app.core.db import async_session
    return await run_collect_core(async_session, task_id, jitter=True)

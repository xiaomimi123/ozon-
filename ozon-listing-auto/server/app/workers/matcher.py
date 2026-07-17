"""货源匹配 worker：遍历商品×启用平台 → 图搜+关键词 → CLIP 去重入库；断点续传/暂停/失败。"""
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.logging import get_logger
from app.services.sources.factory import get_source_provider
from app.services.account_pool import acquire, get_session_credentials, report_risk
from app.services.candidate_ingest import dedup_and_upsert
from app.models import CollectTask, OzonProduct


def _default_now():
    return datetime.now(timezone.utc)


async def run_match_core(session_factory: async_sessionmaker, task_id: int, *, embedder,
                         now_fn=None, provider_factory=None, max_products=None, progress_cb=None) -> dict:
    """纯函数核心：按商品遍历其启用平台，图搜+关键词搜集候选，跨平台合并去重后一次性入库。

    每个商品对应的所有平台候选会先合并为一个列表，再按 (platform, offer_id) 去重
    （MockSourceProvider 的 image_search/keyword_search 返回同一批候选，直接合并会产生
    重复的 (platform, offer_id) 组合，若不去重会撞 SupplyCandidate 的唯一约束），
    最后整体交给 `dedup_and_upsert` 做一次跨平台 CLIP 聚簇去重入库——这样同一商品下来自
    不同平台但视觉相同的候选才能被聚为同一簇。
    """
    now_fn = now_fn or _default_now
    provider_factory = provider_factory or get_source_provider
    log = get_logger(task_id=task_id, phase="match")

    async with session_factory() as s:
        task = (await s.execute(select(CollectTask).where(CollectTask.id == task_id))).scalar_one()
        platforms = list(task.source_platforms or [])
        last_id = (task.match_cursor or {}).get("last_product_id", 0)
        prior_stats = task.match_stats or {}
        task.match_status = "running"
        await s.commit()

    total_products = 0  # 本轮(this-run)已处理商品数，用于 max_products 断点守卫
    total_candidates = prior_stats.get("candidates", 0)
    platforms_skipped = prior_stats.get("platforms_skipped", 0)
    platforms_failed = prior_stats.get("platforms_failed", 0)

    while True:
        if max_products is not None and total_products >= max_products:
            break
        async with session_factory() as s:
            product = (await s.execute(select(OzonProduct).where(
                OzonProduct.task_id == task_id, OzonProduct.id > last_id
            ).order_by(OzonProduct.id.asc()).limit(1))).scalar_one_or_none()
        if product is None:
            async with session_factory() as s:
                task = (await s.execute(select(CollectTask).where(CollectTask.id == task_id))).scalar_one()
                task.match_status = "done"
                task.match_stats = {
                    "products": prior_stats.get("products", 0) + total_products,
                    "candidates": total_candidates,
                    "platforms_skipped": platforms_skipped,
                    "platforms_failed": platforms_failed,
                }
                await s.commit()
            break
        paused = False
        # 逐平台取号+搜索：每个平台独立 try/except 隔离，单平台故障(风控/超时/异常)不阻塞
        # 其他平台与主流程（spec §9 降级要求）；故障平台若已取到账号则上报风控换号。
        merged = []
        for platform in platforms:
            acc = None
            try:
                acc = await acquire(session_factory, platform, now=now_fn())
                if acc is None:
                    platforms_skipped += 1
                    continue
                session_handle = get_session_credentials(acc)
                provider = provider_factory(platform)
                if product.main_image_url:
                    merged += await provider.image_search(product.main_image_url, session=session_handle)
                if product.title:
                    merged += await provider.keyword_search(product.title, session=session_handle)
            except Exception as exc:
                if acc is not None:
                    await report_risk(session_factory, acc.id, now=now_fn())
                log.error("platform_failed", product_id=product.id, platform=platform, error=str(exc))
                platforms_failed += 1
                continue
        # 合并后按 (platform, offer_id) 去重，避免同一 provider 的图搜/关键词搜返回
        # 相同候选导致重复 (task_id, ozon_product_id, platform, offer_id) 撞唯一约束
        seen_key: set[tuple[str, str]] = set()
        deduped = []
        for d in merged:
            key = (d.platform, d.offer_id)
            if key in seen_key:
                continue
            seen_key.add(key)
            deduped.append(d)
        try:
            # 跨平台候选一次性入库，才能让 CLIP 聚簇正确识别不同平台间的近似重复
            # (account_id=None：每条候选来自哪个账号在合并后已不可追溯，仅作审计用途，允许为空)
            async with session_factory() as s:
                r = await dedup_and_upsert(s, task_id, product.id, deduped, embedder, account_id=None)
                await s.commit()
            total_candidates += r["inserted"]
            async with session_factory() as s:
                task = (await s.execute(select(CollectTask).where(CollectTask.id == task_id))).scalar_one()
                task.match_cursor = {"last_product_id": product.id}
                task.match_stats = {
                    "products": prior_stats.get("products", 0) + total_products + 1,
                    "candidates": total_candidates,
                    "platforms_skipped": platforms_skipped,
                    "platforms_failed": platforms_failed,
                }
                paused = task.match_status == "paused"
                await s.commit()
        except Exception as exc:
            # DB 层失败(去重入库/游标写入)：记录日志并置 failed，保留已提交的 cursor/stats 供人工排查后续跑（spec §4.2.6）
            log.error("match_failed", product_id=product.id, error=str(exc))
            async with session_factory() as s:
                task = (await s.execute(select(CollectTask).where(CollectTask.id == task_id))).scalar_one()
                task.match_status = "failed"
                await s.commit()
            break
        last_id = product.id
        total_products += 1
        if progress_cb:
            await progress_cb({"task_id": task_id, "product_id": product.id, "candidates": total_candidates})
        if paused:
            break
    return {
        "products": prior_stats.get("products", 0) + total_products,
        "candidates": total_candidates,
        "platforms_skipped": platforms_skipped,
        "platforms_failed": platforms_failed,
    }


async def run_match(ctx, task_id: int) -> dict:
    """ARQ 任务入口：包装 run_match_core，使用真实 DB session 工厂 + 生产 provider/embedder。

    embedder 按 `settings.embedder`（环境变量 `EMBEDDER`，默认 mock）切换：mock 无需
    torch 即可跑通，clip 需要 worker 镜像以 `INSTALL_ML=true` 构建并安装 `[ml]` 组。
    """
    from app.core.db import async_session
    from app.core.config import settings
    from app.services.embedding.factory import get_embedder
    return await run_match_core(async_session, task_id, embedder=get_embedder(settings.embedder))

"""评分 worker：给任务候选算五维分（先给 Ozon 主图算向量，已算则跳过）；断点续传/暂停/失败。"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.logging import get_logger
from app.services.scoring import score_candidate
from app.models import CollectTask, OzonProduct, SupplyCandidate


async def run_score_core(session_factory: async_sessionmaker, task_id: int, *, embedder, llm,
                         weights=None, thresholds=None, max_products=None, progress_cb=None) -> dict:
    """纯函数核心：按商品遍历（score_cursor 断点续传），缺主图向量的先算好写回 Ozon 商品，
    再给该商品下每个候选算五维分并写回；商品级异常置 failed，暂停后停止但保留游标供续跑。

    统计量（products/candidates_scored）与 M2 matcher 一致做成累计值：本轮基于
    `score_stats` 里已有的历史值继续累加，使续跑/暂停恢复后的统计仍是全任务口径。
    """
    log = get_logger(task_id=task_id, phase="score")
    async with session_factory() as s:
        task = (await s.execute(select(CollectTask).where(CollectTask.id == task_id))).scalar_one()
        last_id = (task.score_cursor or {}).get("last_product_id", 0)
        prev = task.score_stats or {}
        task.score_status = "running"
        await s.commit()

    total_products = 0  # 本轮(this-run)已处理商品数，用于 max_products 断点守卫
    total_scored = prev.get("candidates_scored", 0)

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
                task.score_status = "done"
                task.score_stats = {
                    "products": prev.get("products", 0) + total_products,
                    "candidates_scored": total_scored,
                }
                await s.commit()
            break
        paused = False
        try:
            async with session_factory() as s:
                prod = (await s.execute(select(OzonProduct).where(OzonProduct.id == product.id))).scalar_one()
                if prod.embedding is None and prod.main_image_url:
                    prod.embedding = await embedder.embed_image(prod.main_image_url)
                ozon_emb = prod.embedding
                ozon_title = prod.title
                ozon_attrs = prod.attributes or {}
                cands = (await s.execute(select(SupplyCandidate).where(
                    SupplyCandidate.ozon_product_id == product.id))).scalars().all()
                for cand in cands:
                    r = await score_candidate(ozon_emb, ozon_title, ozon_attrs, cand, llm=llm,
                                              weights=weights, thresholds=thresholds)
                    cand.score_image = r.image
                    cand.score_title = r.title
                    cand.score_attr = r.attr
                    cand.score_price = r.price
                    cand.score_supplier = r.supplier
                    cand.score_total = r.total
                    cand.tier = r.tier
                    cand.score_detail = r.detail
                    total_scored += 1
                await s.commit()
            async with session_factory() as s:
                task = (await s.execute(select(CollectTask).where(CollectTask.id == task_id))).scalar_one()
                task.score_cursor = {"last_product_id": product.id}
                task.score_stats = {
                    "products": prev.get("products", 0) + total_products + 1,
                    "candidates_scored": total_scored,
                }
                paused = task.score_status == "paused"
                await s.commit()
        except Exception as exc:
            log.error("score_failed", product_id=product.id, error=str(exc))
            async with session_factory() as s:
                task = (await s.execute(select(CollectTask).where(CollectTask.id == task_id))).scalar_one()
                task.score_status = "failed"
                await s.commit()
            break
        last_id = product.id
        total_products += 1
        if progress_cb:
            await progress_cb({"task_id": task_id, "product_id": product.id, "scored": total_scored})
        if paused:
            break
    return {
        "products": prev.get("products", 0) + total_products,
        "candidates_scored": total_scored,
    }


async def run_score(ctx, task_id: int) -> dict:
    """ARQ 任务入口：包装 run_score_core，使用真实 DB session 工厂 + 配置选定的 embedder/LLM。"""
    from app.core.db import async_session
    from app.core.config import settings
    from app.services.embedding.factory import get_embedder
    from app.services.llm.factory import get_llm
    return await run_score_core(async_session, task_id,
                                embedder=get_embedder(settings.embedder),
                                llm=get_llm(settings.llm_provider))

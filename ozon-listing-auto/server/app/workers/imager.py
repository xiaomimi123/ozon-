"""改图 worker(§5.6 仅自建)：对 create 任务已采用候选源图跑改图流水线 → product_images，单图失败隔离。"""
import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker
from app.core.logging import get_logger
from app.services.imagegen.factory import process_op, DEFAULT_STATIC_DIR
from app.models import SupplyCandidate, ProductImage

DEFAULT_OPS = ["whitebg", "crop_norm"]


def _default_fetch(url: str) -> bytes:
    return httpx.get(url, timeout=20).content


async def run_image_process_core(session_factory: async_sessionmaker, task_id: int, *, ops=None,
                                 static_dir: str | None = None, gen_provider: str = "mock", fetch=None) -> dict:
    log = get_logger(task_id=task_id, phase="imager")
    ops = ops or DEFAULT_OPS
    static_dir = static_dir or DEFAULT_STATIC_DIR
    fetch = fetch or _default_fetch
    async with session_factory() as s:
        cands = (await s.execute(select(SupplyCandidate).where(
            SupplyCandidate.task_id == task_id, SupplyCandidate.status.in_(("adopted", "auto_adopted"))
        ))).scalars().all()
        jobs = [(c.id, c.image_url) for c in cands if c.image_url]
    processed = failed = 0
    sort = 0
    for cand_id, src in jobs:
        for op in ops:
            async with session_factory() as s:
                row = ProductImage(task_id=task_id, candidate_id=cand_id, source_url=src, op=op,
                                   provider="local", sort=sort, status="processing")
                s.add(row); await s.flush()
                try:
                    img_bytes = fetch(src)
                    res = await process_op(op, image=img_bytes, params={}, static_dir=static_dir, gen_provider=gen_provider)
                    row.result_url = res.url; row.provider = res.provider; row.meta = res.meta; row.status = "done"
                    processed += 1
                except Exception as exc:  # noqa: BLE001
                    err = str(exc) or exc.__class__.__name__
                    log.error("image_process_failed", candidate_id=cand_id, op=op, error=err)
                    row.status = "failed"; row.error = err; failed += 1
                await s.commit()
            sort += 1
    return {"processed": processed, "failed": failed}


async def run_image_process(ctx, task_id: int) -> dict:
    """ARQ 入口：真实 worker 路径，用默认 fetch(httpx 下载源图) + 默认 static_dir + mock gen provider。"""
    from app.core.db import async_session
    return await run_image_process_core(async_session, task_id)

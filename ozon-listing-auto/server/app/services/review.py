"""审核服务：review_config 自动采用 / 审核队列 / 采用拒绝决策 / Redis 并发锁。"""
from contextlib import asynccontextmanager
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import CollectTask, OzonProduct, SupplyCandidate, ReviewDecision

@asynccontextmanager
async def _noop_lock():
    yield

def review_lock(product_id: int):
    return _noop_lock()   # 生产替换为 Redis 锁

async def apply_auto_adopt(session: AsyncSession, task_id: int) -> dict:
    task = (await session.execute(select(CollectTask).where(CollectTask.id == task_id))).scalar_one()
    rc = task.review_config or {}
    if rc.get("source_review_required", True):
        return {"auto_adopted": 0}
    smin = rc.get("source_score_min")
    conds = [SupplyCandidate.task_id == task_id, SupplyCandidate.status == "candidate"]
    if smin is not None:
        conds.append(SupplyCandidate.score_total >= smin)
    cands = (await session.execute(select(SupplyCandidate).where(*conds))).scalars().all()
    n = 0
    for c in cands:
        c.status = "auto_adopted"
        session.add(ReviewDecision(task_id=task_id, ozon_product_id=c.ozon_product_id,
                                   candidate_id=c.id, reviewer_id=None, decision="auto_adopt"))
        n += 1
    return {"auto_adopted": n}

async def get_review_queue(session: AsyncSession, task_id: int, page: int = 1, page_size: int = 20) -> dict:
    prod_ids = (await session.execute(
        select(SupplyCandidate.ozon_product_id).where(
            SupplyCandidate.task_id == task_id, SupplyCandidate.status == "candidate"
        ).distinct().order_by(SupplyCandidate.ozon_product_id).offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()
    total = (await session.execute(
        select(SupplyCandidate.ozon_product_id).where(
            SupplyCandidate.task_id == task_id, SupplyCandidate.status == "candidate").distinct()
    )).scalars().all()
    items = []
    for pid in prod_ids:
        prod = (await session.execute(select(OzonProduct).where(OzonProduct.id == pid))).scalar_one()
        cands = (await session.execute(select(SupplyCandidate).where(
            SupplyCandidate.ozon_product_id == pid, SupplyCandidate.status == "candidate"
        ).order_by(SupplyCandidate.score_total.desc().nulls_last()))).scalars().all()
        items.append({
            "product": {"id": prod.id, "sku": prod.sku, "title": prod.title,
                        "main_image_url": prod.main_image_url, "price": prod.price},
            "candidates": [{"id": c.id, "platform": c.platform, "offer_id": c.offer_id, "title": c.title,
                            "price": c.price, "image_url": c.image_url, "supplier_name": c.supplier_name,
                            "score_total": c.score_total, "tier": c.tier,
                            "scores": {"image": c.score_image, "title": c.score_title, "attr": c.score_attr,
                                       "price": c.score_price, "supplier": c.score_supplier}} for c in cands],
        })
    return {"items": items, "total": len(total)}

async def decide(session: AsyncSession, candidate_id: int, reviewer_id: int | None,
                 decision: str, note: str | None = None, *, lock=None) -> dict:
    if decision not in ("adopt", "reject"):
        raise ValueError(f"非法审核决策: {decision}")
    cand = (await session.execute(select(SupplyCandidate).where(SupplyCandidate.id == candidate_id))).scalar_one()
    lock = lock or review_lock(cand.ozon_product_id)
    async with lock:
        cand.status = "adopted" if decision == "adopt" else "rejected"
        session.add(ReviewDecision(task_id=cand.task_id, ozon_product_id=cand.ozon_product_id,
                                   candidate_id=cand.id, reviewer_id=reviewer_id, decision=decision, note=note))
    return {"candidate_id": candidate_id, "status": cand.status}

"""货源候选入库：CLIP 向量贪心聚簇跨平台去重 + 幂等 upsert。"""
import math
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.sources.base import SupplyCandidateDTO
from app.models import SupplyCandidate

def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)); nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)

def cluster_by_similarity(embeddings: list[list[float]], threshold: float) -> list[int]:
    """贪心聚簇：每条与已有簇代表比余弦，>阈值归入该簇，否则新簇。返回每条的簇号。"""
    reps: list[tuple[int, list[float]]] = []   # (group_id, rep_vec)
    groups: list[int] = []
    for emb in embeddings:
        assigned = None
        if emb is not None:
            for gid, rep in reps:
                if _cosine(emb, rep) >= threshold:
                    assigned = gid
                    break
        if assigned is None:
            assigned = len(reps)
            reps.append((assigned, emb if emb is not None else []))
        groups.append(assigned)
    return groups

async def dedup_and_upsert(session: AsyncSession, task_id: int, ozon_product_id: int,
                           dtos: list[SupplyCandidateDTO], embedder, *,
                           threshold: float = 0.92, account_id: int | None = None) -> dict:
    embeddings = [await embedder.embed_image(d.image_url) if d.image_url else None for d in dtos]
    groups = cluster_by_similarity(embeddings, threshold)
    seen_rep: set[int] = set()
    inserted = skipped = 0
    for d, emb, gid in zip(dtos, embeddings, groups):
        exists = (await session.execute(select(SupplyCandidate.id).where(
            SupplyCandidate.task_id == task_id, SupplyCandidate.ozon_product_id == ozon_product_id,
            SupplyCandidate.platform == d.platform, SupplyCandidate.offer_id == d.offer_id))).scalar_one_or_none()
        if exists:
            skipped += 1
            continue
        is_rep = gid not in seen_rep
        seen_rep.add(gid)
        session.add(SupplyCandidate(
            task_id=task_id, ozon_product_id=ozon_product_id, platform=d.platform, offer_id=d.offer_id,
            title=d.title, price=d.price, currency=d.currency, quantity_begin=d.quantity_begin,
            quantity_prices=d.quantity_prices, image_url=d.image_url, images=d.images, phash=d.phash,
            embedding=emb, detail_url=d.detail_url, supplier_name=d.supplier_name, supplier_info=d.supplier_info,
            dedup_group=gid, is_representative=is_rep, source_account_id=account_id, raw=d.raw,
        ))
        inserted += 1
    return {"inserted": inserted, "skipped": skipped, "clusters": len(set(groups))}

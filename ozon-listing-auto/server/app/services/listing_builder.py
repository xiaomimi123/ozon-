"""跟卖草稿生成：已采用候选 + 定价 → listing_drafts(§5.9)。"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.pricing import price_candidate, DEFAULT_PRICING
from app.models import OzonProduct, SupplyCandidate, ListingDraft

async def build_follow_drafts(session: AsyncSession, task_id: int, *, params: dict | None = None, shop_id: int | None = None) -> dict:
    p = params or DEFAULT_PRICING
    cands = (await session.execute(select(SupplyCandidate).where(
        SupplyCandidate.task_id == task_id, SupplyCandidate.status.in_(("adopted", "auto_adopted"))
    ))).scalars().all()
    built = blocked = skipped = 0
    for c in cands:
        exists = (await session.execute(select(ListingDraft.id).where(
            ListingDraft.task_id == task_id, ListingDraft.candidate_id == c.id))).scalar_one_or_none()
        if exists:
            skipped += 1
            continue
        ozon = (await session.execute(select(OzonProduct).where(OzonProduct.id == c.ozon_product_id))).scalar_one()
        pr = price_candidate(float(c.price) if c.price is not None else 0.0, ozon.weight, p)
        status = "below_min" if pr.blocked else "draft"
        if pr.blocked:
            blocked += 1
        session.add(ListingDraft(
            task_id=task_id, ozon_product_id=ozon.id, candidate_id=c.id, shop_id=shop_id, mode="follow",
            target_ozon_sku=ozon.sku, barcode=ozon.barcode, price=pr.price, currency="RUB",
            stock_qty=0, cost=pr.cost, margin=pr.margin, pricing_detail=pr.detail, status=status))
        built += 1
    return {"built": built, "blocked": blocked, "skipped": skipped}

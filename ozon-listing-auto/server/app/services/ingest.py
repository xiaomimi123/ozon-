"""归集服务：同批次去重（sku/phash）与按 (task_id, sku) 幂等 upsert 入库。"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.ozon_market.base import OzonProductDTO
from app.models import OzonProduct

def dedup(dtos: list[OzonProductDTO]) -> list[OzonProductDTO]:
    seen_sku: set[str] = set()
    seen_phash: set[str] = set()
    out: list[OzonProductDTO] = []
    for d in dtos:
        if d.sku in seen_sku:
            continue
        if d.phash and d.phash in seen_phash:
            continue
        seen_sku.add(d.sku)
        if d.phash:
            seen_phash.add(d.phash)
        out.append(d)
    return out

async def upsert_products(s: AsyncSession, task_id: int, dtos: list[OzonProductDTO]) -> dict:
    inserted = skipped = 0
    for d in dedup(dtos):
        exists = (await s.execute(
            select(OzonProduct.id).where(OzonProduct.task_id == task_id, OzonProduct.sku == d.sku)
        )).scalar_one_or_none()
        if exists:
            skipped += 1
            continue
        s.add(OzonProduct(
            task_id=task_id, sku=d.sku, product_url=d.product_url, title=d.title,
            price=d.price, currency=d.currency, sales_monthly=d.sales_monthly, rating=d.rating,
            reviews_count=d.reviews_count, weight=d.weight, listed_at=d.listed_at,
            follow_count=d.follow_count, return_rate=d.return_rate, main_image_url=d.main_image_url,
            images=d.images, attributes=d.attributes, parent_sku=d.parent_sku, phash=d.phash, raw=d.raw,
        ))
        inserted += 1
    return {"inserted": inserted, "skipped": skipped}

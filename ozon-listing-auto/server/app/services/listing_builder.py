"""跟卖/自建草稿生成：已采用候选 + 定价(+ 自建的译标题/类目/图片) → listing_drafts(§5.9)。"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.pricing import price_candidate, DEFAULT_PRICING
from app.models import OzonProduct, SupplyCandidate, ListingDraft, ProductImage
from app.services.category_map import suggest_category
from app.services.category_tree import get_category_tree
from app.services.llm.factory import get_llm

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


async def build_create_drafts(session: AsyncSession, task_id: int, *, params: dict | None = None,
                              shop_id: int | None = None, llm=None, tree=None) -> dict:
    """自建草稿生成(§5.9 create)：已采用候选 → 译标题 + 定价 + 类目属性建议 + 已确认图 → listing_drafts(mode=create)。
    按 (task_id, candidate_id) 幂等；无 approved 图则 images=[] 待前端补。"""
    p = params or DEFAULT_PRICING
    llm = llm or get_llm("mock")
    tree = tree or get_category_tree("mock")
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
        ozon = (await session.execute(select(OzonProduct).where(OzonProduct.id == c.ozon_product_id))).scalar_one_or_none()
        weight = ozon.weight if ozon else None
        pr = price_candidate(float(c.price) if c.price is not None else 0.0, weight, p)
        title = await llm.translate(c.title or "", target_lang="ru")
        cat = await suggest_category(session, c, llm=llm, tree=tree)
        imgs = (await session.execute(select(ProductImage.result_url).where(
            ProductImage.candidate_id == c.id, ProductImage.status == "approved"
        ).order_by(ProductImage.sort))).scalars().all()
        status = "below_min" if pr.blocked else "draft"
        if pr.blocked:
            blocked += 1
        session.add(ListingDraft(
            task_id=task_id, ozon_product_id=(ozon.id if ozon else None), candidate_id=c.id, shop_id=shop_id,
            mode="create", title=title, description=title, category_id=cat.get("category_id"),
            attributes=cat.get("attributes") or {}, images=[u for u in imgs if u],
            price=pr.price, currency="RUB", stock_qty=0, cost=pr.cost, margin=pr.margin,
            pricing_detail={**pr.detail, "category_source": cat.get("source")}, status=status))
        built += 1
    return {"built": built, "blocked": blocked, "skipped": skipped}

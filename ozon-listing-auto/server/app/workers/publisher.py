"""跟卖上架 worker(follow 分支)：自动确认 + 确认草稿挂靠→回写(§5.9)。M4 直接挂靠, 无节奏。"""
import json
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
from app.core.logging import get_logger
from app.core.crypto import decrypt
from app.services.ozon_seller.factory import get_ozon_seller
from app.models import CollectTask, SupplyCandidate, ListingDraft, Shop

async def apply_auto_confirm(session: AsyncSession, task_id: int) -> dict:
    task = (await session.execute(select(CollectTask).where(CollectTask.id == task_id))).scalar_one()
    rc = task.review_config or {}
    if rc.get("listing_review_required", True):
        return {"confirmed": 0}
    smin = rc.get("listing_score_min")
    drafts = (await session.execute(select(ListingDraft).where(
        ListingDraft.task_id == task_id, ListingDraft.status == "draft"))).scalars().all()
    n = 0
    for d in drafts:
        if smin is not None:
            cand = (await session.execute(select(SupplyCandidate).where(SupplyCandidate.id == d.candidate_id))).scalar_one()
            if cand.score_total is None or float(cand.score_total) < smin:
                continue
        d.status = "confirmed"
        n += 1
    return {"confirmed": n}

async def confirm_draft(session: AsyncSession, draft_id: int) -> dict:
    d = (await session.execute(select(ListingDraft).where(ListingDraft.id == draft_id))).scalar_one()
    if d.status in ("draft",):
        d.status = "confirmed"
    return {"draft_id": draft_id, "status": d.status}

async def run_publish_core(session_factory: async_sessionmaker, task_id: int, *, seller,
                           max_drafts=None, progress_cb=None) -> dict:
    log = get_logger(task_id=task_id, phase="publish")
    published = failed = 0
    async with session_factory() as s:
        drafts = (await s.execute(select(ListingDraft).where(
            ListingDraft.task_id == task_id, ListingDraft.status == "confirmed"))).scalars().all()
        draft_ids = [d.id for d in drafts]
    for i, did in enumerate(draft_ids):
        if max_drafts is not None and i >= max_drafts:
            break
        async with session_factory() as s:
            d = (await s.execute(select(ListingDraft).where(ListingDraft.id == did))).scalar_one()
            shop = (await s.execute(select(Shop).where(Shop.id == d.shop_id))).scalar_one_or_none() if d.shop_id else None
            client_id = shop.client_id if shop else ""
            api_key = decrypt(shop.api_key_encrypted) if shop else ""
            try:
                res = await seller.create_follow_offer(
                    client_id=client_id, api_key=api_key, target_sku=d.target_ozon_sku, barcode=d.barcode,
                    price=float(d.price) if d.price is not None else 0.0, stock=d.stock_qty,
                    offer_id=str((await s.execute(select(SupplyCandidate.offer_id).where(SupplyCandidate.id == d.candidate_id))).scalar_one()))
                if res.ok:
                    d.status = "published"; d.ozon_result = {"ozon_product_id": res.ozon_product_id, "status": res.status}
                    published += 1
                else:
                    d.status = "failed"; d.error = res.error; failed += 1
            except Exception as exc:  # noqa: BLE001
                log.error("publish_failed", draft_id=did, error=str(exc))
                d.status = "failed"; d.error = str(exc); failed += 1
            await s.commit()
        if progress_cb:
            await progress_cb({"task_id": task_id, "draft_id": did, "published": published, "failed": failed})
    return {"published": published, "failed": failed}

async def run_publish(ctx, task_id: int) -> dict:
    from app.core.db import async_session
    return await run_publish_core(async_session, task_id, seller=get_ozon_seller("mock"))

"""跟卖上架 worker(follow 分支)：自动确认 + 确认草稿挂靠→回写(§5.9)。
M4：直接挂靠, 无节奏。M5：tick_publish 按节奏逐一挂靠, 等审核门后再推进下一条。"""
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
from app.core.logging import get_logger
from app.core.crypto import decrypt
from app.core.progress import broadcaster
from app.services.publish_scheduler import get_pace
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
    if d.mode == "create":
        if d.category_id is None or not d.images:
            return {"draft_id": draft_id, "status": d.status, "error": "自建草稿需先确认类目与图片再确认上架"}
        if d.type_id is None or None in (d.depth, d.width, d.height, d.weight):
            return {"draft_id": draft_id, "status": d.status, "error": "自建缺类型或尺寸/重量, 请先补充"}
    if d.status in ("draft",):
        d.status = "confirmed"
    return {"draft_id": draft_id, "status": d.status}

async def _call_seller(seller, d, offer_id: str, *, client_id: str, api_key: str):
    """按 draft.mode 分派 Ozon 写入：create → create_product；follow → create_follow_offer(§5.9)。"""
    price = float(d.price) if d.price is not None else 0.0
    if d.mode == "create":
        return await seller.create_product(
            client_id=client_id, api_key=api_key, offer_id=offer_id, title=d.title or "",
            description=d.description or "", category_id=d.category_id, attributes=d.attributes or {},
            images=d.images or [], price=price, stock=d.stock_qty, barcode=d.barcode,
            type_id=d.type_id, depth=d.depth, width=d.width, height=d.height,
            weight=d.weight, dimension_unit=d.dimension_unit, weight_unit=d.weight_unit)
    return await seller.create_follow_offer(
        client_id=client_id, api_key=api_key, target_sku=d.target_ozon_sku, barcode=d.barcode,
        price=price, stock=d.stock_qty, offer_id=offer_id)

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
            try:
                shop = (await s.execute(select(Shop).where(Shop.id == d.shop_id))).scalar_one_or_none() if d.shop_id else None
                client_id = shop.client_id if shop else ""
                api_key = decrypt(shop.api_key_encrypted) if shop else ""
                offer_id = str((await s.execute(select(SupplyCandidate.offer_id).where(SupplyCandidate.id == d.candidate_id))).scalar_one())
                res = await _call_seller(seller, d, offer_id, client_id=client_id, api_key=api_key)
                if res.ok:
                    d.status = "published"
                    d.ozon_result = {"ozon_product_id": res.ozon_product_id, "status": res.status, "raw": res.raw}
                    published += 1
                else:
                    d.status = "failed"; d.error = res.error; failed += 1
            except Exception as exc:  # noqa: BLE001  单条草稿失败不影响其他草稿(§4.2.6)
                err = str(exc) or exc.__class__.__name__  # 部分异常(如 InvalidToken)str() 为空, 兜底用类名
                log.error("publish_failed", draft_id=did, error=err)
                d.status = "failed"; d.error = err; failed += 1
            await s.commit()
        if progress_cb:
            await progress_cb({"task_id": task_id, "draft_id": did, "published": published, "failed": failed})
    return {"published": published, "failed": failed}

async def run_publish(ctx, task_id: int) -> dict:
    from app.core.db import async_session
    from app.services.ozon_seller.resolve import resolve_seller
    async with async_session() as s:
        seller = await resolve_seller(s)
    return await run_publish_core(async_session, task_id, seller=seller)

async def tick_publish(session_factory, task_id: int, *, seller, now, max_batch: int = 1) -> dict:
    """按节奏逐一挂靠(§5.9)：先过"等审核门"(轮询上一批 pending_review 的 Ozon 审核状态),
    有任一条仍在审核中则本轮不推进下一条；否则取下一条到期 scheduled 草稿挂靠。
    每条草稿独立 session + try/except 隔离(单条失败不影响其他草稿, 对齐 run_publish_core)。"""
    log = get_logger(task_id=task_id, phase="publish_tick")
    published = pending_review = failed = 0
    waiting = False
    async with session_factory() as s:
        pace = await get_pace(s, task_id)
    wait_approval = pace.get("wait_ozon_approval", True)
    # 1) 等审核门：轮询已提交待审的草稿, 有任一条未出结果则本轮不再推进下一条
    if wait_approval:
        async with session_factory() as s:
            pend = (await s.execute(select(ListingDraft).where(
                ListingDraft.task_id == task_id, ListingDraft.status == "pending_review"))).scalars().all()
            pend_ids = [d.id for d in pend]
        for did in pend_ids:
            async with session_factory() as s:
                d = (await s.execute(select(ListingDraft).where(ListingDraft.id == did))).scalar_one()
                shop = (await s.execute(select(Shop).where(Shop.id == d.shop_id))).scalar_one_or_none() if d.shop_id else None
                ozon_id = (d.ozon_result or {}).get("ozon_product_id", "")
                try:
                    st = await seller.get_product_status(
                        client_id=(shop.client_id if shop else ""),
                        api_key=(decrypt(shop.api_key_encrypted) if shop else ""), ozon_product_id=ozon_id)
                except Exception as exc:  # noqa: BLE001  查询失败按"仍在审核中"处理, 不误判成功/失败
                    st = "pending"; log.error("status_poll_failed", draft_id=did, error=str(exc))
                if st == "approved":
                    d.status = "published"; published += 1
                elif st == "rejected":
                    d.status = "failed"; d.error = "ozon rejected"; failed += 1
                else:
                    waiting = True
                await s.commit()
        if waiting:
            return {"published": 0, "pending_review": 0, "failed": 0, "waiting": True}
    # 2) 取下一条到期 scheduled 草稿(按 scheduled_at 排序, 限 max_batch 条)
    async with session_factory() as s:
        due = (await s.execute(select(ListingDraft).where(
            ListingDraft.task_id == task_id, ListingDraft.status == "scheduled",
            ListingDraft.scheduled_at <= now).order_by(ListingDraft.scheduled_at).limit(max_batch))).scalars().all()
        due_ids = [d.id for d in due]
    for did in due_ids:
        async with session_factory() as s:
            d = (await s.execute(select(ListingDraft).where(ListingDraft.id == did))).scalar_one()
            try:
                shop = (await s.execute(select(Shop).where(Shop.id == d.shop_id))).scalar_one_or_none() if d.shop_id else None
                offer_id = str((await s.execute(select(SupplyCandidate.offer_id).where(SupplyCandidate.id == d.candidate_id))).scalar_one())
                res = await _call_seller(seller, d, offer_id,
                    client_id=(shop.client_id if shop else ""),
                    api_key=(decrypt(shop.api_key_encrypted) if shop else ""))
                if res.ok:
                    d.ozon_result = {"ozon_product_id": res.ozon_product_id, "status": res.status, "raw": res.raw}
                    d.status = "pending_review" if wait_approval else "published"
                    if wait_approval:
                        pending_review += 1
                    else:
                        published += 1
                else:
                    d.status = "failed"; d.error = res.error; failed += 1
            except Exception as exc:  # noqa: BLE001  单条草稿失败不影响其他草稿(§4.2.6)
                err = str(exc) or exc.__class__.__name__
                log.error("publish_failed", draft_id=did, error=err)
                d.status = "failed"; d.error = err; failed += 1
            await s.commit()
        await broadcaster.publish({"task_id": task_id, "draft_id": did, "phase": "publish",
                                   "published": published, "pending_review": pending_review, "failed": failed})
    return {"published": published, "pending_review": pending_review, "failed": failed, "waiting": False}

async def run_publish_tick(ctx) -> dict:
    """ARQ cron 入口：扫描所有有到期 scheduled 或待审 pending_review 草稿的任务, 逐个 tick(真实 seller 按配置)。"""
    from app.core.db import async_session
    from app.services.ozon_seller.resolve import resolve_seller
    now = datetime.now(timezone.utc)
    async with async_session() as s:
        task_ids = (await s.execute(select(ListingDraft.task_id).where(
            ListingDraft.status.in_(("scheduled", "pending_review"))).distinct())).scalars().all()
    async with async_session() as s:
        seller = await resolve_seller(s)
    total = {"published": 0, "pending_review": 0, "failed": 0}
    for tid in task_ids:
        r = await tick_publish(async_session, tid, seller=seller, now=now)
        for k in total:
            total[k] += r.get(k, 0)
    return total

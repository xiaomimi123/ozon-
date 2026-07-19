"""上架 API：生成草稿/列表/确认/自动确认/挂靠/监控。"""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
import app.core.db as dbmod
from app.core.db import get_session
from app.api.deps import require_role, get_current_user
from app.models import CollectTask, ListingDraft, User
from app.schemas.listing import DraftOut
from app.services.listing_builder import build_follow_drafts
from app.services.pricing import DEFAULT_PRICING
from app.services.settings_store import get_category
from app.services.category_tree import build_category_tree
from app.workers.publisher import apply_auto_confirm, confirm_draft, run_publish_core
from app.services.ozon_seller.resolve import resolve_seller

router = APIRouter(prefix="/listing", tags=["listing"])


class CreateFieldsIn(BaseModel):
    """自建草稿补充信息回写：type_id + 尺寸/重量(confirm_draft 必填校验用)。"""
    type_id: int
    depth: int
    width: int
    height: int
    weight: int
    dimension_unit: str = "mm"
    weight_unit: str = "g"
    attributes: dict | None = None

async def _pricing_params(s: AsyncSession) -> dict:
    stored = await get_category(s, "pricing")
    params = {**DEFAULT_PRICING}
    for k, v in stored.items():   # 存的是字符串, 数值字段转 float
        if k in ("mode", "formula"):
            params[k] = v
        else:
            try: params[k] = float(v)
            except (TypeError, ValueError): pass
    return params

@router.post("/build")
async def listing_build(task_id: int, shop_id: int | None = None, s: AsyncSession = Depends(get_session), _: User = Depends(require_role("operator"))):
    t = (await s.execute(select(CollectTask).where(CollectTask.id == task_id))).scalar_one_or_none()
    if not t:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "任务不存在")
    params = await _pricing_params(s)
    if t.listing_mode == "create":
        from app.services.listing_builder import build_create_drafts
        from app.services.llm.config import get_configured_llm
        name = (await get_category(s, "system")).get("category_tree_provider", "mock")
        r = await build_create_drafts(s, task_id, params=params, shop_id=shop_id, llm=await get_configured_llm(s),
                                      tree=await build_category_tree(s, name))
    else:
        r = await build_follow_drafts(s, task_id, params=params, shop_id=shop_id)
    await s.commit()
    return r

@router.get("/drafts", response_model=list[DraftOut])
async def listing_drafts(task_id: int, status: str | None = None, s: AsyncSession = Depends(get_session), _: User = Depends(get_current_user)):
    conds = [ListingDraft.task_id == task_id]
    if status:
        conds.append(ListingDraft.status == status)
    rows = (await s.execute(select(ListingDraft).where(*conds).order_by(ListingDraft.id.desc()))).scalars().all()
    return [DraftOut.model_validate(r) for r in rows]

@router.post("/{draft_id}/confirm")
async def listing_confirm(draft_id: int, s: AsyncSession = Depends(get_session), _: User = Depends(require_role("reviewer"))):
    d = (await s.execute(select(ListingDraft).where(ListingDraft.id == draft_id))).scalar_one_or_none()
    if not d:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "草稿不存在")
    r = await confirm_draft(s, draft_id); await s.commit()
    return r

@router.post("/{draft_id}/confirm-create-fields")
async def confirm_create_fields(draft_id: int, body: CreateFieldsIn, s: AsyncSession = Depends(get_session), _: User = Depends(require_role("operator"))):
    d = (await s.execute(select(ListingDraft).where(ListingDraft.id == draft_id))).scalar_one_or_none()
    if not d:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "草稿不存在")
    d.type_id = body.type_id; d.depth = body.depth; d.width = body.width; d.height = body.height
    d.weight = body.weight; d.dimension_unit = body.dimension_unit; d.weight_unit = body.weight_unit
    if body.attributes is not None:
        merged = dict(d.attributes or {}); merged.update({str(k): v for k, v in body.attributes.items()})
        d.attributes = merged
    await s.commit()
    return {"ok": True}

@router.post("/auto-confirm")
async def listing_auto_confirm(task_id: int, s: AsyncSession = Depends(get_session), _: User = Depends(require_role("operator"))):
    t = (await s.execute(select(CollectTask).where(CollectTask.id == task_id))).scalar_one_or_none()
    if not t:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "任务不存在")
    r = await apply_auto_confirm(s, task_id); await s.commit()
    return r

@router.post("/publish")
async def listing_publish(task_id: int, sync: bool = False, s: AsyncSession = Depends(get_session), _: User = Depends(require_role("publisher"))):
    t = (await s.execute(select(CollectTask).where(CollectTask.id == task_id))).scalar_one_or_none()
    if not t:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "任务不存在")
    if sync:
        r = await run_publish_core(dbmod.async_session, task_id, seller=await resolve_seller(s))
        return r
    from arq import create_pool
    from arq.connections import RedisSettings
    from app.core.config import settings
    pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    try:
        await pool.enqueue_job("run_publish", task_id)
    finally:
        await pool.aclose()
    return {"status": "queued"}

@router.get("/monitor")
async def listing_monitor(task_id: int, s: AsyncSession = Depends(get_session), _: User = Depends(get_current_user)):
    rows = (await s.execute(select(ListingDraft.status, func.count()).where(
        ListingDraft.task_id == task_id).group_by(ListingDraft.status))).all()
    return {"counts": {status_: cnt for status_, cnt in rows}}

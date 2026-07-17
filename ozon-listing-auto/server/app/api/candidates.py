"""货源候选查询 API（分页/按平台/仅代表）。"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.db import get_session
from app.api.deps import get_current_user
from app.models import SupplyCandidate, User
from app.schemas.candidate import CandidateOut

router = APIRouter(prefix="/candidates", tags=["candidates"])

@router.get("")
async def list_candidates(task_id: int, ozon_product_id: int | None = None, platform: str | None = None,
                          only_representative: bool = False, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=200),
                          s: AsyncSession = Depends(get_session), _: User = Depends(get_current_user)):
    conds = [SupplyCandidate.task_id == task_id]
    if ozon_product_id is not None:
        conds.append(SupplyCandidate.ozon_product_id == ozon_product_id)
    if platform:
        conds.append(SupplyCandidate.platform == platform)
    if only_representative:
        conds.append(SupplyCandidate.is_representative.is_(True))
    base = select(SupplyCandidate).where(*conds)
    total = (await s.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    rows = (await s.execute(base.order_by(SupplyCandidate.id.desc()).offset((page-1)*page_size).limit(page_size))).scalars().all()
    return {"items": [CandidateOut.model_validate(r) for r in rows], "total": total}

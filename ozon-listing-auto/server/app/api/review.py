"""审核台 API：队列 / 采用拒绝决策 / 自动采用。"""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.db import get_session
from app.api.deps import require_role
from app.models import CollectTask, SupplyCandidate, User
from app.schemas.review import DecisionIn
from app.services.review import get_review_queue, decide, apply_auto_adopt

router = APIRouter(prefix="/review", tags=["review"])

@router.get("/queue")
async def review_queue(task_id: int, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=200),
                       s: AsyncSession = Depends(get_session), _: User = Depends(require_role("reviewer"))):
    return await get_review_queue(s, task_id, page, page_size)

@router.post("/auto-adopt")
async def review_auto_adopt(task_id: int, s: AsyncSession = Depends(get_session), _: User = Depends(require_role("operator"))):
    t = (await s.execute(select(CollectTask).where(CollectTask.id == task_id))).scalar_one_or_none()
    if t is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "任务不存在")
    r = await apply_auto_adopt(s, task_id); await s.commit()
    return r

@router.post("/{candidate_id}")
async def review_decide(candidate_id: int, body: DecisionIn, s: AsyncSession = Depends(get_session), user: User = Depends(require_role("reviewer"))):
    c = (await s.execute(select(SupplyCandidate).where(SupplyCandidate.id == candidate_id))).scalar_one_or_none()
    if c is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "候选不存在")
    r = await decide(s, candidate_id, user.id, body.decision, body.note); await s.commit()
    return r

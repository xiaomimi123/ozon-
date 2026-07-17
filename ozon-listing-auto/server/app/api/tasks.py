"""任务接口：创建（operator+）、列表与详情（登录即可）。"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.db import get_session
from app.api.deps import require_role, get_current_user
from app.models import CollectTask, User
from app.schemas.task import TaskCreate, TaskOut

router = APIRouter(prefix="/tasks", tags=["tasks"])

@router.post("", response_model=TaskOut, status_code=201)
async def create_task(body: TaskCreate, s: AsyncSession = Depends(get_session), user: User = Depends(require_role("operator"))):
    if body.entry_type not in {"keyword", "category", "seller", "own_shop"}:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "非法 entry_type")
    if body.listing_mode not in {"follow", "create"}:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "非法 listing_mode")
    t = CollectTask(**body.model_dump(), created_by=user.id)
    s.add(t); await s.commit(); await s.refresh(t)
    return t

@router.get("", response_model=list[TaskOut])
async def list_tasks(s: AsyncSession = Depends(get_session), _: User = Depends(get_current_user)):
    rows = (await s.execute(select(CollectTask).order_by(CollectTask.id.desc()))).scalars().all()
    return list(rows)

@router.get("/{task_id}", response_model=TaskOut)
async def get_task(task_id: int, s: AsyncSession = Depends(get_session), _: User = Depends(get_current_user)):
    t = (await s.execute(select(CollectTask).where(CollectTask.id == task_id))).scalar_one_or_none()
    if not t:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "任务不存在")
    return t

"""节奏配置 API(operator+)：get-or-default / upsert。"""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.db import get_session
from app.api.deps import require_role
from app.models import PublishPace, User
from app.schemas.pace import PaceIn, PaceOut
from app.services.publish_scheduler import get_pace

router = APIRouter(prefix="/pace", tags=["pace"])

@router.get("", response_model=PaceOut)
async def read_pace(task_id: int | None = None, s: AsyncSession = Depends(get_session), _: User = Depends(require_role("operator"))):
    p = await get_pace(s, task_id) if task_id is not None else await get_pace(s, -1)
    return PaceOut(task_id=task_id, **p)

@router.put("", response_model=PaceOut)
async def write_pace(body: PaceIn, task_id: int | None = None, s: AsyncSession = Depends(get_session), _: User = Depends(require_role("operator"))):
    row = (await s.execute(select(PublishPace).where(PublishPace.task_id == task_id))).scalar_one_or_none()
    if not row:
        row = PublishPace(task_id=task_id); s.add(row)
    row.min_interval_sec = body.min_interval_sec; row.max_interval_sec = body.max_interval_sec
    row.daily_limit = body.daily_limit; row.active_hours = body.active_hours; row.wait_ozon_approval = body.wait_ozon_approval
    await s.commit()
    return PaceOut(task_id=task_id, **body.model_dump())

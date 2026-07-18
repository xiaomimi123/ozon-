"""改图 API(§5.6 仅自建)：触发流水线 / 列表 / 采用 / 弃用。"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.db import get_session
import app.core.db as dbmod
from app.api.deps import require_role
from app.models import ProductImage, User
from app.schemas.image import ImageOut, ProcessOut
from app.workers.imager import run_image_process_core

router = APIRouter(prefix="/images", tags=["images"])


@router.post("/process")
async def process_images(task_id: int, sync: bool = False, _: User = Depends(require_role("operator"))):
    # sync 语义同全项目规律(如 /listing/publish?sync=true)：sync=true 同步跑真实流水线(真实下载源图)供演示/测试；
    # 否则走 arq 的 run_image_process 异步任务，与 publish_tick 的分派方式一致。
    if sync:
        res = await run_image_process_core(dbmod.async_session, task_id)
        return ProcessOut(**res)
    from arq import create_pool
    from arq.connections import RedisSettings
    from app.core.config import settings
    pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    try:
        await pool.enqueue_job("run_image_process", task_id)
    finally:
        await pool.aclose()
    return {"status": "queued"}


@router.get("", response_model=list[ImageOut])
async def list_images(task_id: int, status: str | None = None, s: AsyncSession = Depends(get_session),
                      _: User = Depends(require_role("operator"))):
    q = select(ProductImage).where(ProductImage.task_id == task_id)
    if status:
        q = q.where(ProductImage.status == status)
    rows = (await s.execute(q.order_by(ProductImage.candidate_id, ProductImage.sort))).scalars().all()
    return rows


@router.post("/{image_id}/approve", response_model=ImageOut)
async def approve_image(image_id: int, s: AsyncSession = Depends(get_session),
                        _: User = Depends(require_role("reviewer"))):
    row = (await s.execute(select(ProductImage).where(ProductImage.id == image_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "图片不存在")
    row.status = "approved"; await s.commit()
    return row


@router.post("/{image_id}/reject", response_model=ImageOut)
async def reject_image(image_id: int, s: AsyncSession = Depends(get_session),
                       _: User = Depends(require_role("reviewer"))):
    row = (await s.execute(select(ProductImage).where(ProductImage.id == image_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "图片不存在")
    row.status = "rejected"; await s.commit()
    return row

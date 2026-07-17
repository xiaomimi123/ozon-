"""评分控制 API：启动(同步/入队)/暂停/监控。"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import app.core.db as dbmod
from app.core.db import get_session
from app.api.deps import require_role
from app.models import CollectTask, User
from app.workers.scorer import run_score_core
from app.services.embedding.factory import get_embedder
from app.services.llm.factory import get_llm

router = APIRouter(prefix="/score", tags=["score"])

@router.post("/start")
async def start_score(task_id: int, sync: bool = False, s: AsyncSession = Depends(get_session), _: User = Depends(require_role("operator"))):
    t = (await s.execute(select(CollectTask).where(CollectTask.id == task_id))).scalar_one_or_none()
    if not t:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "任务不存在")
    if sync:
        await run_score_core(dbmod.async_session, task_id, embedder=get_embedder("mock"), llm=get_llm("mock"))
        return {"status": "done"}
    from arq import create_pool
    from arq.connections import RedisSettings
    from app.core.config import settings
    pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    try:
        await pool.enqueue_job("run_score", task_id)
    finally:
        await pool.aclose()
    return {"status": "queued"}

@router.post("/pause")
async def pause_score(task_id: int, s: AsyncSession = Depends(get_session), _: User = Depends(require_role("operator"))):
    t = (await s.execute(select(CollectTask).where(CollectTask.id == task_id))).scalar_one_or_none()
    if not t:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "任务不存在")
    t.score_status = "paused"; await s.commit()
    return {"ok": True}

@router.get("/monitor")
async def score_monitor(task_id: int, s: AsyncSession = Depends(get_session), _: User = Depends(require_role("operator"))):
    t = (await s.execute(select(CollectTask).where(CollectTask.id == task_id))).scalar_one_or_none()
    if not t:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "任务不存在")
    return {"score_status": t.score_status, "score_stats": t.score_stats}

"""货源匹配控制 API：启动(同步/入队)/暂停/监控。"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import app.core.db as dbmod
from app.core.db import get_session
from app.api.deps import require_role
from app.models import CollectTask, User
from app.workers.matcher import run_match_core
from app.services.embedding.factory import get_embedder
from app.services.sources.mock import MockSourceProvider

router = APIRouter(prefix="/match", tags=["match"])

@router.post("/start")
async def start_match(task_id: int, sync: bool = False, s: AsyncSession = Depends(get_session), _: User = Depends(require_role("operator"))):
    t = (await s.execute(select(CollectTask).where(CollectTask.id == task_id))).scalar_one_or_none()
    if not t:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "任务不存在")
    if sync:
        # 注意：此处通过模块属性 dbmod.async_session 在调用时读取，而非在模块顶层
        # `from app.core.db import async_session`；后者会在导入时把名字绑定为当时的
        # 对象引用，测试 conftest 对 `app.core.db.async_session` 的 monkeypatch 就不会
        # 生效，sync 分支仍会打到真实/原始 DB。写成属性访问可以让 monkeypatch 在测试库
        # 与生产库之间正确切换。
        await run_match_core(dbmod.async_session, task_id, embedder=get_embedder("mock"),
                             provider_factory=lambda p: MockSourceProvider(platform=p))
        return {"status": "done"}
    from arq import create_pool
    from arq.connections import RedisSettings
    from app.core.config import settings
    pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    try:
        await pool.enqueue_job("run_match", task_id)
    finally:
        # 用完立即关闭连接池，避免每次请求都泄漏一个 Redis 连接池
        await pool.aclose()
    return {"status": "queued"}

@router.post("/pause")
async def pause_match(task_id: int, s: AsyncSession = Depends(get_session), _: User = Depends(require_role("operator"))):
    t = (await s.execute(select(CollectTask).where(CollectTask.id == task_id))).scalar_one_or_none()
    if not t:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "任务不存在")
    t.match_status = "paused"; await s.commit()
    return {"ok": True}

@router.get("/monitor")
async def match_monitor(task_id: int, s: AsyncSession = Depends(get_session), _: User = Depends(require_role("operator"))):
    t = (await s.execute(select(CollectTask).where(CollectTask.id == task_id))).scalar_one_or_none()
    if not t:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "任务不存在")
    return {"match_status": t.match_status, "match_stats": t.match_stats}

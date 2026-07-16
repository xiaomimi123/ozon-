"""采集任务启动(同步/入队)/暂停接口。"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import app.core.db as dbmod
from app.core.db import get_session
from app.api.deps import require_role
from app.models import CollectTask, User
from app.core.progress import broadcaster
from app.workers.collector import run_collect_core

router = APIRouter(prefix="/collect", tags=["collect"])

@router.post("/start")
async def start_collect(task_id: int, sync: bool = False, s: AsyncSession = Depends(get_session), _: User = Depends(require_role("operator"))):
    t = (await s.execute(select(CollectTask).where(CollectTask.id == task_id))).scalar_one_or_none()
    if not t:
        raise HTTPException(404, "任务不存在")
    if sync:
        async def cb(msg): await broadcaster.publish(msg)
        # 注意：此处通过模块属性 dbmod.async_session 在调用时读取，而非在模块顶层
        # `from app.core.db import async_session`；后者会在导入时把名字绑定为当时的
        # 对象引用，测试 conftest 对 `app.core.db.async_session` 的 monkeypatch 就不会
        # 生效，sync 分支仍会打到真实/原始 DB。写成属性访问可以让 monkeypatch 在测试库
        # 与生产库之间正确切换。
        await run_collect_core(dbmod.async_session, task_id, progress_cb=cb)
        return {"status": "done"}
    from arq import create_pool
    from arq.connections import RedisSettings
    from app.core.config import settings
    pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    try:
        await pool.enqueue_job("run_collect", task_id)
    finally:
        # 用完立即关闭连接池，避免每次请求都泄漏一个 Redis 连接池
        # （arq 的 ArqRedis 继承自 redis.asyncio.Redis，redis-py 5.x 用 aclose()）
        await pool.aclose()
    return {"status": "queued"}

@router.post("/pause")
async def pause_collect(task_id: int, s: AsyncSession = Depends(get_session), _: User = Depends(require_role("operator"))):
    t = (await s.execute(select(CollectTask).where(CollectTask.id == task_id))).scalar_one_or_none()
    if not t:
        raise HTTPException(404, "任务不存在")
    t.status = "paused"; await s.commit()
    return {"ok": True}

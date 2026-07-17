from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.logging import setup_logging
from app.api.auth import router as auth_router
from app.api.settings import router as settings_router
from app.api.tasks import router as tasks_router
from app.api.collect import router as collect_router
from app.api.ws import router as ws_router
from app.api.products import router as products_router
from app.api.accounts import router as accounts_router
from app.api.match import router as match_router
from app.api.candidates import router as candidates_router
from app.api.score import router as score_router
from app.api.review import router as review_router
from app.api.shops import router as shops_router
from app.api.listing import router as listing_router
from app.api.pace import router as pace_router

setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    import asyncio

    from app.core.config import settings
    from app.core.db import async_session
    from app.core.progress import broadcaster
    from app.seed import ensure_admin
    await ensure_admin(async_session)
    if settings.progress_backend == "redis":
        # redis 后端才需要 API 进程订阅 Redis 频道并本地 fan-out 给 WS 连接；
        # memory 后端（默认/测试）无需订阅，行为不变。
        asyncio.create_task(broadcaster.start_redis_subscriber())
    yield


app = FastAPI(title="Ozon 跟卖/铺货自动化系统", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)
app.include_router(auth_router)
app.include_router(settings_router)
app.include_router(tasks_router)
app.include_router(collect_router)
app.include_router(ws_router)
app.include_router(products_router)
app.include_router(accounts_router)
app.include_router(match_router)
app.include_router(candidates_router)
app.include_router(score_router)
app.include_router(review_router)
app.include_router(shops_router)
app.include_router(listing_router)
app.include_router(pace_router)

@app.get("/health")
async def health():
    return {"status": "ok"}

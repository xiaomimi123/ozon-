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

setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.core.db import async_session
    from app.seed import ensure_admin
    await ensure_admin(async_session)
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

@app.get("/health")
async def health():
    return {"status": "ok"}

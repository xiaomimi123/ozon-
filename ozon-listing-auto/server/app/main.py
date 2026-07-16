from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.logging import setup_logging
from app.api.auth import router as auth_router
from app.api.settings import router as settings_router
from app.api.tasks import router as tasks_router

setup_logging()

app = FastAPI(title="Ozon 跟卖/铺货自动化系统", version="0.1.0")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)
app.include_router(auth_router)
app.include_router(settings_router)
app.include_router(tasks_router)

@app.get("/health")
async def health():
    return {"status": "ok"}

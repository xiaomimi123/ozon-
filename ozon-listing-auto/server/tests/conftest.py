"""测试基座：内存 SQLite engine/db_session 与覆盖 get_session 后的 AsyncClient 等共享 fixture。"""
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.core.db import Base, get_session
from app.main import app
from app import models  # noqa: F401  # 注册所有 ORM 模型到 Base.metadata，确保 create_all 建出真实业务表；
# 注意：不能写成 `import app.models`，那会把本模块局部名 `app` 重新绑定为顶层包，
# 覆盖掉上面 `from app.main import app` 拿到的 FastAPI 实例。

@pytest_asyncio.fixture
async def engine():
    eng = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()

@pytest_asyncio.fixture
async def db_session(engine):
    sm = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with sm() as s:
        yield s

@pytest_asyncio.fixture
async def client(engine):
    sm = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async def _override():
        async with sm() as s:
            yield s
    app.dependency_overrides[get_session] = _override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.pop(get_session, None)

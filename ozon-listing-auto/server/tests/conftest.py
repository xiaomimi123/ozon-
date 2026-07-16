"""测试基座：内存 SQLite engine/db_session 与覆盖 get_session 后的 AsyncClient 等共享 fixture。"""
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.core.db import Base, get_session
from app.main import app

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
    app.dependency_overrides.clear()

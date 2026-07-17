"""ORM 模型测试：在内存 SQLite 上建表并验证 CollectTask/OzonProduct 的映射与默认值。"""
import pytest
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.core.db import Base
from app.models import User, CollectTask, OzonProduct

@pytest.mark.asyncio
async def test_create_task_and_product():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with sm() as s:
        t = CollectTask(name="t1", entry_type="keyword", entry_value="phone", provider="mock", source_platforms=[])
        s.add(t); await s.flush()
        p = OzonProduct(task_id=t.id, sku="SKU1", title="Phone", price=99.0)
        s.add(p); await s.commit()
        assert t.id is not None and t.status == "pending" and t.listing_mode == "follow"
        assert p.sku == "SKU1"

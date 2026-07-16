"""验证测试基座 fixture 产出的内存库确实建好了真实业务表。"""
import pytest
from sqlalchemy import select
from app.models import User


@pytest.mark.asyncio
async def test_db_session_has_real_tables(db_session):
    db_session.add(User(username="fx", password_hash="x", role="operator"))
    await db_session.commit()
    got = (await db_session.execute(select(User).where(User.username == "fx"))).scalar_one()
    assert got.id is not None and got.role == "operator"

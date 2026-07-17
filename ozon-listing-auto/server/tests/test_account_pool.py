"""账号池服务测试：限速间隔、日限+跨日重置、风控冷却+自动恢复、cookie 解密。"""
import json
import pytest
from datetime import datetime, timezone, timedelta
from app.services.account_pool import acquire, report_risk, get_session_credentials
from app.core.crypto import encrypt
from app.models import SourceAccount

def _acc(**kw):
    base = dict(platform="ali1688", credentials_encrypted=encrypt(json.dumps({"cookie": "c"})),
                status="active", daily_limit=5, min_interval_sec=6, daily_used_count=0)
    base.update(kw)
    return SourceAccount(**base)

@pytest.mark.asyncio
async def test_acquire_respects_interval(engine):
    from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
    sm = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    now = datetime(2026, 7, 17, 12, 0, 0, tzinfo=timezone.utc)
    async with sm() as s:
        s.add(_acc(last_used_at=now - timedelta(seconds=3)))   # 3s前用过, <6s 不可用
        await s.commit()
    got = await acquire(sm, "ali1688", now=now)
    assert got is None
    # 7s 后可用
    got2 = await acquire(sm, "ali1688", now=now + timedelta(seconds=7))
    assert got2 is not None and got2.platform == "ali1688"

@pytest.mark.asyncio
async def test_acquire_daily_limit_and_reset(engine):
    from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
    sm = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    now = datetime(2026, 7, 17, 12, 0, 0, tzinfo=timezone.utc)
    async with sm() as s:
        s.add(_acc(daily_used_count=5, daily_used_date=now.date(), last_used_at=None))  # 已达上限
        await s.commit()
    assert await acquire(sm, "ali1688", now=now) is None
    # 次日重置
    assert await acquire(sm, "ali1688", now=now + timedelta(days=1)) is not None

@pytest.mark.asyncio
async def test_report_risk_sets_cooldown(engine):
    from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
    from sqlalchemy import select
    sm = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    now = datetime(2026, 7, 17, 12, 0, 0, tzinfo=timezone.utc)
    async with sm() as s:
        s.add(_acc(last_used_at=None)); await s.commit()
        aid = (await s.execute(select(SourceAccount.id))).scalar_one()
    await report_risk(sm, aid, now=now, cooldown_sec=1800)
    async with sm() as s:
        acc = (await s.execute(select(SourceAccount).where(SourceAccount.id == aid))).scalar_one()
        assert acc.status == "cooldown" and acc.risk_hits == 1
    assert await acquire(sm, "ali1688", now=now) is None                    # 冷却中不可用
    assert await acquire(sm, "ali1688", now=now + timedelta(seconds=1801)) is not None  # 冷却结束

def test_get_credentials_decrypts():
    acc = _acc()
    assert get_session_credentials(acc)["cookie"] == "c"

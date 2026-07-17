"""货源账号池：按平台取可用账号(限速/日限/冷却), 风控置冷却换号; cookie Fernet 解密。"""
import json
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker
from app.core.crypto import decrypt
from app.models import SourceAccount


@asynccontextmanager
async def _noop_lock():
    yield


def _as_aware(dt: datetime | None) -> datetime | None:
    """SQLite 不保留 DateTime 列的 tzinfo，读出后为 naive；按 UTC 补齐时区以便与调用方传入的
    aware `now` 比较，避免 `can't compare offset-naive and offset-aware datetimes`。"""
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def get_session_credentials(account: SourceAccount) -> dict:
    """Fernet 解密账号的 credentials_encrypted，返回明文凭证字典。"""
    return json.loads(decrypt(account.credentials_encrypted))


async def acquire(session_factory: async_sessionmaker, platform: str, *, now: datetime, lock=None):
    """选取一个可用账号：非 disabled、不在冷却中、满足最小调用间隔、当日用量未超限。

    冷却到期自动恢复：status=="cooldown" 但 cooldown_until<=now 时，复位为 active 后继续判断。
    命中后更新 last_used_at/当日计数(跨天按 now.date() 重置)并提交；无可用账号返回 None。
    """
    lock = lock or _noop_lock()
    async with lock:
        async with session_factory() as s:
            rows = (await s.execute(select(SourceAccount).where(
                SourceAccount.platform == platform, SourceAccount.status != "disabled"
            ).order_by(SourceAccount.last_used_at.asc().nulls_first()))).scalars().all()
            for acc in rows:
                cooldown_until = _as_aware(acc.cooldown_until)
                last_used_at = _as_aware(acc.last_used_at)
                if cooldown_until and cooldown_until > now:
                    continue  # 冷却中
                if acc.status == "cooldown":
                    acc.status = "active"  # 冷却到期, 复位
                if last_used_at and (now - last_used_at).total_seconds() < acc.min_interval_sec:
                    continue
                today = now.date()
                used = acc.daily_used_count if acc.daily_used_date == today else 0
                if used >= acc.daily_limit:
                    continue
                # 命中：更新用量
                acc.last_used_at = now
                acc.daily_used_date = today
                acc.daily_used_count = used + 1
                await s.commit()
                await s.refresh(acc)
                return acc
            return None


async def report_risk(session_factory: async_sessionmaker, account_id: int, *, now: datetime, cooldown_sec: int = 1800):
    """风控命中：风险计数+1，置入冷却状态，cooldown_until=now+cooldown_sec。"""
    async with session_factory() as s:
        acc = (await s.execute(select(SourceAccount).where(SourceAccount.id == account_id))).scalar_one()
        acc.risk_hits += 1
        acc.status = "cooldown"
        acc.cooldown_until = now + timedelta(seconds=cooldown_sec)
        await s.commit()

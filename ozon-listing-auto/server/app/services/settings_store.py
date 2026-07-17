"""加密配置存取服务：按 category/key 读写 AppSetting，值以 Fernet 加密存储。"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.crypto import encrypt, decrypt
from app.models import AppSetting

async def set_value(s: AsyncSession, category: str, key: str, value: str, is_secret: bool = True, updated_by: int | None = None):
    row = (await s.execute(select(AppSetting).where(AppSetting.category == category, AppSetting.key == key))).scalar_one_or_none()
    enc = encrypt(value)
    if row:
        row.value_encrypted = enc; row.is_secret = is_secret; row.updated_by = updated_by
    else:
        s.add(AppSetting(category=category, key=key, value_encrypted=enc, is_secret=is_secret, updated_by=updated_by))

async def get_value(s: AsyncSession, category: str, key: str) -> str | None:
    row = (await s.execute(select(AppSetting).where(AppSetting.category == category, AppSetting.key == key))).scalar_one_or_none()
    return decrypt(row.value_encrypted) if row else None

async def get_category(s: AsyncSession, category: str) -> dict[str, str]:
    rows = (await s.execute(select(AppSetting).where(AppSetting.category == category))).scalars().all()
    return {r.key: decrypt(r.value_encrypted) for r in rows}

async def get_category_masked(s: AsyncSession, category: str) -> dict[str, str]:
    rows = (await s.execute(select(AppSetting).where(AppSetting.category == category))).scalars().all()
    return {r.key: ("***" if r.is_secret else decrypt(r.value_encrypted)) for r in rows}

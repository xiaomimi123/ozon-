"""配置中心接口：管理员按 category 读取（脱敏）与写入加密配置。"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.db import get_session
from app.api.deps import require_role
from app.models import User
from app.services.settings_store import set_value, get_category_masked

router = APIRouter(prefix="/settings", tags=["settings"])

@router.get("/{category}")
async def read_settings(category: str, s: AsyncSession = Depends(get_session), _: User = Depends(require_role("admin"))):
    return await get_category_masked(s, category)

@router.put("/{category}")
async def write_settings(category: str, body: dict, s: AsyncSession = Depends(get_session), user: User = Depends(require_role("admin"))):
    for k, v in body.items():
        await set_value(s, category, k, str(v), is_secret=True, updated_by=user.id)
    await s.commit()
    return {"ok": True}

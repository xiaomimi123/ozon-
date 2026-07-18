"""系统配置 API(admin)：全局 Ozon Seller provider(mock|real)切换。"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.db import get_session
from app.api.deps import require_role
from app.models import User
from app.schemas.system import SystemIn, SystemOut
from app.services import settings_store as store

router = APIRouter(prefix="/settings/system", tags=["settings"])
_CAT = "system"


@router.get("", response_model=SystemOut)
async def read(s: AsyncSession = Depends(get_session), _: User = Depends(require_role("admin"))):
    m = await store.get_category(s, _CAT)
    return SystemOut(ozon_seller_provider=m.get("ozon_seller_provider", "mock"))


@router.put("", response_model=SystemOut)
async def write(body: SystemIn, s: AsyncSession = Depends(get_session), u: User = Depends(require_role("admin"))):
    await store.set_value(s, _CAT, "ozon_seller_provider", body.ozon_seller_provider, is_secret=False, updated_by=u.id)
    await s.commit()
    return SystemOut(ozon_seller_provider=body.ozon_seller_provider)

"""货源配置 API(admin)：1688 图搜端点/方法/额外参数·头/响应路径(均非 secret; cookie 在账号池)。"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.db import get_session
from app.api.deps import require_role
from app.models import User
from app.schemas.sources import SourcesIn, SourcesOut
from app.services import settings_store as store

router = APIRouter(prefix="/settings/sources", tags=["settings"])
_CAT = "sources"
_KEYS = ("ali1688_image_search_url", "ali1688_keyword_search_url", "ali1688_method",
         "ali1688_extra_params", "ali1688_extra_headers", "ali1688_offer_list_path")


@router.get("", response_model=SourcesOut)
async def read(s: AsyncSession = Depends(get_session), _: User = Depends(require_role("admin"))):
    m = await store.get_category(s, _CAT)
    return SourcesOut(**{k: m.get(k, getattr(SourcesIn(), k)) for k in _KEYS})


@router.put("", response_model=SourcesOut)
async def write(body: SourcesIn, s: AsyncSession = Depends(get_session), u: User = Depends(require_role("admin"))):
    for k in _KEYS:
        await store.set_value(s, _CAT, k, getattr(body, k), is_secret=False, updated_by=u.id)
    await s.commit()
    return SourcesOut(**{k: getattr(body, k) for k in _KEYS})

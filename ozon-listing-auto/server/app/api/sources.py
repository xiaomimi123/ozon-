"""货源配置 API(admin)：1688 图搜端点/方法/额外参数·头/响应路径 + 采集解析路径 override(均非 secret;
cookie 在账号池)；import_token 为 secret，GET 脱敏("***")、PUT 留空不覆盖。"""
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
_PATH_KEYS = ("import_1688_list_path", "import_1688_offer_id_path", "import_1688_title_path",
              "import_1688_price_path", "import_1688_image_path", "import_1688_shop_path",
              "import_1688_detail_url_path", "import_1688_sales_path")


@router.get("", response_model=SourcesOut)
async def read(s: AsyncSession = Depends(get_session), _: User = Depends(require_role("admin"))):
    m = await store.get_category_masked(s, _CAT)
    data = {k: m.get(k, getattr(SourcesIn(), k)) for k in _KEYS + _PATH_KEYS}
    data["import_token"] = m.get("import_token", "")
    return SourcesOut(**data)


@router.put("", response_model=SourcesOut)
async def write(body: SourcesIn, s: AsyncSession = Depends(get_session), u: User = Depends(require_role("admin"))):
    for k in _KEYS + _PATH_KEYS:
        await store.set_value(s, _CAT, k, getattr(body, k), is_secret=False, updated_by=u.id)
    if body.import_token:
        await store.set_value(s, _CAT, "import_token", body.import_token, is_secret=True, updated_by=u.id)
    await s.commit()
    token_set = bool(body.import_token) or bool(await store.get_value(s, _CAT, "import_token"))
    data = {k: getattr(body, k) for k in _KEYS + _PATH_KEYS}
    data["import_token"] = "***" if token_set else ""
    return SourcesOut(**data)

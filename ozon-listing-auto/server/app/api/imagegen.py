"""AI 生图 provider 配置 API(§5.5.5, admin)：base_url/api_key/model/provider/降级顺序，Fernet 加密脱敏。"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.db import get_session
from app.api.deps import require_role
from app.models import User
from app.schemas.imagegen import ImagegenIn, ImagegenOut
from app.services import settings_store as store

router = APIRouter(prefix="/settings/imagegen", tags=["settings"])
_CAT = "imagegen"


@router.get("", response_model=ImagegenOut)
async def read(s: AsyncSession = Depends(get_session), _: User = Depends(require_role("admin"))):
    masked = await store.get_category_masked(s, _CAT)
    return ImagegenOut(provider=masked.get("provider", "mock"), img_base_url=masked.get("img_base_url", ""),
                       img_api_key=masked.get("img_api_key"), img_model=masked.get("img_model", ""),
                       fallback=masked.get("fallback", ""),
                       img_request_template=masked.get("img_request_template", ""),
                       img_response_path=masked.get("img_response_path", ""))


@router.put("", response_model=ImagegenOut)
async def write(body: ImagegenIn, s: AsyncSession = Depends(get_session),
                u: User = Depends(require_role("admin"))):
    await store.set_value(s, _CAT, "provider", body.provider, is_secret=False, updated_by=u.id)
    await store.set_value(s, _CAT, "img_base_url", body.img_base_url, is_secret=False, updated_by=u.id)
    if body.img_api_key:
        # 留空则不更改：前端 GET 脱敏为 "***" 且加载时强制清空该字段，
        # 若无条件覆盖会在管理员只改其他字段时静默清空已存密钥。
        await store.set_value(s, _CAT, "img_api_key", body.img_api_key, is_secret=True, updated_by=u.id)
    await store.set_value(s, _CAT, "img_model", body.img_model, is_secret=False, updated_by=u.id)
    await store.set_value(s, _CAT, "fallback", body.fallback, is_secret=False, updated_by=u.id)
    await store.set_value(s, _CAT, "img_request_template", body.img_request_template, is_secret=False, updated_by=u.id)
    await store.set_value(s, _CAT, "img_response_path", body.img_response_path, is_secret=False, updated_by=u.id)
    await s.commit()
    return ImagegenOut(provider=body.provider, img_base_url=body.img_base_url, img_api_key="***",
                       img_model=body.img_model, fallback=body.fallback,
                       img_request_template=body.img_request_template,
                       img_response_path=body.img_response_path)

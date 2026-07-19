"""Ozon 卖家端类目/类型/属性查询(admin/operator)：供上架审核自建补充表单用。
有真实 ozon 店铺+provider=real 时走真实 API, 否则样例模式。"""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.db import get_session
from app.core.crypto import decrypt
from app.api.deps import require_role
from app.models import Shop, User
from app.services.settings_store import get_category
from app.services.ozon_seller.catalog import OzonCatalog

router = APIRouter(prefix="/ozon-catalog", tags=["ozon-catalog"])

async def _catalog_and_creds(s: AsyncSession):
    conf = await get_category(s, "system")
    real = (conf.get("ozon_seller_provider") or "mock") == "real"
    shop = (await s.execute(select(Shop).where(Shop.platform == "ozon", Shop.is_active == True))).scalars().first()
    if real and shop:
        return OzonCatalog(), shop.client_id, decrypt(shop.api_key_encrypted)
    return OzonCatalog(sample=True), "", ""

@router.get("/types")
async def types(s: AsyncSession = Depends(get_session), _: User = Depends(require_role("operator"))):
    cat, cid, key = await _catalog_and_creds(s)
    return await cat.get_types(cid, key)

@router.get("/attributes")
async def attributes(category_id: int, type_id: int, s: AsyncSession = Depends(get_session), _: User = Depends(require_role("operator"))):
    cat, cid, key = await _catalog_and_creds(s)
    return await cat.get_attributes(cid, key, category_id=category_id, type_id=type_id)

@router.get("/attribute-values")
async def attribute_values(category_id: int, type_id: int, attribute_id: int, s: AsyncSession = Depends(get_session), _: User = Depends(require_role("operator"))):
    cat, cid, key = await _catalog_and_creds(s)
    return await cat.get_attribute_values(cid, key, category_id=category_id, type_id=type_id, attribute_id=attribute_id)

"""店铺凭据 CRUD(admin)：api_key Fernet 加密, 响应脱敏。"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.db import get_session
from app.core.crypto import encrypt
from app.api.deps import require_role
from app.models import Shop, User
from app.schemas.shop import ShopCreate, ShopUpdate, ShopOut

router = APIRouter(prefix="/shops", tags=["shops"])

@router.post("", response_model=ShopOut, status_code=201)
async def create_shop(body: ShopCreate, s: AsyncSession = Depends(get_session), _: User = Depends(require_role("admin"))):
    shop = Shop(name=body.name, client_id=body.client_id, api_key_encrypted=encrypt(body.api_key), is_sandbox=body.is_sandbox)
    s.add(shop); await s.commit(); await s.refresh(shop)
    return shop

@router.get("", response_model=list[ShopOut])
async def list_shops(s: AsyncSession = Depends(get_session), _: User = Depends(require_role("admin"))):
    return list((await s.execute(select(Shop).order_by(Shop.id.desc()))).scalars().all())

@router.put("/{shop_id}", response_model=ShopOut)
async def update_shop(shop_id: int, body: ShopUpdate, s: AsyncSession = Depends(get_session), _: User = Depends(require_role("admin"))):
    shop = (await s.execute(select(Shop).where(Shop.id == shop_id))).scalar_one_or_none()
    if not shop:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "店铺不存在")
    for f in ("name", "client_id", "is_active", "is_sandbox"):
        v = getattr(body, f)
        if v is not None:
            setattr(shop, f, v)
    if body.api_key is not None:
        shop.api_key_encrypted = encrypt(body.api_key)
    await s.commit(); await s.refresh(shop)
    return shop

@router.delete("/{shop_id}", status_code=204)
async def delete_shop(shop_id: int, s: AsyncSession = Depends(get_session), _: User = Depends(require_role("admin"))):
    shop = (await s.execute(select(Shop).where(Shop.id == shop_id))).scalar_one_or_none()
    if shop:
        await s.delete(shop); await s.commit()

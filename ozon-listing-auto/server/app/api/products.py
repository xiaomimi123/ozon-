"""商品列表接口：按任务 + 六维筛选条件分页查询。"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.db import get_session
from app.api.deps import get_current_user
from app.models import OzonProduct, User
from app.schemas.product import ProductOut
from app.services.filtering import ProductFilter, build_conditions

router = APIRouter(prefix="/products", tags=["products"])

@router.get("")
async def list_products(task_id: int, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=200),
                        f: ProductFilter = Depends(),
                        s: AsyncSession = Depends(get_session), _: User = Depends(get_current_user)):
    conds = build_conditions(f)
    base = select(OzonProduct).where(OzonProduct.task_id == task_id, *conds)
    total = (await s.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    rows = (await s.execute(base.order_by(OzonProduct.id.desc()).offset((page-1)*page_size).limit(page_size))).scalars().all()
    return {"items": [ProductOut.model_validate(r) for r in rows], "total": total}

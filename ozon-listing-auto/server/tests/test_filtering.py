"""筛选引擎单元测试：多维条件组合与空筛选放行。"""
import pytest
from sqlalchemy import select, func
from app.services.filtering import build_conditions, ProductFilter
from app.models import OzonProduct

@pytest.mark.asyncio
async def test_filter_by_sales_and_rating(db_session):
    db_session.add_all([
        OzonProduct(task_id=1, sku="A", sales_monthly=100, rating=4.8, return_rate=0.03),
        OzonProduct(task_id=1, sku="B", sales_monthly=10,  rating=4.0, return_rate=0.20),
        OzonProduct(task_id=1, sku="C", sales_monthly=500, rating=4.9, return_rate=0.02),
    ])
    await db_session.commit()
    f = ProductFilter(sales_min=50, rating_min=4.5, return_rate_max=0.10)
    conds = build_conditions(f)
    q = select(func.count()).select_from(OzonProduct).where(OzonProduct.task_id == 1, *conds)
    assert (await db_session.execute(q)).scalar_one() == 2   # A, C

@pytest.mark.asyncio
async def test_empty_filter_matches_all(db_session):
    db_session.add_all([OzonProduct(task_id=2, sku="A"), OzonProduct(task_id=2, sku="B")])
    await db_session.commit()
    conds = build_conditions(ProductFilter())
    q = select(func.count()).select_from(OzonProduct).where(OzonProduct.task_id == 2, *conds)
    assert (await db_session.execute(q)).scalar_one() == 2

"""商品筛选引擎：六维（销量/评分/退货率/重量/上架时间/关注数）+ 关键词的可空条件构造。"""
from datetime import datetime
from pydantic import BaseModel
from app.models import OzonProduct

class ProductFilter(BaseModel):
    sales_min: int | None = None
    sales_max: int | None = None
    return_rate_max: float | None = None
    rating_min: float | None = None
    weight_min: float | None = None
    weight_max: float | None = None
    listed_after: datetime | None = None
    follow_min: int | None = None
    follow_max: int | None = None
    keyword: str | None = None

def build_conditions(f: ProductFilter) -> list:
    c = []
    if f.sales_min is not None: c.append(OzonProduct.sales_monthly >= f.sales_min)
    if f.sales_max is not None: c.append(OzonProduct.sales_monthly <= f.sales_max)
    if f.return_rate_max is not None: c.append(OzonProduct.return_rate <= f.return_rate_max)
    if f.rating_min is not None: c.append(OzonProduct.rating >= f.rating_min)
    if f.weight_min is not None: c.append(OzonProduct.weight >= f.weight_min)
    if f.weight_max is not None: c.append(OzonProduct.weight <= f.weight_max)
    if f.listed_after is not None: c.append(OzonProduct.listed_at >= f.listed_after)
    if f.follow_min is not None: c.append(OzonProduct.follow_count >= f.follow_min)
    if f.follow_max is not None: c.append(OzonProduct.follow_count <= f.follow_max)
    if f.keyword: c.append(OzonProduct.title.ilike(f"%{f.keyword}%"))
    return c

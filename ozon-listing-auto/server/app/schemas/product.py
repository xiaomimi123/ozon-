"""商品列表接口的响应 Pydantic 模型。"""
from pydantic import BaseModel, ConfigDict

class ProductOut(BaseModel):
    id: int
    sku: str
    title: str | None
    price: float | None
    currency: str | None
    sales_monthly: int | None
    rating: float | None
    reviews_count: int | None
    weight: float | None
    follow_count: int | None
    return_rate: float | None
    main_image_url: str | None
    parent_sku: str | None
    model_config = ConfigDict(from_attributes=True)

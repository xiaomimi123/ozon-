"""货源候选 API 响应 schema。"""
from datetime import datetime
from pydantic import BaseModel, ConfigDict

class CandidateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    ozon_product_id: int
    platform: str
    offer_id: str
    title: str | None
    price: float | None
    currency: str | None
    quantity_begin: int | None
    image_url: str | None
    detail_url: str | None
    supplier_name: str | None
    supplier_info: dict | None
    dedup_group: int | None
    is_representative: bool
    status: str

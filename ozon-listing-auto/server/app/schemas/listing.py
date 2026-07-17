"""上架草稿 API schema。"""
from pydantic import BaseModel, ConfigDict

class DraftOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    task_id: int
    ozon_product_id: int | None
    candidate_id: int
    mode: str
    target_ozon_sku: str | None
    barcode: str | None
    title: str | None = None
    description: str | None = None
    category_id: int | None = None
    attributes: dict | None = None
    images: list | None = None
    price: float | None
    cost: float | None
    margin: float | None
    currency: str
    stock_qty: int
    status: str
    ozon_result: dict | None

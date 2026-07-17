"""上架草稿 API schema。"""
from pydantic import BaseModel, ConfigDict

class DraftOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    task_id: int
    ozon_product_id: int
    candidate_id: int
    target_ozon_sku: str | None
    barcode: str | None
    price: float | None
    cost: float | None
    margin: float | None
    currency: str
    stock_qty: int
    status: str
    ozon_result: dict | None

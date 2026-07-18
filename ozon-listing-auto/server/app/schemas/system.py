"""系统配置 API schema：全局 Ozon Seller provider(mock|real)切换。"""
from pydantic import BaseModel

class SystemIn(BaseModel):
    ozon_seller_provider: str = "mock"   # mock | real

class SystemOut(BaseModel):
    ozon_seller_provider: str = "mock"

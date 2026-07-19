"""系统配置 API schema：全局 Ozon Seller provider(mock|real) + 类目树 provider(mock|real) 切换。"""
from pydantic import BaseModel

class SystemIn(BaseModel):
    ozon_seller_provider: str = "mock"   # mock | real
    category_tree_provider: str = "mock"   # mock | real
    ozon_publish_dry_run: str = "true"   # real 模式下是否 dry-run("true"|"false")

class SystemOut(BaseModel):
    ozon_seller_provider: str = "mock"
    category_tree_provider: str = "mock"
    ozon_publish_dry_run: str = "true"

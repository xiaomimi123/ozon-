"""按名返回 OzonSellerProvider；默认 mock，real 惰性 import。"""
from app.services.ozon_seller.base import OzonSellerProvider
from app.services.ozon_seller.mock import MockOzonSeller

def get_ozon_seller(name: str = "mock") -> OzonSellerProvider:
    if name == "mock":
        return MockOzonSeller()
    if name == "real":
        from app.services.ozon_seller.real import RealOzonSeller
        return RealOzonSeller()
    raise ValueError(f"未知 ozon_seller: {name}")

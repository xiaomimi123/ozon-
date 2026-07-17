"""Ozon Seller 写入抽象：跟卖 offer 创建(§5.9 follow 分支)。"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Protocol

@dataclass
class PublishResult:
    ok: bool
    ozon_product_id: str | None
    status: str            # published | pending_review | failed
    raw: dict = field(default_factory=dict)
    error: str | None = None

class OzonSellerProvider(Protocol):
    name: str
    async def create_follow_offer(self, *, client_id: str, api_key: str, target_sku: str,
                                  barcode: str | None, price: float, stock: int, offer_id: str) -> PublishResult: ...

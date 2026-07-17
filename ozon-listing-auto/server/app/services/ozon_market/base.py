"""采集数据传输对象 OzonProductDTO 与 Provider 协议定义。"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

@dataclass
class OzonProductDTO:
    sku: str
    title: str | None = None
    price: float | None = None
    currency: str | None = None
    sales_monthly: int | None = None
    rating: float | None = None
    reviews_count: int | None = None
    weight: float | None = None
    listed_at: datetime | None = None
    follow_count: int | None = None
    return_rate: float | None = None
    main_image_url: str | None = None
    images: list[str] = field(default_factory=list)
    attributes: dict = field(default_factory=dict)
    parent_sku: str | None = None
    product_url: str | None = None
    phash: str | None = None
    raw: dict = field(default_factory=dict)

class OzonMarketProvider(Protocol):
    name: str
    async def search_by_keyword(self, kw: str, page: int) -> list[OzonProductDTO]: ...
    async def list_by_category(self, category_url: str, page: int) -> list[OzonProductDTO]: ...
    async def list_by_seller(self, seller_id: str, page: int) -> list[OzonProductDTO]: ...

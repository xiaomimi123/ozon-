"""货源 SourceProvider 抽象接口与候选 DTO（对齐开发文档 §5.3）。"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Protocol

@dataclass
class SupplyCandidateDTO:
    platform: str
    offer_id: str
    title: str | None = None
    price: float | None = None
    currency: str | None = None
    quantity_begin: int | None = None
    quantity_prices: list | None = None
    image_url: str | None = None
    images: list[str] = field(default_factory=list)
    detail_url: str | None = None
    supplier_name: str | None = None
    supplier_info: dict = field(default_factory=dict)
    phash: str | None = None
    raw: dict = field(default_factory=dict)

class SourceProvider(Protocol):
    platform: str
    async def image_search(self, image_url: str, *, session) -> list[SupplyCandidateDTO]: ...
    async def keyword_search(self, kw: str, *, session) -> list[SupplyCandidateDTO]: ...
    async def fetch_detail(self, offer_id: str, *, session) -> SupplyCandidateDTO: ...

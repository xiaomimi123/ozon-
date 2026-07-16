"""Apify 采集 Provider 占位实现，后续里程碑接入付费采集 API。"""
from app.services.ozon_market.base import OzonProductDTO

class OzonApifyProvider:
    name = "apify"
    async def search_by_keyword(self, kw: str, page: int) -> list[OzonProductDTO]:
        raise NotImplementedError("Apify provider 占位，后续里程碑接入付费采集 API")
    async def list_by_category(self, category_url: str, page: int) -> list[OzonProductDTO]:
        raise NotImplementedError("Apify provider 占位")
    async def list_by_seller(self, seller_id: str, page: int) -> list[OzonProductDTO]:
        raise NotImplementedError("Apify provider 占位")

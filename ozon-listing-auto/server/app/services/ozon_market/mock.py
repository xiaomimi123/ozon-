"""Mock 采集 Provider 最小实现，Task 8 补充 fixtures 与变体样本。"""
from app.services.ozon_market.base import OzonProductDTO

class OzonMockProvider:
    name = "mock"
    async def search_by_keyword(self, kw: str, page: int) -> list[OzonProductDTO]:
        return [OzonProductDTO(sku="MOCK-1", title=f"{kw} 示例", price=99.0)] if page == 1 else []
    async def list_by_category(self, category_url: str, page: int) -> list[OzonProductDTO]:
        return await self.search_by_keyword("category", page)
    async def list_by_seller(self, seller_id: str, page: int) -> list[OzonProductDTO]:
        return await self.search_by_keyword("seller", page)

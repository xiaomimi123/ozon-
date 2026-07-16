"""Composer-api 采集 Provider 占位实现，真实请求逻辑由 Task 15 补充。"""
from app.services.ozon_market.base import OzonProductDTO


class OzonComposerProvider:
    name = "composer"

    async def search_by_keyword(self, kw: str, page: int) -> list[OzonProductDTO]:
        raise NotImplementedError("composer provider 将在 Task 15 实现真实 composer-api")

    async def list_by_category(self, category_url: str, page: int) -> list[OzonProductDTO]:
        raise NotImplementedError

    async def list_by_seller(self, seller_id: str, page: int) -> list[OzonProductDTO]:
        raise NotImplementedError

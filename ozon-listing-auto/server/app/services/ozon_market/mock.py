"""Mock 采集 Provider 完整实现：从 fixtures/ozon_mock.json 加载样本并分页返回。

样本中含变体（相同 parent_sku）与重复（相同 sku 或相同 phash）数据，
用于驱动后续归集（variant grouping）与去重（dedup）逻辑的测试。
"""
import json
from pathlib import Path
from app.services.ozon_market.base import OzonProductDTO

_DATA_PATH = Path(__file__).resolve().parents[2] / "fixtures" / "ozon_mock.json"

def _load() -> list[dict]:
    """读取 fixtures JSON 文件为原始字典列表。"""
    return json.loads(_DATA_PATH.read_text(encoding="utf-8"))

def _to_dto(d: dict) -> OzonProductDTO:
    """把 fixtures 中的单条原始字典转换为 OzonProductDTO。"""
    return OzonProductDTO(
        sku=d["sku"], title=d.get("title"), price=d.get("price"), currency=d.get("currency"),
        sales_monthly=d.get("sales_monthly"), rating=d.get("rating"), reviews_count=d.get("reviews_count"),
        weight=d.get("weight"), follow_count=d.get("follow_count"), return_rate=d.get("return_rate"),
        main_image_url=d.get("main_image_url"), images=d.get("images", []), attributes=d.get("attributes", {}),
        parent_sku=d.get("parent_sku"), product_url=d.get("product_url"), phash=d.get("phash"), raw=d,
    )

class OzonMockProvider:
    """本地 mock Provider：不发起真实网络请求，从固定 fixtures 分页返回样本数据。"""

    name = "mock"

    def __init__(self, page_size: int = 10):
        self.page_size = page_size
        self._all = [_to_dto(d) for d in _load()]

    async def _page(self, page: int) -> list[OzonProductDTO]:
        start = (page - 1) * self.page_size
        return self._all[start:start + self.page_size]

    async def search_by_keyword(self, kw: str, page: int) -> list[OzonProductDTO]:
        return await self._page(page)

    async def list_by_category(self, category_url: str, page: int) -> list[OzonProductDTO]:
        return await self._page(page)

    async def list_by_seller(self, seller_id: str, page: int) -> list[OzonProductDTO]:
        return await self._page(page)

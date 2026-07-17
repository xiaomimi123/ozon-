"""MockSourceProvider：按平台从 fixtures 返回货源候选（含跨平台近似重复样本）。"""
import json
from pathlib import Path
from app.services.sources.base import SupplyCandidateDTO

_DATA = Path(__file__).resolve().parents[2] / "fixtures" / "source_mock.json"

def _load() -> dict:
    return json.loads(_DATA.read_text(encoding="utf-8"))

def _to_dto(platform: str, d: dict) -> SupplyCandidateDTO:
    return SupplyCandidateDTO(
        platform=platform, offer_id=d["offer_id"], title=d.get("title"), price=d.get("price"),
        currency=d.get("currency"), quantity_begin=d.get("quantity_begin"), quantity_prices=d.get("quantity_prices"),
        image_url=d.get("image_url"), images=d.get("images", []), detail_url=d.get("detail_url"),
        supplier_name=d.get("supplier_name"), supplier_info=d.get("supplier_info", {}), raw=d,
    )

class MockSourceProvider:
    def __init__(self, platform: str = "mock"):
        self.platform = platform
        self._all = _load()

    def _candidates(self) -> list[SupplyCandidateDTO]:
        rows = self._all.get(self.platform, [])
        return [_to_dto(self.platform, d) for d in rows]

    async def image_search(self, image_url: str, *, session) -> list[SupplyCandidateDTO]:
        return self._candidates()
    async def keyword_search(self, kw: str, *, session) -> list[SupplyCandidateDTO]:
        return self._candidates()
    async def fetch_detail(self, offer_id: str, *, session) -> SupplyCandidateDTO:
        for c in self._candidates():
            if c.offer_id == offer_id:
                return c
        return SupplyCandidateDTO(platform=self.platform, offer_id=offer_id)

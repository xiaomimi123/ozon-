"""MockSourceProvider：从 fixtures 返回货源候选，供 mock-first 跑通链路。"""
from app.services.sources.base import SupplyCandidateDTO

class MockSourceProvider:
    platform = "mock"
    async def image_search(self, image_url: str, *, session) -> list[SupplyCandidateDTO]:
        return [SupplyCandidateDTO(platform="mock", offer_id="M1", title="示例", price=9.9)]
    async def keyword_search(self, kw: str, *, session) -> list[SupplyCandidateDTO]:
        return await self.image_search("", session=session)
    async def fetch_detail(self, offer_id: str, *, session) -> SupplyCandidateDTO:
        return SupplyCandidateDTO(platform="mock", offer_id=offer_id)

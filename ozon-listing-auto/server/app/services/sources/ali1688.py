"""Ali1688Provider：httpx + cookie 拍立淘图搜为主 + 关键词；请求层与解析层分离。"""
import httpx
from app.services.sources.base import SupplyCandidateDTO
from app.services.sources.parser_ali import parse_image_search

_IMAGE_SEARCH_URL = "https://s.1688.com/youyuan/index.htm"   # 占位, 联调以实际图搜端点为准


class Ali1688Provider:
    """1688 货源 Provider：httpx + cookie 会话，图搜为主、关键词为辅。"""

    platform = "ali1688"

    def __init__(self, timeout: float = 20.0):
        self._timeout = timeout

    def _client(self, session) -> httpx.AsyncClient:
        """按传入 session（含登录态 cookie）构造带 cookie 的 httpx 客户端。"""
        cookies = (session or {}).get("cookie") if isinstance(session, dict) else None
        headers = {"User-Agent": "Mozilla/5.0"}
        return httpx.AsyncClient(timeout=self._timeout, headers=headers,
                                  cookies={"cookie2": cookies} if cookies else None)

    async def image_search(self, image_url: str, *, session) -> list[SupplyCandidateDTO]:
        """拍立淘图搜：以图搜图，返回相似货源候选。"""
        async with self._client(session) as c:
            r = await c.get(_IMAGE_SEARCH_URL, params={"imageAddress": image_url})
            r.raise_for_status()
            return parse_image_search(r.json())

    async def keyword_search(self, kw: str, *, session) -> list[SupplyCandidateDTO]:
        """关键词搜索：图搜结果不足时的补充手段。"""
        async with self._client(session) as c:
            r = await c.get("https://s.1688.com/selloffer/offer_search.htm", params={"keywords": kw})
            r.raise_for_status()
            return parse_image_search(r.json())

    async def fetch_detail(self, offer_id: str, *, session) -> SupplyCandidateDTO:
        """按 offer_id 拉取商品详情（占位，联调时补齐真实端点解析）。"""
        return SupplyCandidateDTO(platform="ali1688", offer_id=offer_id)

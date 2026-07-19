"""Ali1688Provider：配置驱动(端点/方法/额外参数·头/响应路径可配) + cookie 账号池会话。
拍立淘签名由用户抓包填 /settings/sources(本轮不复现)。请求层与解析层分离。"""
import httpx
from app.services.sources.base import SupplyCandidateDTO
from app.services.sources.parser_ali import parse_offers


class Ali1688Provider:
    """1688 货源 Provider：配置驱动，端点/方法/额外参数·头/响应路径均从 /settings/sources 配置注入。"""

    platform = "ali1688"

    def __init__(self, conf: dict, timeout: float = 20.0, transport=None):
        self._conf = conf or {}
        self._timeout = timeout
        self._transport = transport

    def _client(self, session) -> httpx.AsyncClient:
        """按传入 session（含登录态 cookie）+ 配置的额外头构造 httpx 客户端。"""
        cookies = (session or {}).get("cookie") if isinstance(session, dict) else None
        headers = {"User-Agent": "Mozilla/5.0", **(self._conf.get("ali1688_extra_headers") or {})}
        if cookies:
            headers["Cookie"] = cookies
        kw = {"timeout": self._timeout, "headers": headers}
        if self._transport is not None:
            kw["transport"] = self._transport
        return httpx.AsyncClient(**kw)

    async def _search(self, url: str, base_params: dict, session) -> list[SupplyCandidateDTO]:
        if not url:
            return []
        params = {**base_params, **(self._conf.get("ali1688_extra_params") or {})}
        method = (self._conf.get("ali1688_method") or "GET").upper()
        path = self._conf.get("ali1688_offer_list_path") or "data.offerList"
        async with self._client(session) as c:
            if method == "POST":
                r = await c.post(url, json=params)
            else:
                r = await c.get(url, params=params)
            r.raise_for_status()
            return parse_offers(r.json(), path)

    async def image_search(self, image_url: str, *, session) -> list[SupplyCandidateDTO]:
        """拍立淘图搜：以图搜图，返回相似货源候选。"""
        return await self._search(self._conf.get("ali1688_image_search_url", ""),
                                  {"imageAddress": image_url}, session)

    async def keyword_search(self, kw: str, *, session) -> list[SupplyCandidateDTO]:
        """关键词搜索：图搜结果不足时的补充手段。"""
        return await self._search(self._conf.get("ali1688_keyword_search_url", ""),
                                  {"keywords": kw}, session)

    async def fetch_detail(self, offer_id: str, *, session) -> SupplyCandidateDTO:
        """按 offer_id 拉取商品详情（占位，联调时补齐真实端点解析）。"""
        return SupplyCandidateDTO(platform="ali1688", offer_id=offer_id)

"""Composer-api 真实请求层：cookie 头注入、随机 UA、间隔抖动、307/403/429 反爬退避，解析交由 parser。
实际请求逻辑委托给 composer_http.composer_fetch（与 RealCategoryTree 共用）。"""
from app.services.ozon_market.base import OzonProductDTO
from app.services.ozon_market.parser import parse_search_widgets
from app.services.ozon_market.composer_http import composer_fetch, CrawlerBlockedError

_ENDPOINT = "https://api.ozon.ru/composer-api.bx/page/json/v2"

__all__ = ["OzonComposerProvider", "CrawlerBlockedError"]


class OzonComposerProvider:
    name = "composer"

    def __init__(self, cookie=None, proxy: str | None = None, timeout: float = 20.0,
                 min_delay: float = 0.3, max_delay: float = 1.0, max_retries: int = 4, transport=None):
        self._cookie = cookie            # str(原始 Cookie 头) 或 dict 或 None
        self._proxy = proxy
        self._timeout = timeout
        self._min_delay = min_delay
        self._max_delay = max_delay
        self._max_retries = max(1, int(max_retries))
        self._transport = transport      # 测试注入 httpx.MockTransport

    async def _fetch(self, page_url: str) -> dict:
        return await composer_fetch(
            _ENDPOINT, {"url": page_url}, cookie=self._cookie, proxy=self._proxy,
            timeout=self._timeout, min_delay=self._min_delay, max_delay=self._max_delay,
            max_retries=self._max_retries, transport=self._transport)

    async def search_by_keyword(self, kw: str, page: int) -> list[OzonProductDTO]:
        return parse_search_widgets(await self._fetch(f"/search/?text={kw}&page={page}"))

    async def list_by_category(self, category_url: str, page: int) -> list[OzonProductDTO]:
        sep = "&" if "?" in category_url else "?"
        return parse_search_widgets(await self._fetch(f"{category_url}{sep}page={page}"))

    async def list_by_seller(self, seller_id: str, page: int) -> list[OzonProductDTO]:
        return parse_search_widgets(await self._fetch(f"/seller/{seller_id}/?page={page}"))

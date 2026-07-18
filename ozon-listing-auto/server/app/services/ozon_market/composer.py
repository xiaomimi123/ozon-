"""Composer-api 真实请求层：cookie 头注入、随机 UA、间隔抖动、307/403/429 反爬退避，解析交由 parser。"""
import asyncio
import random
import httpx
from app.services.ozon_market.base import OzonProductDTO
from app.services.ozon_market.parser import parse_search_widgets

_UA_POOL = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
]
_ENDPOINT = "https://api.ozon.ru/composer-api.bx/page/json/v2"
_BLOCK_CODES = {429, 403, 307, 301, 302}   # 反爬信号：限流/禁止/重定向到挑战页


class CrawlerBlockedError(RuntimeError):
    """疑似反爬拦截或 cookie 失效，需人工更新 cookie/代理。"""


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

    def _headers(self) -> dict:
        h = {"User-Agent": random.choice(_UA_POOL), "Accept": "application/json"}
        if isinstance(self._cookie, str) and self._cookie:
            h["Cookie"] = self._cookie
        return h

    def _client(self) -> httpx.AsyncClient:
        kw = {"timeout": self._timeout, "follow_redirects": False}
        if self._transport is not None:
            kw["transport"] = self._transport
        else:
            if self._proxy:
                kw["proxy"] = self._proxy
        if isinstance(self._cookie, dict):
            kw["cookies"] = self._cookie
        return httpx.AsyncClient(**kw)

    async def _fetch(self, page_url: str) -> dict:
        await asyncio.sleep(random.uniform(self._min_delay, self._max_delay))
        params = {"url": page_url}
        backoff = 1.0
        for _ in range(self._max_retries):
            async with self._client() as c:
                r = await c.get(_ENDPOINT, params=params, headers=self._headers())
            if r.status_code in _BLOCK_CODES:
                await asyncio.sleep(backoff)
                backoff *= 2
                continue
            r.raise_for_status()
            return r.json()
        raise CrawlerBlockedError(
            f"疑似反爬/cookie 失效，请在爬虫配置更新 cookie 或代理（url={page_url}）")

    async def search_by_keyword(self, kw: str, page: int) -> list[OzonProductDTO]:
        return parse_search_widgets(await self._fetch(f"/search/?text={kw}&page={page}"))

    async def list_by_category(self, category_url: str, page: int) -> list[OzonProductDTO]:
        sep = "&" if "?" in category_url else "?"
        return parse_search_widgets(await self._fetch(f"{category_url}{sep}page={page}"))

    async def list_by_seller(self, seller_id: str, page: int) -> list[OzonProductDTO]:
        return parse_search_widgets(await self._fetch(f"/seller/{seller_id}/?page={page}"))

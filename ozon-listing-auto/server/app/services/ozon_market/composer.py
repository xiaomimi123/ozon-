"""Composer-api 真实请求层：随机 UA、间隔抖动、429/403 指数退避，解析交由 parser。"""
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


class OzonComposerProvider:
    name = "composer"

    def __init__(self, cookies: dict | None = None, proxies: str | None = None, timeout: float = 20.0):
        self._cookies = cookies or {}
        self._proxies = proxies
        self._timeout = timeout

    async def _fetch(self, page_url: str) -> dict:
        # 随机 UA + 轻微抖动，降低被识别为脚本流量的概率
        await asyncio.sleep(random.uniform(0.2, 0.8))
        headers = {"User-Agent": random.choice(_UA_POOL), "Accept": "application/json"}
        params = {"url": page_url}
        backoff = 1.0
        for attempt in range(4):
            async with httpx.AsyncClient(
                timeout=self._timeout, cookies=self._cookies, proxy=self._proxies
            ) as c:
                r = await c.get(_ENDPOINT, params=params, headers=headers)
            if r.status_code in (429, 403):
                await asyncio.sleep(backoff)
                backoff *= 2
                continue
            r.raise_for_status()
            return r.json()
        raise RuntimeError(f"composer-api 反爬拦截，重试耗尽: {page_url}")

    async def search_by_keyword(self, kw: str, page: int) -> list[OzonProductDTO]:
        return parse_search_widgets(await self._fetch(f"/search/?text={kw}&page={page}"))

    async def list_by_category(self, category_url: str, page: int) -> list[OzonProductDTO]:
        sep = "&" if "?" in category_url else "?"
        return parse_search_widgets(await self._fetch(f"{category_url}{sep}page={page}"))

    async def list_by_seller(self, seller_id: str, page: int) -> list[OzonProductDTO]:
        return parse_search_widgets(await self._fetch(f"/seller/{seller_id}/?page={page}"))

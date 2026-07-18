"""composer-api 共享请求层：cookie 头注入、随机 UA、间隔抖动、307/403/429 反爬退避。
OzonComposerProvider 与 RealCategoryTree 共用，避免重复请求逻辑。"""
import asyncio
import random
import httpx

_UA_POOL = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
]
_BLOCK_CODES = {429, 403, 307, 301, 302}


class CrawlerBlockedError(RuntimeError):
    """疑似反爬拦截或 cookie 失效，需人工更新 cookie/代理。"""


async def composer_fetch(endpoint: str, params: dict, *, cookie=None, proxy: str | None = None,
                         timeout: float = 20.0, min_delay: float = 0.3, max_delay: float = 1.0,
                         max_retries: int = 4, transport=None) -> dict:
    await asyncio.sleep(random.uniform(min_delay, max_delay))
    backoff = 1.0
    for _ in range(max(1, int(max_retries))):
        headers = {"User-Agent": random.choice(_UA_POOL), "Accept": "application/json"}
        if isinstance(cookie, str) and cookie:
            headers["Cookie"] = cookie
        kw = {"timeout": timeout, "follow_redirects": False}
        if transport is not None:
            kw["transport"] = transport
        elif proxy:
            kw["proxy"] = proxy
        if isinstance(cookie, dict):
            kw["cookies"] = cookie
        async with httpx.AsyncClient(**kw) as c:
            r = await c.get(endpoint, params=params, headers=headers)
        if r.status_code in _BLOCK_CODES:
            await asyncio.sleep(backoff)
            backoff *= 2
            continue
        r.raise_for_status()
        return r.json()
    raise CrawlerBlockedError(
        f"疑似反爬/cookie 失效，请在爬虫配置更新 cookie 或代理（{endpoint} {params}）")

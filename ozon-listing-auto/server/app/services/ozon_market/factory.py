"""采集 Provider 工厂：按名称装配 mock/composer/apify 实现。"""
from app.services.ozon_market.base import OzonMarketProvider
from app.services.ozon_market.mock import OzonMockProvider
from app.services.ozon_market.apify import OzonApifyProvider

def get_provider(name: str) -> OzonMarketProvider:
    if name == "mock":
        return OzonMockProvider()
    if name == "apify":
        return OzonApifyProvider()
    if name == "composer":
        from app.services.ozon_market.composer import OzonComposerProvider
        return OzonComposerProvider()
    raise ValueError(f"未知 provider: {name}")


async def build_ozon_provider(session, name: str):
    """配置驱动构造：composer 读 settings/crawler(cookie/proxy/超时/间隔/重试)；mock/apify 同 get_provider。"""
    if name == "composer":
        from app.services.ozon_market.composer import OzonComposerProvider
        from app.services.crawler_conf import get_crawler_conf
        c = await get_crawler_conf(session)
        return OzonComposerProvider(
            cookie=c.get("cookie") or None, proxy=c.get("proxy") or None,
            timeout=c["timeout"], min_delay=c["min_delay"], max_delay=c["max_delay"],
            max_retries=c["max_retries"])
    return get_provider(name)

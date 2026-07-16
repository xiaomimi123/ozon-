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

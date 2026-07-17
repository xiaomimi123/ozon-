"""采集 Provider 工厂测试：mock provider 可用、未知 provider 报错。"""
import pytest
from app.services.ozon_market.factory import get_provider
from app.services.ozon_market.base import OzonProductDTO

@pytest.mark.asyncio
async def test_factory_returns_mock():
    p = get_provider("mock")
    assert p.name == "mock"
    items = await p.search_by_keyword("phone", 1)
    assert items and isinstance(items[0], OzonProductDTO)

def test_factory_unknown_raises():
    with pytest.raises(ValueError):
        get_provider("nope")

"""真实 composer-api 抓取冒烟（@live 默认跳过）。跑法：
先在后台 /settings/crawler 配好 cookie/proxy，或设 OZON_COOKIE/OZON_PROXY 环境变量后：
  .venv/bin/python -m pytest tests/test_live_crawler.py -m live -v"""
import os
import pytest
from app.services.ozon_market.composer import OzonComposerProvider


@pytest.mark.live
@pytest.mark.asyncio
async def test_live_search_returns_products():
    cookie = os.environ.get("OZON_COOKIE")
    proxy = os.environ.get("OZON_PROXY") or None
    if not cookie:
        pytest.skip("需设置 OZON_COOKIE 环境变量")
    prov = OzonComposerProvider(cookie=cookie, proxy=proxy)
    products = await prov.search_by_keyword("телефон", 1)
    assert len(products) > 0
    assert products[0].sku and products[0].title

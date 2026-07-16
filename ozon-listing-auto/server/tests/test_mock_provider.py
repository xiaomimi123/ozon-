"""OzonMockProvider 分页与变体/重复样本测试。"""
import pytest
from app.services.ozon_market.mock import OzonMockProvider

@pytest.mark.asyncio
async def test_mock_paging():
    p = OzonMockProvider(page_size=10)
    page1 = await p.search_by_keyword("x", 1)
    page2 = await p.search_by_keyword("x", 2)
    assert len(page1) == 10
    assert 1 <= len(page2) <= 10
    page3 = await p.search_by_keyword("x", 3)
    assert page3 == []

@pytest.mark.asyncio
async def test_mock_has_variant_and_duplicate_samples():
    p = OzonMockProvider(page_size=100)
    items = await p.search_by_keyword("x", 1)
    parents = [i.parent_sku for i in items if i.parent_sku]
    assert parents.count("OZ-1000") == 2                      # 变体样本
    skus = [i.sku for i in items]
    assert skus.count("OZ-1003") == 2                         # 重复 sku 样本
    phashes = [i.phash for i in items if i.phash]
    assert phashes.count("cccc3333") == 2                     # 重复 phash 样本

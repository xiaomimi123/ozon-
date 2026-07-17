import pytest
from app.services.sources.mock import MockSourceProvider

@pytest.mark.asyncio
async def test_mock_platform_scoped():
    ali = MockSourceProvider(platform="ali1688")
    pdd = MockSourceProvider(platform="pinduoduo")
    a = await ali.keyword_search("耳机", session=None)
    p = await pdd.keyword_search("耳机", session=None)
    assert all(c.platform == "ali1688" for c in a) and len(a) == 2
    assert all(c.platform == "pinduoduo" for c in p) and len(p) == 2
    al1 = next(c for c in a if c.offer_id == "AL-1")
    assert al1.supplier_info["credit_level"] == "AAA" and al1.quantity_begin == 2
    # 跨平台同款: AL-1 与 PDD-1 同图
    pdd1 = next(c for c in p if c.offer_id == "PDD-1")
    assert pdd1.image_url == al1.image_url

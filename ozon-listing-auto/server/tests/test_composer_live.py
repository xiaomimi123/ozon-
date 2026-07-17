"""OzonComposerProvider 真实网络冒烟测试，默认跳过（需 pytest -m live 显式触发）。"""
import pytest
from app.services.ozon_market.composer import OzonComposerProvider


@pytest.mark.live
@pytest.mark.asyncio
async def test_composer_live_search():
    p = OzonComposerProvider()
    items = await p.search_by_keyword("телефон", 1)
    assert isinstance(items, list)
    # 联调时：若端点可达，应解析出商品；被 CF 拦则改配 cookie/代理后重试
    print(f"live 采到 {len(items)} 条")

"""Ali1688Provider 真实网络冒烟测试，默认跳过（需 pytest -m live 显式触发）。"""
import pytest
from app.services.sources.ali1688 import Ali1688Provider


@pytest.mark.live
@pytest.mark.asyncio
async def test_ali_image_search_live():
    p = Ali1688Provider()
    items = await p.keyword_search("耳机", session=None)
    assert isinstance(items, list)
    print(f"1688 live 采到 {len(items)} 条")

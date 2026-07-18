"""真实 categoryChildV3 抓取冒烟（@live 默认跳过）。跑法：
先在后台 /settings/crawler 配好 cookie/proxy，或设 OZON_COOKIE/OZON_PROXY 环境变量后：
  OZON_COOKIE=... .venv/bin/python -m pytest tests/test_live_category_tree.py -m live -v"""
import os
import pytest
from app.services.ozon_market.category_tree_real import RealCategoryTree


@pytest.mark.live
@pytest.mark.asyncio
async def test_live_category_children():
    cookie = os.environ.get("OZON_COOKIE")
    if not cookie:
        pytest.skip("需设置 OZON_COOKIE 环境变量")
    proxy = os.environ.get("OZON_PROXY") or None
    t = RealCategoryTree(cookie=cookie, proxy=proxy)
    # 15500 = Электроника（真实一级类目，用作已知非空节点冒烟）
    nodes = await t.list_children(parent_id=15500)
    assert isinstance(nodes, list) and len(nodes) > 0
    for n in nodes:
        assert n.get("id") is not None
        assert n.get("name")
        assert n.get("path")
        assert "leaf" in n

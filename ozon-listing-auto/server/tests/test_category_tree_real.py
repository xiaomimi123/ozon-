"""RealCategoryTree × 真实 categoryChildV3 结构对齐（Task 3，§sub-project B）。
实抓样本 tests/fixtures/category_child.json：data.columns[].categories[] 才是子类目。"""
import json
from pathlib import Path

import httpx
import pytest

from app.services.ozon_market.category_tree_real import RealCategoryTree, _parse_category_children

_FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "category_child.json").read_text())


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    async def _f(*a, **k): return None
    monkeypatch.setattr("app.services.ozon_market.composer_http.asyncio.sleep", _f)


@pytest.mark.asyncio
async def test_list_children_parses_real_fixture():
    t = RealCategoryTree(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=_FIXTURE)))
    nodes = await t.list_children(parent_id=15500)
    assert len(nodes) == 3

    n0 = nodes[0]
    assert n0["id"] == 15501
    assert "Телефоны" in n0["name"]
    assert n0["path"] == "/category/telefony-i-smart-chasy-15501/"
    assert n0["leaf"] is False   # 有嵌套 categories

    assert nodes[1]["id"] == 8730
    assert nodes[1]["leaf"] is False
    assert nodes[2]["id"] == 15984
    assert nodes[2]["leaf"] is False


def test_parse_category_children_leaf_true_when_no_nested_categories():
    payload = {"data": {"columns": [{"categories": [
        {"title": "Смартфоны", "url": "/category/smartfony-15502/"},
    ]}]}}
    out = _parse_category_children(payload)
    assert len(out) == 1
    assert out[0] == {"id": 15502, "name": "Смартфоны", "path": "/category/smartfony-15502/", "leaf": True}

"""composer-api 解析器：基于真实抓取的 Ozon composer_search.json fixture 的回归测试。

fixture 由浏览器实抓（tests/fixtures/composer_search.json），widgetStates 的值本身是
JSON 字符串（真实 Ozon 行为），key 为 tileGridDesktop-3669724-default-2，
商品数据挂在 mainState 原子列表（priceV2 / textDS / labelListV2）下。
"""
import json
from pathlib import Path
from app.services.ozon_market.parser import parse_search_widgets


def _load():
    p = Path(__file__).resolve().parent / "fixtures" / "composer_search.json"
    return json.loads(p.read_text(encoding="utf-8"))


def test_parse_search_widgets_real_fixture_returns_two_products():
    dtos = parse_search_widgets(_load())
    assert len(dtos) == 2


def test_parse_search_widgets_real_fixture_product_one():
    dtos = parse_search_widgets(_load())
    p = dtos[0]
    assert p.sku == "2006925142"
    assert "CAMON 40 Pro" in p.title
    assert p.price == 18512.0
    assert p.product_url.startswith("https://www.ozon.ru/product/")
    assert p.main_image_url == "https://ir.ozone.ru/s3/multimedia-1-3/7473007263.jpg"
    assert p.rating == 4.9
    assert p.reviews_count == 1030


def test_parse_search_widgets_real_fixture_product_two():
    dtos = parse_search_widgets(_load())
    p = dtos[1]
    assert p.sku == "2640938732"
    assert p.price == 8909.0
    assert p.reviews_count == 13726

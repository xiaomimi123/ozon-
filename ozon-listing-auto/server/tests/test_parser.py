"""composer-api 响应解析器单元测试。"""
import json
from pathlib import Path
from app.services.ozon_market.parser import parse_search_widgets


def _load():
    p = Path(__file__).resolve().parents[1] / "app" / "fixtures" / "composer_search_sample.json"
    return json.loads(p.read_text(encoding="utf-8"))


def test_parse_search_widgets_extracts_products():
    dtos = parse_search_widgets(_load())
    assert len(dtos) == 2
    skus = {d.sku for d in dtos}
    assert "123" in skus
    a = next(d for d in dtos if d.sku == "123")
    assert a.title == "Товар A"
    assert a.price == 1290.0                 # "1 290 ₽" → 1290.0
    assert a.main_image_url == "https://ozon/a.jpg"


def test_parse_handles_missing_fields():
    payload = {"widgetStates": {"searchResultsV2-1": "{\"items\":[{\"sku\":9}]}"}}
    dtos = parse_search_widgets(payload)
    assert len(dtos) == 1 and dtos[0].sku == "9" and dtos[0].price is None

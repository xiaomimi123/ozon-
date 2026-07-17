import json
from pathlib import Path
from app.services.sources.parser_ali import parse_image_search

def _load():
    p = Path(__file__).resolve().parents[1] / "app" / "fixtures" / "ali_search_sample.json"
    return json.loads(p.read_text(encoding="utf-8"))

def test_parse_image_search():
    dtos = parse_image_search(_load())
    assert len(dtos) == 2
    a = next(d for d in dtos if d.offer_id == "1001")
    assert a.platform == "ali1688"
    assert a.price == 12.5 and a.quantity_begin == 2
    assert a.supplier_name == "深圳某厂"
    assert a.supplier_info["credit_level"] == "AAA"
    assert a.supplier_info["repurchase_rate"] == 0.4545        # "45.45%" → 0.4545
    # 缺字段容错
    b = next(d for d in dtos if d.offer_id == "1002")
    assert b.supplier_name is None or isinstance(b.supplier_info, dict)

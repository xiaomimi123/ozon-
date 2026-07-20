from app.services.sources.parser_import import parse_1688_search, DEFAULT_IMPORT_PATHS


def _payload():  # 符合默认路径(data.offerList / offerId / subject / priceInfo.price / imageUrl / company.name)
    return {"data": {"offerList": [
        {"offerId": 111, "subject": "连衣裙", "priceInfo": {"price": "18.5"}, "imageUrl": "http://i/1.jpg",
         "detailUrl": "http://d/111", "company": {"name": "甲店"}, "monthSold": 300},
        {"subject": "无id应跳过"},
    ]}}


def test_default_paths():
    rows = parse_1688_search(_payload())
    assert len(rows) == 1
    r = rows[0]
    assert r["offer_id"] == "111" and r["title"] == "连衣裙" and float(r["price"]) == 18.5
    assert r["image_url"] == "http://i/1.jpg" and r["shop_name"] == "甲店" and r["raw"]["offerId"] == 111


def test_custom_paths():  # 不同结构(如 onebound items.item / num_iid / pic_url / seller_nick)靠改 paths 适配
    payload = {"items": {"item": [{"num_iid": 9, "title": "T", "price": "5", "pic_url": "p", "seller_nick": "S"}]}}
    paths = {**DEFAULT_IMPORT_PATHS, "list": "items.item", "offer_id": "num_iid", "title": "title",
             "price": "price", "image": "pic_url", "shop": "seller_nick", "detail_url": "detail_url", "sales": "sales"}
    rows = parse_1688_search(payload, paths)
    assert rows[0]["offer_id"] == "9" and rows[0]["shop_name"] == "S"


def test_missing_list_returns_empty():
    assert parse_1688_search({"x": 1}) == []

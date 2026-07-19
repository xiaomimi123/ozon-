import json
import pytest
import httpx
from app.services.ozon_seller.real import RealOzonSeller, _to_ozon_attributes, _fmt_price


def _prov(handler):
    return RealOzonSeller(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_follow_offer_uses_import_by_sku():
    seen = {}
    def h(req):
        seen["path"] = req.url.path
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, json={"result": {"task_id": 123, "unmatched_sku_list": []}})
    res = await _prov(h).create_follow_offer(client_id="c", api_key="k", target_sku="298789742",
                                             barcode="460", price=2300.0, stock=5, offer_id="A1")
    assert seen["path"] == "/v1/product/import-by-sku"
    assert seen["body"]["items"][0]["sku"] == 298789742 and seen["body"]["items"][0]["offer_id"] == "A1"
    assert res.ok and res.ozon_product_id == "123" and res.status == "pending_review"


@pytest.mark.asyncio
async def test_follow_offer_unmatched_fails():
    def h(req):
        return httpx.Response(200, json={"result": {"task_id": 0, "unmatched_sku_list": [298789742]}})
    res = await _prov(h).create_follow_offer(client_id="c", api_key="k", target_sku="298789742",
                                             barcode=None, price=1.0, stock=1, offer_id="A1")
    assert not res.ok and res.status == "failed"


@pytest.mark.asyncio
async def test_create_product_uses_v3_import():
    seen = {}
    def h(req):
        seen["path"] = req.url.path
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, json={"result": {"task_id": 456}})
    res = await _prov(h).create_product(client_id="c", api_key="k", offer_id="A1", title="童鞋",
                                        description="d", category_id=17028922, attributes={"85": "Samsung"},
                                        images=["http://x/a.jpg"], price=1000.0, stock=3, barcode="460")
    assert seen["path"] == "/v3/product/import"
    it = seen["body"]["items"][0]
    assert it["name"] == "童鞋" and it["description_category_id"] == 17028922
    assert it["attributes"] == [{"complex_id": 0, "id": 85, "values": [{"value": "Samsung"}]}]
    assert res.ok and res.ozon_product_id == "456"


@pytest.mark.asyncio
@pytest.mark.parametrize("st,expect", [("imported", "approved"), ("failed", "rejected"), ("pending", "pending")])
async def test_get_status_maps(st, expect):
    def h(req):
        assert req.url.path == "/v1/product/import/info"
        return httpx.Response(200, json={"result": {"items": [{"status": st, "product_id": 9}]}})
    out = await _prov(h).get_product_status(client_id="c", api_key="k", ozon_product_id="456")
    assert out == expect


@pytest.mark.asyncio
async def test_get_status_exception_is_pending():
    def h(req):
        return httpx.Response(500)
    out = await _prov(h).get_product_status(client_id="c", api_key="k", ozon_product_id="456")
    assert out == "pending"


def test_to_ozon_attributes():
    assert _to_ozon_attributes({"85": "Samsung", "9048": "红"}) == [
        {"complex_id": 0, "id": 85, "values": [{"value": "Samsung"}]},
        {"complex_id": 0, "id": 9048, "values": [{"value": "红"}]}]
    assert _to_ozon_attributes({}) == [] and _to_ozon_attributes(None) == []


def test_fmt_price():
    assert _fmt_price(2300.0) == "2300"
    assert _fmt_price(2300.5) == "2300.5"
    assert _fmt_price(1000) == "1000"


@pytest.mark.asyncio
async def test_follow_offer_price_is_clean_string():
    seen = {}
    def h(req):
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, json={"result": {"task_id": 123, "unmatched_sku_list": []}})
    await _prov(h).create_follow_offer(client_id="c", api_key="k", target_sku="298789742",
                                       barcode="460", price=2300.0, stock=5, offer_id="A1")
    assert seen["body"]["items"][0]["price"] == "2300"


@pytest.mark.asyncio
async def test_missing_task_id_fails():
    def h(req):
        return httpx.Response(200, json={"result": {}})
    res = await _prov(h).create_follow_offer(client_id="c", api_key="k", target_sku="298789742",
                                             barcode="460", price=1.0, stock=1, offer_id="A1")
    assert not res.ok and res.status == "failed"


def _boom_transport():
    def handler(request):  # 任何真实请求都视为错误
        raise AssertionError(f"dry-run 不应发起网络: {request.url}")
    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_follow_dry_run_builds_body_without_post():
    s = RealOzonSeller(transport=_boom_transport(), dry_run=True)
    r = await s.create_follow_offer(client_id="c", api_key="k", target_sku="123",
                                    barcode="b", price=2300.0, stock=5, offer_id="OF1")
    assert r.ok and r.status == "pending_review" and r.ozon_product_id == "DRYRUN"
    body = r.raw["dry_run"]
    assert body["items"][0]["sku"] == 123
    assert body["items"][0]["price"] == "2300"
    assert body["items"][0]["offer_id"] == "OF1"


@pytest.mark.asyncio
async def test_status_dry_run_is_approved():
    s = RealOzonSeller(transport=_boom_transport(), dry_run=True)
    assert await s.get_product_status(client_id="c", api_key="k", ozon_product_id="DRYRUN") == "approved"


@pytest.mark.asyncio
async def test_create_product_dry_run_includes_full_fields():
    s = RealOzonSeller(transport=_boom_transport(), dry_run=True)
    r = await s.create_product(client_id="c", api_key="k", offer_id="OF9", title="T", description="D",
        category_id=17028922, type_id=93080, attributes={85: {"dictionary_value_id": 1000}, 9048: "手动名称"},
        images=["u1"], price=1999.0, stock=3, barcode="B", depth=100, width=80, height=50,
        weight=250, dimension_unit="mm", weight_unit="g")
    item = r.raw["dry_run"]["items"][0]
    assert item["description_category_id"] == 17028922 and item["type_id"] == 93080
    assert item["depth"] == 100 and item["weight"] == 250 and item["dimension_unit"] == "mm"
    ids = {a["id"]: a for a in item["attributes"]}
    assert ids[85]["values"][0]["dictionary_value_id"] == 1000
    assert ids[9048]["values"][0]["value"] == "手动名称"

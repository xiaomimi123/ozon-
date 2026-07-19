import json, httpx, pytest
from app.services.ozon_seller.catalog import OzonCatalog

def _transport(expect_path, reply):
    def handler(req):
        assert req.url.path == expect_path
        assert req.headers["Client-Id"] == "c" and req.headers["Api-Key"] == "k"
        return httpx.Response(200, json=reply)
    return httpx.MockTransport(handler)

@pytest.mark.asyncio
async def test_get_attributes_calls_correct_endpoint():
    reply = {"result": [{"id": 85, "name": "Бренд", "is_required": True, "dictionary_id": 28}]}
    cat = OzonCatalog(transport=_transport("/v1/description-category/attribute", reply))
    attrs = await cat.get_attributes("c", "k", category_id=17028922, type_id=93080)
    assert attrs[0]["id"] == 85 and attrs[0]["is_required"] is True

@pytest.mark.asyncio
async def test_sample_mode_no_network():
    cat = OzonCatalog(sample=True)
    assert isinstance(await cat.get_types("", ""), list)
    assert isinstance(await cat.get_attributes("", "", category_id=1, type_id=1), list)

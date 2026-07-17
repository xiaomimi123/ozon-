import pytest
from app.services.ozon_seller.factory import get_ozon_seller
from app.services.ozon_seller.base import PublishResult

@pytest.mark.asyncio
async def test_mock_ozon_seller():
    s = get_ozon_seller("mock")
    r = await s.create_follow_offer(client_id="C", api_key="K", target_sku="OZSKU1",
                                    barcode="460", price=1290.0, stock=10, offer_id="A1")
    assert isinstance(r, PublishResult)
    assert r.ok is True and r.status == "published" and r.ozon_product_id == "OZ-A1"

def test_factory_unknown():
    with pytest.raises(ValueError):
        get_ozon_seller("nope")

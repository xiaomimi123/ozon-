import pytest
from app.services.ozon_seller.mock import MockOzonSeller

@pytest.mark.asyncio
async def test_get_product_status_default_approved():
    s = MockOzonSeller()
    st = await s.get_product_status(client_id="C", api_key="K", ozon_product_id="OZ-A1")
    assert st == "approved"

@pytest.mark.asyncio
async def test_get_product_status_pending_injected():
    s = MockOzonSeller(pending_ids={"OZ-A1"})
    assert await s.get_product_status(client_id="C", api_key="K", ozon_product_id="OZ-A1") == "pending"
    assert await s.get_product_status(client_id="C", api_key="K", ozon_product_id="OZ-A2") == "approved"

import pytest
from app.services.ozon_seller.resolve import resolve_seller
from app.services.ozon_seller.mock import MockOzonSeller
from app.services.ozon_seller.real import RealOzonSeller
from app.services import settings_store

@pytest.mark.asyncio
async def test_resolve_mock_default(db_session):
    assert isinstance(await resolve_seller(db_session), MockOzonSeller)

@pytest.mark.asyncio
async def test_resolve_real_dry_run_default_true(db_session):
    await settings_store.set_value(db_session, "system", "ozon_seller_provider", "real", is_secret=False)
    seller = await resolve_seller(db_session)
    assert isinstance(seller, RealOzonSeller) and seller._dry_run is True

@pytest.mark.asyncio
async def test_resolve_real_dry_run_off(db_session):
    await settings_store.set_value(db_session, "system", "ozon_seller_provider", "real", is_secret=False)
    await settings_store.set_value(db_session, "system", "ozon_publish_dry_run", "false", is_secret=False)
    seller = await resolve_seller(db_session)
    assert isinstance(seller, RealOzonSeller) and seller._dry_run is False

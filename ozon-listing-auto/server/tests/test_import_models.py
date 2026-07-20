import pytest
from app.models import ImportCapture, ImportedProduct

@pytest.mark.asyncio
async def test_capture_and_product(db_session):
    cap = ImportCapture(platform="ali1688", keyword="连衣裙", raw={"data": {}}, item_count=1)
    db_session.add(cap); await db_session.flush()
    p = ImportedProduct(platform="ali1688", offer_id="A1", title="裙", price=12.5,
                        image_url="u", shop_name="店", detail_url="d", sales=100, raw={"offerId": "A1"},
                        capture_id=cap.id)
    db_session.add(p); await db_session.flush()
    got = await db_session.get(ImportedProduct, p.id)
    assert got.offer_id == "A1" and got.capture_id == cap.id and got.price == 12.5

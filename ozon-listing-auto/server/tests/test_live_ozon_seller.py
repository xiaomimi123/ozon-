"""真实/沙箱 Ozon Seller 冒烟(@live 默认跳过)。用法(优先沙箱店):
  OZON_CLIENT_ID=.. OZON_API_KEY=.. OZON_TARGET_SKU=.. \\
    .venv/bin/python -m pytest tests/test_live_ozon_seller.py -m live -v"""
import os, pytest
from app.services.ozon_seller.real import RealOzonSeller


@pytest.mark.live
@pytest.mark.asyncio
async def test_live_follow_offer_and_status():
    cid, key, sku = os.environ.get("OZON_CLIENT_ID"), os.environ.get("OZON_API_KEY"), os.environ.get("OZON_TARGET_SKU")
    if not (cid and key and sku):
        pytest.skip("需设置 OZON_CLIENT_ID/OZON_API_KEY/OZON_TARGET_SKU")
    prov = RealOzonSeller()
    res = await prov.create_follow_offer(client_id=cid, api_key=key, target_sku=sku, barcode=None,
                                         price=1000.0, stock=1, offer_id="live-smoke-1")
    assert res.raw is not None    # 有响应(ok 视 SKU 是否可跟卖)
    if res.ok:
        st = await prov.get_product_status(client_id=cid, api_key=key, ozon_product_id=res.ozon_product_id)
        assert st in ("approved", "pending", "rejected")

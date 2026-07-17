"""MockOzonSeller：确定性挂靠成功，供 mock-first 跑通链路。"""
from app.services.ozon_seller.base import PublishResult

class MockOzonSeller:
    name = "mock"
    async def create_follow_offer(self, *, client_id, api_key, target_sku, barcode, price, stock, offer_id) -> PublishResult:
        return PublishResult(ok=True, ozon_product_id=f"OZ-{offer_id}", status="published",
                             raw={"target_sku": target_sku, "price": price, "stock": stock})

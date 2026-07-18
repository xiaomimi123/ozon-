"""MockOzonSeller：确定性挂靠(follow)/建品(create)成功 + 审核状态(默认 approved, 可注入 pending_ids)。"""
from app.services.ozon_seller.base import PublishResult

class MockOzonSeller:
    name = "mock"
    def __init__(self, pending_ids: set | None = None):
        self._pending = pending_ids or set()
    async def create_follow_offer(self, *, client_id, api_key, target_sku, barcode, price, stock, offer_id) -> PublishResult:
        return PublishResult(ok=True, ozon_product_id=f"OZ-{offer_id}", status="published",
                             raw={"target_sku": target_sku, "price": price, "stock": stock})
    async def get_product_status(self, *, client_id, api_key, ozon_product_id) -> str:
        return "pending" if ozon_product_id in self._pending else "approved"
    async def create_product(self, *, client_id, api_key, offer_id, title, description,
                             category_id, attributes, images, price, stock, barcode) -> PublishResult:
        return PublishResult(ok=True, ozon_product_id=f"OZC-{offer_id}", status="imported",
                             raw={"title": title, "category_id": category_id, "images": len(images or []),
                                  "price": price, "stock": stock})

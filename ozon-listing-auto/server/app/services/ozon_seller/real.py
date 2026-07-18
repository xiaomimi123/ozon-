"""RealOzonSeller：以条码/SKU 调 Ozon Seller API 创建跟卖 offer(live 默认跳过, 端点联调时定)。"""
from app.services.ozon_seller.base import PublishResult

_ENDPOINT = "https://api-seller.ozon.ru/v2/product/import"   # 占位; 真实跟卖端点联调时校正

class RealOzonSeller:
    name = "real"
    _IMPORT_ENDPOINT = "https://api-seller.ozon.ru/v2/product/import"  # 占位, live 校正
    def __init__(self, timeout: float = 30.0):
        self._timeout = timeout
    async def create_follow_offer(self, *, client_id, api_key, target_sku, barcode, price, stock, offer_id) -> PublishResult:
        import httpx
        headers = {"Client-Id": client_id, "Api-Key": api_key, "Content-Type": "application/json"}
        body = {"items": [{"offer_id": offer_id, "barcode": barcode, "price": str(price),
                           "stock": stock, "sku": target_sku}]}
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as c:
                r = await c.post(_ENDPOINT, headers=headers, json=body)
                r.raise_for_status()
                data = r.json()
            return PublishResult(ok=True, ozon_product_id=str(data.get("result", {}).get("task_id", offer_id)),
                                 status="pending_review", raw=data)
        except Exception as exc:  # noqa: BLE001
            return PublishResult(ok=False, ozon_product_id=None, status="failed", error=str(exc))

    async def get_product_status(self, *, client_id, api_key, ozon_product_id) -> str:
        import httpx
        headers = {"Client-Id": client_id, "Api-Key": api_key, "Content-Type": "application/json"}
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as c:
                r = await c.post("https://api-seller.ozon.ru/v2/product/info", headers=headers,
                                 json={"product_id": ozon_product_id})   # 占位, 联调校正
                r.raise_for_status()
                data = r.json()
            # 依 Ozon 返回映射 → approved|pending|rejected; 占位默认 pending
            return "pending"
        except Exception:  # noqa: BLE001
            return "pending"

    async def create_product(self, *, client_id, api_key, offer_id, title, description,
                             category_id, attributes, images, price, stock, barcode) -> PublishResult:
        # live 后置：真实 /v2/product/import 的请求体字段/鉴权需与官方文档联调校正。
        # 占位实现：构造请求体但不保证可直接用于生产（与 create_follow_offer 同范式），
        # 且显式不发起真实网络请求，避免非 live 环境下的 live 泄漏。
        payload = {"offer_id": offer_id, "name": title, "description_category_id": category_id,
                   "attributes": attributes, "images": images, "price": str(price),
                   "stock": stock, "barcode": barcode}
        return PublishResult(ok=False, ozon_product_id=None, status="failed",
                             raw={"endpoint": self._IMPORT_ENDPOINT, "payload_keys": list(payload)},
                             error="RealOzonSeller.create_product 未联调(live 校正)")

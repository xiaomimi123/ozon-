"""RealOzonSeller：对齐真实 Ozon Seller API(api-seller.ozon.ru, Client-Id+Api-Key 头)。
跟卖 /v1/product/import-by-sku、自建 /v3/product/import、状态 /v1/product/import/info。
真实调用 @live 校验(沙箱)；非 live 用 MockTransport 测请求/响应形状。"""
from app.services.ozon_seller.base import PublishResult

_HOST = "https://api-seller.ozon.ru"
_IMPORT_BY_SKU = f"{_HOST}/v1/product/import-by-sku"   # 跟卖：按目标 SKU 克隆卡片建 offer
_IMPORT_V3 = f"{_HOST}/v3/product/import"               # 自建：创建新商品
_IMPORT_INFO = f"{_HOST}/v1/product/import/info"        # 异步导入任务状态


def _to_ozon_attributes(attrs: dict) -> list:
    """草稿 {attr_id: value} → Ozon [{complex_id,id,values:[...]}]；值为 {"dictionary_value_id": int}
    时走属性字典值 id，否则(标量或 {"value":...})走自由文本 value。"""
    out = []
    for k, v in (attrs or {}).items():
        if isinstance(v, dict) and "dictionary_value_id" in v:
            values = [{"dictionary_value_id": int(v["dictionary_value_id"])}]
        else:
            values = [{"value": str(v.get("value") if isinstance(v, dict) else v)}]
        out.append({"complex_id": 0, "id": int(k), "values": values})
    return out


def _fmt_price(v) -> str:
    """价格转字符串：整数值去掉 .0（Ozon 期望 "2300" 而非 "2300.0"）。"""
    try:
        f = float(v)
        return str(int(f)) if f.is_integer() else repr(f)
    except (TypeError, ValueError):
        return str(v)


class RealOzonSeller:
    name = "real"

    def __init__(self, timeout: float = 30.0, transport=None, dry_run: bool = False):
        self._timeout = timeout
        self._transport = transport
        self._dry_run = dry_run

    def _client(self):
        import httpx
        kw = {"timeout": self._timeout}
        if self._transport is not None:
            kw["transport"] = self._transport
        return httpx.AsyncClient(**kw)

    @staticmethod
    def _headers(client_id, api_key):
        return {"Client-Id": str(client_id), "Api-Key": str(api_key), "Content-Type": "application/json"}

    async def create_follow_offer(self, *, client_id, api_key, target_sku, barcode, price, stock, offer_id) -> PublishResult:
        body = {"items": [{"sku": int(target_sku), "offer_id": str(offer_id),
                           "price": _fmt_price(price), "currency_code": "RUB"}]}
        if self._dry_run:
            return PublishResult(ok=True, ozon_product_id="DRYRUN", status="pending_review", raw={"dry_run": body})
        try:
            async with self._client() as c:
                r = await c.post(_IMPORT_BY_SKU, headers=self._headers(client_id, api_key), json=body)
                r.raise_for_status()
                data = r.json()
            result = data.get("result", {})
            if result.get("unmatched_sku_list"):
                return PublishResult(ok=False, ozon_product_id=None, status="failed",
                                     raw=data, error=f"SKU 未匹配/禁止复制: {result['unmatched_sku_list']}")
            task_id = result.get("task_id")
            if task_id is None:
                return PublishResult(ok=False, ozon_product_id=None, status="failed",
                                     raw=data, error="Ozon 响应缺 task_id")
            return PublishResult(ok=True, ozon_product_id=str(task_id),
                                 status="pending_review", raw=data)
        except Exception as exc:  # noqa: BLE001
            return PublishResult(ok=False, ozon_product_id=None, status="failed", error=str(exc) or exc.__class__.__name__)

    async def create_product(self, *, client_id, api_key, offer_id, title, description,
                             category_id, attributes, images, price, stock, barcode,
                             type_id=None, depth=None, width=None, height=None,
                             weight=None, dimension_unit="mm", weight_unit="g") -> PublishResult:
        item = {"offer_id": str(offer_id), "name": title or "", "description_category_id": category_id,
                "type_id": type_id, "price": _fmt_price(price), "currency_code": "RUB",
                "barcode": barcode or "", "images": images or [],
                "depth": depth, "width": width, "height": height, "dimension_unit": dimension_unit,
                "weight": weight, "weight_unit": weight_unit,
                "attributes": _to_ozon_attributes(attributes)}
        if self._dry_run:
            return PublishResult(ok=True, ozon_product_id="DRYRUN", status="pending_review",
                                 raw={"dry_run": {"items": [item]}})
        try:
            async with self._client() as c:
                r = await c.post(_IMPORT_V3, headers=self._headers(client_id, api_key), json={"items": [item]})
                r.raise_for_status()
                data = r.json()
            task_id = data.get("result", {}).get("task_id")
            if task_id is None:
                return PublishResult(ok=False, ozon_product_id=None, status="failed",
                                     raw=data, error="Ozon 响应缺 task_id")
            return PublishResult(ok=True, ozon_product_id=str(task_id),
                                 status="pending_review", raw=data,
                                 error=None)
        except Exception as exc:  # noqa: BLE001
            return PublishResult(ok=False, ozon_product_id=None, status="failed", error=str(exc) or exc.__class__.__name__)

    async def get_product_status(self, *, client_id, api_key, ozon_product_id) -> str:
        # ozon_product_id 实为 create 返回的 import task_id；轮询 import/info 映射状态。
        if self._dry_run:
            return "approved"
        try:
            task_id = int(ozon_product_id)
        except (TypeError, ValueError):
            return "pending"
        try:
            async with self._client() as c:
                r = await c.post(_IMPORT_INFO, headers=self._headers(client_id, api_key), json={"task_id": task_id})
                r.raise_for_status()
                items = r.json().get("result", {}).get("items", [])
            st = (items[0].get("status") if items else "") or ""
            if st == "imported":
                return "approved"
            if st == "failed":
                return "rejected"
            return "pending"
        except Exception:  # noqa: BLE001  查询失败按未出结果处理, 不误判
            return "pending"

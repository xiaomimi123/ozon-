"""Ozon 卖家端类目/类型/属性(description-category 系列)，供自建上品取 type_id/必填属性/字典值。
注意：这与买家端 composer 类目树是两套。sample=True 或无凭证时返回内置样例。"""
import httpx

_BASE = "https://api-seller.ozon.ru"
_TREE = "/v1/description-category/tree"
_ATTR = "/v1/description-category/attribute"
_ATTR_VALUES = "/v1/description-category/attribute/values"

_SAMPLE_TYPES = [{"category_id": 17028922, "category_name": "示例类目",
                  "types": [{"type_id": 93080, "type_name": "示例类型"}]}]
_SAMPLE_ATTRS = [{"id": 85, "name": "品牌", "is_required": True, "dictionary_id": 28},
                 {"id": 9048, "name": "商品名称", "is_required": True, "dictionary_id": 0}]
_SAMPLE_VALUES = [{"id": 1000, "value": "示例值A"}, {"id": 1001, "value": "示例值B"}]


class OzonCatalog:
    def __init__(self, timeout: float = 30.0, transport=None, sample: bool = False):
        self._timeout = timeout
        self._transport = transport
        self._sample = sample

    def _client(self):
        return httpx.AsyncClient(base_url=_BASE, timeout=self._timeout, transport=self._transport)

    @staticmethod
    def _headers(client_id, api_key):
        return {"Client-Id": str(client_id), "Api-Key": str(api_key), "Content-Type": "application/json"}

    async def _post(self, path, client_id, api_key, body):
        async with self._client() as c:
            r = await c.post(path, headers=self._headers(client_id, api_key), json=body)
            r.raise_for_status()
            return r.json()

    async def get_types(self, client_id, api_key):
        if self._sample or not client_id:
            return _SAMPLE_TYPES
        return (await self._post(_TREE, client_id, api_key, {})).get("result", [])

    async def get_attributes(self, client_id, api_key, *, category_id, type_id):
        if self._sample or not client_id:
            return _SAMPLE_ATTRS
        body = {"description_category_id": category_id, "type_id": type_id}
        return (await self._post(_ATTR, client_id, api_key, body)).get("result", [])

    async def get_attribute_values(self, client_id, api_key, *, category_id, type_id, attribute_id):
        if self._sample or not client_id:
            return _SAMPLE_VALUES
        body = {"description_category_id": category_id, "type_id": type_id,
                "attribute_id": attribute_id, "limit": 100}
        return (await self._post(_ATTR_VALUES, client_id, api_key, body)).get("result", [])

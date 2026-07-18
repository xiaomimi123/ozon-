"""RealCategoryTree：composer categoryChildV3 → 真实 Ozon 类目树。复用 composer_fetch(cookie/proxy/退避)。
解析层独立；categoryChildV3 真实结构由 Task 3 用实抓样本对齐(此处为初版容错解析)。"""
from app.services.ozon_market.composer_http import composer_fetch

_CATEGORY_CHILD = "https://api.ozon.ru/composer-api.bx/_action/v2/categoryChildV3"


class RealCategoryTree:
    name = "real"

    def __init__(self, cookie=None, proxy: str | None = None, timeout: float = 20.0,
                 max_retries: int = 4, transport=None):
        self._cookie = cookie
        self._proxy = proxy
        self._timeout = timeout
        self._max_retries = max_retries
        self._transport = transport

    async def list_children(self, *, parent_id: int | None) -> list[dict]:
        params = {"categoryId": parent_id} if parent_id is not None else {}
        data = await composer_fetch(_CATEGORY_CHILD, params, cookie=self._cookie, proxy=self._proxy,
                                    timeout=self._timeout, max_retries=self._max_retries, transport=self._transport)
        return _parse_category_children(data)   # Task 3 对齐真实结构

    def all_leaves(self) -> list[dict]:
        return []   # 真实树巨大；suggest_category 对非 mock 树用 list_children(parent_id=None)


def _parse_category_children(payload: dict) -> list[dict]:
    """初版容错解析（Task 3 用实抓样本对齐真实字段路径）。找不到返回 []，不崩。"""
    items = payload.get("categories") or payload.get("items") or []
    out = []
    for it in items if isinstance(items, list) else []:
        cid = it.get("id") or it.get("categoryId")
        if cid is None:
            continue
        out.append({"id": int(cid), "name": it.get("title") or it.get("name"),
                    "path": it.get("path") or it.get("title") or it.get("name"),
                    "leaf": bool(it.get("isLeaf") or it.get("leaf"))})
    return out

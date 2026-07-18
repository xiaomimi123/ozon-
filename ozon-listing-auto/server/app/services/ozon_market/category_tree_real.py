"""RealCategoryTree：composer categoryChildV3 → 真实 Ozon 类目树。复用 composer_fetch(cookie/proxy/退避)。
真实响应结构（Task 3 用实抓样本 tests/fixtures/category_child.json 对齐）：
payload["data"] 是 {id,title,url,columns,...}；data["columns"] 是 [{categories:[...]}]，
展开所有 columns[].categories[] 即为查询类目的直接子类目。每个子节点：
title→name；url（如 /category/xxx-15501/）→ path，并用其末尾数字作 id；
子节点自身若带非空 categories → 非叶子(leaf=False)，否则叶子(leaf=True)。"""
import re

from app.services.ozon_market.composer_http import composer_fetch

_CATEGORY_CHILD = "https://api.ozon.ru/composer-api.bx/_action/v2/categoryChildV3"
_MENU_ID = 185


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
        if parent_id is not None:
            params = {"menuId": _MENU_ID, "categoryId": parent_id, "hash": ""}
        else:
            params = {"menuId": _MENU_ID}
        data = await composer_fetch(_CATEGORY_CHILD, params, cookie=self._cookie, proxy=self._proxy,
                                    timeout=self._timeout, max_retries=self._max_retries, transport=self._transport)
        return _parse_category_children(data)   # Task 3 对齐真实结构

    def all_leaves(self) -> list[dict]:
        return []   # 真实树巨大；suggest_category 对非 mock 树用 list_children(parent_id=None)


def _parse_category_children(payload: dict) -> list[dict]:
    """真实 categoryChildV3 结构解析：data.columns[].categories[] → 子类目列表。
    对遗留/非预期结构（无 data.columns，直接是 categories 列表）也容错回退。
    任何非预期结构都跳过/返回 []，绝不崩。"""
    if not isinstance(payload, dict):
        return []
    data = payload.get("data")
    if not isinstance(data, dict):
        data = payload   # 容错回退：payload 本身当作 data（无 "data" 包裹的旧/异形结构）

    columns = data.get("columns")
    if isinstance(columns, list):
        items: list = []
        for col in columns:
            if not isinstance(col, dict):
                continue
            cats = col.get("categories")
            if isinstance(cats, list):
                items.extend(cats)
    else:
        items = data.get("categories") or data.get("items") or []
    if not isinstance(items, list):
        return []

    out = []
    for it in items:
        if not isinstance(it, dict):
            continue
        name = it.get("title") or it.get("name")
        url = it.get("url")
        if isinstance(url, str) and url:
            nums = re.findall(r"\d+", url)
            if not nums:
                continue
            try:
                cid = int(nums[-1])
            except (TypeError, ValueError):
                continue
            path = url
            children = it.get("categories")
            leaf = not (isinstance(children, list) and len(children) > 0)
        else:
            cid = it.get("id") or it.get("categoryId")
            if cid is None:
                continue
            try:
                cid = int(cid)
            except (TypeError, ValueError):
                continue
            path = it.get("path") or name
            leaf = bool(it.get("isLeaf") or it.get("leaf"))
        out.append({"id": cid, "name": name, "path": path, "leaf": leaf})
    return out

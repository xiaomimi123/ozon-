"""类目属性映射（§5.7）：记忆表优先 → LLM 建议 → 兜底默认；确认写回草稿 + upsert 记忆表复用。"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import CategoryMap, ListingDraft
from app.services.category_tree import MockCategoryTree

_FALLBACK_CATEGORY = {"category_id": 15621048, "path": "Дом", "attributes": {}}


def _signature(candidate) -> str:
    """归一化签名：取标题前若干词做 key（跨任务复用同类商品的类目映射）。"""
    t = (candidate.title or "").strip().lower()
    return t[:120] if t else f"cand-{candidate.id}"


async def suggest_category(session: AsyncSession, candidate, *, llm, tree=None) -> dict:
    tree = tree or MockCategoryTree()
    sig = _signature(candidate)
    row = (await session.execute(select(CategoryMap).where(CategoryMap.signature == sig))).scalar_one_or_none()
    if row and row.confirmed and row.ozon_category_id is not None:
        row.usage_count = (row.usage_count or 0) + 1
        return {"category_id": row.ozon_category_id, "path": row.ozon_category_path,
                "attributes": row.attributes or {}, "source": "memory"}
    # 未命中记忆 → LLM 建议（结构化 JSON）
    leaves = tree.all_leaves() if isinstance(tree, MockCategoryTree) else await tree.list_children(parent_id=None)
    catalog = "; ".join(f'{n["id"]}={n["path"]}' for n in leaves)
    prompt = ("从以下 Ozon 类目中为该商品选最合适的一个，并给出关键属性，"
              f'返回 JSON {{"category_id":int,"path":str,"attributes":object}}。'
              f'\n商品标题: {candidate.title}\n候选类目: {catalog}')
    try:
        data = await llm.extract_json(prompt)
    except Exception:  # noqa: BLE001
        data = {}
    cid = data.get("category_id") if isinstance(data, dict) else None
    if cid:
        return {"category_id": int(cid), "path": data.get("path"),
                "attributes": data.get("attributes") or {}, "source": "llm"}
    return {**_FALLBACK_CATEGORY, "source": "fallback"}


async def confirm_category(session: AsyncSession, draft_id: int, *, category_id: int,
                           attributes: dict, path: str | None = None, signature: str | None = None) -> dict:
    d = (await session.execute(select(ListingDraft).where(ListingDraft.id == draft_id))).scalar_one()
    d.category_id = category_id
    d.attributes = attributes
    sig = signature or (d.title or "").strip().lower()[:120] or f"draft-{draft_id}"
    row = (await session.execute(select(CategoryMap).where(CategoryMap.signature == sig))).scalar_one_or_none()
    if not row:
        row = CategoryMap(signature=sig); session.add(row)
    row.source_hint = d.title
    row.ozon_category_id = category_id
    row.ozon_category_path = path
    row.attributes = attributes
    row.confirmed = True
    return {"draft_id": draft_id, "category_id": category_id}

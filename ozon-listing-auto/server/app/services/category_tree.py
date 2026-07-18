"""Ozon 类目树 provider（§5.7）：mock 固定小树；real 走 composer-api categoryChildV3（live 后置）。"""
from __future__ import annotations
from typing import Protocol

# mock 固定小树：id/name/path/leaf/parent（供 LLM 候选 + 前端下拉）
_MOCK_TREE = [
    {"id": 17027492, "name": "Одежда", "path": "Одежда", "leaf": False, "parent": None},
    {"id": 17028922, "name": "Обувь", "path": "Обувь", "leaf": False, "parent": None},
    {"id": 15621048, "name": "Дом", "path": "Дом", "leaf": False, "parent": None},
    {"id": 17028930, "name": "Детская обувь", "path": "Обувь/Детская обувь", "leaf": True, "parent": 17028922},
    {"id": 17028931, "name": "Женская обувь", "path": "Обувь/Женская обувь", "leaf": True, "parent": 17028922},
    {"id": 17027500, "name": "Футболки", "path": "Одежда/Футболки", "leaf": True, "parent": 17027492},
]


class CategoryTreeProvider(Protocol):
    name: str
    async def list_children(self, *, parent_id: int | None) -> list[dict]: ...


class MockCategoryTree:
    name = "mock"

    async def list_children(self, *, parent_id: int | None) -> list[dict]:
        return [{"id": n["id"], "name": n["name"], "path": n["path"], "leaf": n["leaf"]}
                for n in _MOCK_TREE if n["parent"] == parent_id]

    def all_leaves(self) -> list[dict]:
        return [n for n in _MOCK_TREE if n["leaf"]]


def get_category_tree(name: str = "mock") -> CategoryTreeProvider:
    if name == "mock":
        return MockCategoryTree()
    if name == "real":
        from app.services.ozon_market.category_tree_real import RealCategoryTree  # live 后置
        return RealCategoryTree()
    raise ValueError(f"未知 category tree: {name}")

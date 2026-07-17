"""类目 API schema(§5.7)。"""
from pydantic import BaseModel


class CategoryNode(BaseModel):
    id: int
    name: str
    path: str
    leaf: bool


class SuggestOut(BaseModel):
    category_id: int | None = None
    path: str | None = None
    attributes: dict = {}
    source: str


class ConfirmCategoryIn(BaseModel):
    category_id: int
    attributes: dict = {}
    path: str | None = None

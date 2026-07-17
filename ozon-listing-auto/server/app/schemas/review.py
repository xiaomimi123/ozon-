"""审核 API schema。"""
from typing import Literal
from pydantic import BaseModel

class DecisionIn(BaseModel):
    decision: Literal["adopt", "reject"]
    note: str | None = None

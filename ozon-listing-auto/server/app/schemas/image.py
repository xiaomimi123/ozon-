"""改图 API schema。"""
from pydantic import BaseModel, ConfigDict


class ImageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    candidate_id: int
    source_url: str | None = None
    op: str
    provider: str
    result_url: str | None = None
    sort: int
    status: str


class ProcessOut(BaseModel):
    processed: int
    failed: int

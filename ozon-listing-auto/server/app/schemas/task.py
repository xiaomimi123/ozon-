"""采集任务的请求/响应 Pydantic 模型。"""
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field

class TaskCreate(BaseModel):
    name: str
    listing_mode: str = "follow"
    entry_type: str
    entry_value: str
    provider: str = "mock"
    source_platforms: list[str] = Field(default_factory=lambda: ["ali1688", "pinduoduo"])
    review_config: dict | None = None

class TaskOut(BaseModel):
    id: int
    name: str
    listing_mode: str
    entry_type: str
    entry_value: str
    provider: str
    source_platforms: list[str]
    review_config: dict | None
    status: str
    stats: dict | None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

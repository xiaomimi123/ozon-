"""账号池 API 的请求/响应 schema（响应不含凭据）。"""
from datetime import datetime
from pydantic import BaseModel, ConfigDict

class AccountCreate(BaseModel):
    platform: str
    label: str | None = None
    credentials: dict
    daily_limit: int = 200
    min_interval_sec: int = 6

class AccountUpdate(BaseModel):
    label: str | None = None
    daily_limit: int | None = None
    min_interval_sec: int | None = None
    status: str | None = None
    credentials: dict | None = None

class AccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    platform: str
    label: str | None
    status: str
    daily_limit: int
    min_interval_sec: int
    daily_used_count: int
    cooldown_until: datetime | None
    risk_hits: int
    created_at: datetime

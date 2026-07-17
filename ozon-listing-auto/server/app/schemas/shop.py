"""店铺 API schema(响应不含 api_key)。"""
from datetime import datetime
from pydantic import BaseModel, ConfigDict

class ShopCreate(BaseModel):
    name: str
    client_id: str
    api_key: str
    is_sandbox: bool = True

class ShopUpdate(BaseModel):
    name: str | None = None
    client_id: str | None = None
    api_key: str | None = None
    is_active: bool | None = None
    is_sandbox: bool | None = None

class ShopOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    platform: str
    client_id: str
    is_active: bool
    is_sandbox: bool
    created_at: datetime

from datetime import datetime
from pydantic import BaseModel

class UserCreate(BaseModel):
    username: str
    password: str
    role: str = "operator"

class UserUpdate(BaseModel):
    role: str | None = None
    is_active: bool | None = None

class PasswordReset(BaseModel):
    password: str

class UserOut(BaseModel):
    model_config = {"from_attributes": True}
    id: int
    username: str
    role: str
    is_active: bool
    created_at: datetime

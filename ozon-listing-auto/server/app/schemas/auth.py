"""鉴权相关的请求/响应模型。"""
from pydantic import BaseModel

class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str

class UserOut(BaseModel):
    id: int
    username: str
    role: str

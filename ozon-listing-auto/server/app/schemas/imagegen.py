"""AI 生图 provider 配置 API schema(§5.5.5)。"""
from pydantic import BaseModel


class ImagegenIn(BaseModel):
    provider: str = "mock"          # mock|local|openai_compat|http
    img_base_url: str = ""
    img_api_key: str = ""
    img_model: str = ""
    fallback: str = ""              # 降级顺序，逗号分隔


class ImagegenOut(BaseModel):
    provider: str = "mock"
    img_base_url: str = ""
    img_api_key: str | None = None  # 脱敏
    img_model: str = ""
    fallback: str = ""

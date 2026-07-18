"""爬虫配置 API schema：cookie/proxy(脱敏) + 超时/延迟/重试。"""
from pydantic import BaseModel

class CrawlerIn(BaseModel):
    cookie: str = ""
    proxy: str = ""
    timeout: float = 20.0
    min_delay: float = 0.3
    max_delay: float = 1.0
    max_retries: int = 4

class CrawlerOut(BaseModel):
    cookie: str | None = None      # 脱敏
    proxy: str | None = None       # 脱敏
    timeout: float = 20.0
    min_delay: float = 0.3
    max_delay: float = 1.0
    max_retries: int = 4

"""按平台名返回 SourceProvider 实现；真实 provider 惰性 import。"""
from app.services.sources.base import SourceProvider
from app.services.sources.mock import MockSourceProvider

def get_source_provider(platform: str) -> SourceProvider:
    if platform == "mock":
        return MockSourceProvider()
    if platform == "ali1688":
        from app.services.sources.ali1688 import Ali1688Provider
        return Ali1688Provider()
    if platform == "pinduoduo":
        from app.services.sources.pinduoduo import PinduoduoProvider
        return PinduoduoProvider()
    raise ValueError(f"未知货源平台: {platform}")

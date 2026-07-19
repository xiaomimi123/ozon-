"""按平台名返回 SourceProvider 实现；真实 provider 惰性 import。"""
from app.services.sources.base import SourceProvider
from app.services.sources.mock import MockSourceProvider

def get_source_provider(platform: str) -> SourceProvider:
    if platform == "mock":
        return MockSourceProvider()
    if platform == "ali1688":
        raise ValueError("ali1688 须经 build_source_provider 从 /settings/sources 配置构造")
    if platform == "pinduoduo":
        from app.services.sources.pinduoduo import PinduoduoProvider
        return PinduoduoProvider()
    raise ValueError(f"未知货源平台: {platform}")


async def build_source_provider(session_factory, platform):
    """配置驱动：ali1688 读 /settings/sources 构造 Ali1688Provider(conf)；mock/pinduoduo 同 get_source_provider。"""
    if platform == "ali1688":
        from app.services.sources.ali1688 import Ali1688Provider
        from app.services.sources.conf import get_source_conf
        async with session_factory() as s:
            conf = await get_source_conf(s)
        return Ali1688Provider(conf)
    return get_source_provider(platform)

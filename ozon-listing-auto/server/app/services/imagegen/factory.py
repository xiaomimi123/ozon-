"""按名返回 ImageProvider + 分派器：本地类操作走 LocalProvider，gen 走配置的外部/mock provider。"""
from app.services.imagegen.base import ImageProvider, ImageResult, LOCAL_OPS, GEN_OPS
from app.services.imagegen.mock import MockImageProvider
from app.services.imagegen.local import LocalProvider

DEFAULT_STATIC_DIR = "static/images"


def get_image_provider(name: str = "mock", *, static_dir: str = DEFAULT_STATIC_DIR) -> ImageProvider:
    if name == "mock":
        return MockImageProvider()
    if name == "local":
        return LocalProvider(static_dir)
    if name == "openai_compat":
        from app.services.imagegen.openai_compat import OpenAICompatImageProvider
        return OpenAICompatImageProvider()
    if name == "http":
        from app.services.imagegen.http import HttpImageProvider
        return HttpImageProvider()
    raise ValueError(f"未知 image provider: {name}")


async def process_op(op: str, *, image: bytes, params: dict, static_dir: str = DEFAULT_STATIC_DIR,
                     gen_provider: str = "mock") -> ImageResult:
    """本地类操作(rmbg/whitebg/watermark/crop_norm)恒走 LocalProvider；gen 走配置的外部 provider(默认 mock)。"""
    if op in LOCAL_OPS:
        return await LocalProvider(static_dir).process(image=image, op=op, params=params)
    if op in GEN_OPS:
        return await get_image_provider(gen_provider, static_dir=static_dir).process(image=image, op=op, params=params)
    raise ValueError(f"未知 op: {op}")

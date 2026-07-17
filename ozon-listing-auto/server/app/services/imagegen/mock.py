"""MockImageProvider：确定性占位产物（默认，测试/演示，无外部依赖）。"""
import hashlib
from app.services.imagegen.base import ImageResult


class MockImageProvider:
    name = "mock"

    async def process(self, *, image: bytes, op: str, params: dict) -> ImageResult:
        h = hashlib.sha1(image + op.encode()).hexdigest()[:12]   # 确定性：同输入同产物名
        return ImageResult(url=f"/static/images/mock_{op}_{h}.png", provider="mock",
                           meta={"op": op, "mock": True})

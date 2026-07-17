"""HttpImageProvider：通用 HTTP 适配器(GRSAI/云舞AI 等非 OpenAI 格式)，字段映射可配，live 后置。"""
from app.services.imagegen.base import ImageResult


class HttpImageProvider:
    name = "http"

    async def process(self, *, image: bytes, op: str, params: dict) -> ImageResult:
        raise NotImplementedError("HttpImageProvider 未联调(live 校正)")

"""OpenAICompatImageProvider：走 OpenAI 兼容图像接口(如千问万相)，live 后置。"""
from app.services.imagegen.base import ImageResult


class OpenAICompatImageProvider:
    name = "openai_compat"

    async def process(self, *, image: bytes, op: str, params: dict) -> ImageResult:
        # live：真实调用 {img_base_url}/images/generations，此处占位不发网络请求。
        raise NotImplementedError("OpenAICompatImageProvider 未联调(live 校正)")

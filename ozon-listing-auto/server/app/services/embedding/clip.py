"""ChineseClipEmbedder：cn_clip ViT-B/16 CPU 推理（Task 10 实现真实版）。"""
from app.models.supply_candidate import EMBED_DIM

class ChineseClipEmbedder:
    dim = EMBED_DIM
    async def embed_image(self, image_url: str) -> list[float]:
        raise NotImplementedError("ChineseClipEmbedder 将在 Task 10 实现真实 CLIP 推理")
    async def embed_images(self, urls: list[str]) -> list[list[float]]:
        raise NotImplementedError

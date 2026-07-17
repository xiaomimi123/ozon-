"""图像向量 Embedder 抽象（CLIP）。"""
from typing import Protocol

class Embedder(Protocol):
    dim: int
    async def embed_image(self, image_url: str) -> list[float]: ...
    async def embed_images(self, urls: list[str]) -> list[list[float]]: ...

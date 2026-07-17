"""MockEmbedder：对 URL 做确定性哈希 → 归一化 512 维向量，供测试/开发（无模型/网络）。"""
import hashlib
import math
from app.models.supply_candidate import EMBED_DIM

class MockEmbedder:
    dim = EMBED_DIM
    async def embed_image(self, image_url: str) -> list[float]:
        vec: list[float] = []
        i = 0
        seed = (image_url or "").encode()
        while len(vec) < self.dim:
            h = hashlib.sha256(seed + i.to_bytes(4, "big")).digest()
            for b in h:
                vec.append(b / 255.0 - 0.5)
                if len(vec) == self.dim:
                    break
            i += 1
        norm = math.sqrt(sum(x * x for x in vec)) or 1.0
        return [x / norm for x in vec]
    async def embed_images(self, urls: list[str]) -> list[list[float]]:
        return [await self.embed_image(u) for u in urls]

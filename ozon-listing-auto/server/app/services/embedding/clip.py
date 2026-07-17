"""ChineseClipEmbedder：cn_clip ViT-B/16 CPU 推理，懒加载，图 URL → 512 维向量。

注意：torch / cn_clip / PIL / httpx 均在方法内部懒加载导入，而非模块顶层——
未安装 [ml] 可选依赖组时，其余测试套件仍可正常 import 本模块（不会因缺 torch 报错）。
"""
import io
from app.models.supply_candidate import EMBED_DIM

_MAX_RETRIES = 3


class ChineseClipEmbedder:
    """中文 CLIP（cn_clip ViT-B/16）图像向量化，CPU 推理，模型懒加载单例。"""

    dim = EMBED_DIM

    def __init__(self):
        self._model = None
        self._preprocess = None
        self._torch = None

    def _load(self):
        """首次调用时才导入并加载模型，避免未安装 torch 时模块级导入失败。"""
        if self._model is None:
            import torch
            from cn_clip.clip import load_from_name
            self._torch = torch
            self._model, self._preprocess = load_from_name("ViT-B-16", device="cpu")
            self._model.eval()

    async def embed_image(self, image_url: str) -> list[float]:
        """下载图片并编码为 512 维归一化向量；网络失败时重试。"""
        import httpx
        from PIL import Image

        self._load()
        last_exc: Exception | None = None
        content: bytes | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                async with httpx.AsyncClient(timeout=20.0) as c:
                    r = await c.get(image_url)
                    r.raise_for_status()
                    content = r.content
                break
            except (httpx.HTTPError, httpx.TimeoutException) as exc:
                last_exc = exc
                if attempt == _MAX_RETRIES - 1:
                    raise
        if content is None:
            raise last_exc  # pragma: no cover - 理论上不可达，保护性兜底

        img = Image.open(io.BytesIO(content)).convert("RGB")
        tensor = self._preprocess(img).unsqueeze(0)
        with self._torch.no_grad():
            feat = self._model.encode_image(tensor)
            feat = feat / feat.norm(dim=-1, keepdim=True)
        return feat[0].tolist()

    async def embed_images(self, urls: list[str]) -> list[list[float]]:
        """批量向量化（逐张调用 embed_image，保持接口简单）。"""
        return [await self.embed_image(u) for u in urls]

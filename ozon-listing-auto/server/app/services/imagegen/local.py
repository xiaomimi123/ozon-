"""LocalProvider：Pillow 本地真实处理（whitebg/watermark/crop_norm），rmbg 惰性 rembg 降级。
产物写 static_dir，文件名用内容 hash 保证确定性（测试可复现）。"""
import hashlib
import io
import os
from PIL import Image, ImageDraw
from app.services.imagegen.base import ImageResult


class LocalProvider:
    name = "local"

    def __init__(self, static_dir: str):
        self.static_dir = static_dir
        os.makedirs(static_dir, exist_ok=True)

    def _save(self, img: Image.Image, op: str, seed: bytes) -> str:
        h = hashlib.sha1(seed + op.encode()).hexdigest()[:12]
        fname = f"{op}_{h}.png"
        img.save(os.path.join(self.static_dir, fname), format="PNG")
        return f"/static/{fname}"

    async def process(self, *, image: bytes, op: str, params: dict) -> ImageResult:
        meta: dict = {"op": op, "degraded": False}
        img = Image.open(io.BytesIO(image))
        if op == "whitebg":
            img = self._whitebg(img)
        elif op == "crop_norm":
            size = params.get("size") or [800, 800]
            img = self._crop_norm(img, int(size[0]), int(size[1]))
        elif op == "watermark":
            img = self._watermark(img.convert("RGBA"), str(params.get("text", "OZON"))).convert("RGB")
        elif op == "rmbg":
            img, degraded = self._rmbg(img)
            meta["degraded"] = degraded
        else:
            raise ValueError(f"LocalProvider 不支持 op={op}")
        if img.mode == "RGBA":
            img = img.convert("RGB")
        url = self._save(img, op, image)
        return ImageResult(url=url, provider="local", meta=meta)

    def _whitebg(self, img: Image.Image) -> Image.Image:
        img = img.convert("RGBA")
        bg = Image.new("RGBA", img.size, (255, 255, 255, 255))
        bg.alpha_composite(img)
        return bg.convert("RGB")

    def _crop_norm(self, img: Image.Image, tw: int, th: int) -> Image.Image:
        img = img.convert("RGB")
        sw, sh = img.size
        scale = max(tw / sw, th / sh)
        img = img.resize((max(1, round(sw * scale)), max(1, round(sh * scale))))
        rw, rh = img.size
        left, top = (rw - tw) // 2, (rh - th) // 2
        return img.crop((left, top, left + tw, top + th))

    def _watermark(self, img: Image.Image, text: str) -> Image.Image:
        draw = ImageDraw.Draw(img)
        draw.text((5, 5), text, fill=(255, 255, 255, 180))
        return img

    def _rmbg(self, img: Image.Image):
        try:
            from rembg import remove   # 惰性：仅 INSTALL_ML 环境有
            out = remove(img)
            return out, False
        except Exception:               # noqa: BLE001  无 rembg/onnx 时降级白底
            return self._whitebg(img), True

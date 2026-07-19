"""OpenAICompatImageProvider：标准 OpenAI 图像接口(images/generations)文生图。默认适配千问万相等 OpenAI 兼容端点。"""
import base64
import httpx
from app.services.imagegen.base import ImageResult
from app.services.imagegen.save import save_image_bytes
from app.services.imagegen.factory import DEFAULT_STATIC_DIR


class OpenAICompatImageProvider:
    name = "openai_compat"

    def __init__(self, base_url: str, api_key: str, model: str,
                 static_dir: str = DEFAULT_STATIC_DIR, timeout: float = 30.0, transport=None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.static_dir = static_dir
        self.timeout = timeout
        self.transport = transport

    def _client(self) -> httpx.AsyncClient:
        kw = {"timeout": self.timeout}
        if self.transport is not None:
            kw["transport"] = self.transport
        return httpx.AsyncClient(**kw)

    async def process(self, *, image: bytes, op: str, params: dict) -> ImageResult:
        prompt = params.get("prompt") or ""
        body = {"model": self.model, "prompt": prompt, "n": 1,
                "size": params.get("size", "1024x1024"), "response_format": "url"}
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        last = None
        for _ in range(3):
            try:
                async with self._client() as c:
                    r = await c.post(f"{self.base_url}/images/generations", json=body, headers=headers)
                    r.raise_for_status()
                    item = (r.json().get("data") or [{}])[0]
                    if item.get("url"):
                        ir = await c.get(item["url"])
                        ir.raise_for_status()
                        raw = ir.content
                    elif item.get("b64_json"):
                        raw = base64.b64decode(item["b64_json"])
                    else:
                        raise RuntimeError("生图响应缺 url/b64_json")
                url = save_image_bytes(raw, self.static_dir)
                return ImageResult(url=url, provider="openai_compat", meta={"op": "gen", "model": self.model})
            except Exception as exc:  # noqa: BLE001  重试；耗尽抛
                last = exc
        raise RuntimeError(f"OpenAICompat 生图失败: {last}")

"""HttpImageProvider：通用 HTTP 生图适配器。请求体模板({prompt}/{model} 占位)+响应取图路径(点路径)可配，接非 OpenAI 格式服务。"""
import base64
import json
import httpx
from app.services.imagegen.base import ImageResult
from app.services.imagegen.save import save_image_bytes
from app.services.imagegen.factory import DEFAULT_STATIC_DIR


def _dig(obj, path: str):
    """点路径提取：'data.0.url' → obj['data'][0]['url']；缺失返回 None。"""
    cur = obj
    for part in path.split("."):
        if isinstance(cur, list):
            try:
                cur = cur[int(part)]
            except (ValueError, IndexError):
                return None
        elif isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
        if cur is None:
            return None
    return cur


class HttpImageProvider:
    name = "http"

    def __init__(self, base_url: str, api_key: str, model: str, request_template: str, response_path: str,
                 static_dir: str = DEFAULT_STATIC_DIR, timeout: float = 30.0, transport=None):
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self.request_template = request_template
        self.response_path = response_path
        self.static_dir = static_dir
        self.timeout = timeout
        self.transport = transport

    def _client(self):
        kw = {"timeout": self.timeout}
        if self.transport is not None:
            kw["transport"] = self.transport
        return httpx.AsyncClient(**kw)

    async def process(self, *, image: bytes, op: str, params: dict) -> ImageResult:
        prompt = params.get("prompt") or ""
        # 模板占位替换（JSON 安全：用 json.dumps 转义后去掉外层引号）
        body_str = (self.request_template
                    .replace("{prompt}", json.dumps(prompt)[1:-1])
                    .replace("{model}", json.dumps(self.model)[1:-1]))
        body = json.loads(body_str)
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        async with self._client() as c:
            r = await c.post(self.base_url, json=body, headers=headers)
            r.raise_for_status()
            val = _dig(r.json(), self.response_path)
            if not val:
                raise RuntimeError(f"生图响应按路径 {self.response_path} 取图为空")
            if isinstance(val, str) and val.startswith("http"):
                ir = await c.get(val)
                ir.raise_for_status()
                raw = ir.content
            else:
                raw = base64.b64decode(val)
        url = save_image_bytes(raw, self.static_dir)
        return ImageResult(url=url, provider="http", meta={"op": "gen", "path": self.response_path})

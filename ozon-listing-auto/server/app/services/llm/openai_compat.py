"""OpenAICompatLLM：OpenAI 兼容 Chat Completions（默认通义千问 DashScope）。"""
import json
import re
import asyncio


def _parse_json_loose(text: str) -> dict:
    """从模型返回文本中容错解析 JSON：去掉 ```json 代码围栏、截取 {...} 片段，解析失败返回 {}。"""
    if not text:
        return {}
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    raw = m.group(1) if m else text
    m2 = re.search(r"\{.*\}", raw, re.DOTALL)
    if m2:
        raw = m2.group(0)
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}


class OpenAICompatLLM:
    """OpenAI 兼容 Chat Completions 客户端，默认对接通义千问 DashScope。"""

    name = "openai"

    def __init__(self, base_url: str, api_key: str, model: str, timeout: float = 30.0):
        self.base_url = base_url.rstrip("/"); self.api_key = api_key; self.model = model; self.timeout = timeout

    async def chat(self, messages: list[dict], *, temperature: float = 0.0, **opts) -> str:
        """POST {base_url}/chat/completions，Bearer 鉴权，失败重试 3 次。"""
        import httpx  # 方法内导入：非 live 测试套件不依赖真实网络即可导入本模块

        url = f"{self.base_url}/chat/completions"
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        body = {"model": self.model, "messages": messages, "temperature": temperature, **opts}
        last = None
        for _ in range(3):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as c:
                    r = await c.post(url, headers=headers, json=body)
                    r.raise_for_status()
                    return r.json()["choices"][0]["message"]["content"]
            except Exception as exc:  # noqa: BLE001
                last = exc
                await asyncio.sleep(1.0)
        raise RuntimeError(f"LLM chat 失败: {last}")

    async def translate(self, text: str, target_lang: str = "zh") -> str:
        """把文本翻译成中文（target_lang 预留，当前实现固定译为中文）。"""
        msg = [{"role": "user", "content": f"把下面文本翻译成中文，只返回译文：\n{text}"}]
        return await self.chat(msg)

    async def extract_json(self, prompt: str) -> dict:
        """让模型只返回 JSON，再用 _parse_json_loose 容错解析。"""
        msg = [{"role": "user", "content": prompt + "\n只返回 JSON。"}]
        return _parse_json_loose(await self.chat(msg))

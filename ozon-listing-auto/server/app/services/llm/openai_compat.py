"""OpenAICompatLLM：OpenAI 兼容 Chat Completions（Task 7 实现真实方法）。"""

class OpenAICompatLLM:
    name = "openai"
    def __init__(self, base_url: str, api_key: str, model: str, timeout: float = 30.0):
        self.base_url = base_url.rstrip("/"); self.api_key = api_key; self.model = model; self.timeout = timeout
    async def chat(self, messages: list[dict], **opts) -> str:
        raise NotImplementedError("OpenAICompatLLM 将在 Task 7 实现")
    async def translate(self, text: str, target_lang: str = "zh") -> str:
        raise NotImplementedError
    async def extract_json(self, prompt: str) -> dict:
        raise NotImplementedError

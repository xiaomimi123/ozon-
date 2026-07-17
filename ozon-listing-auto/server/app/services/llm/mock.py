"""MockLLM：确定性桩，供测试/开发（无 key、无网络、可复现）。"""

class MockLLM:
    name = "mock"
    async def chat(self, messages: list[dict], **opts) -> str:
        for m in reversed(messages):
            if m.get("role") == "user":
                return str(m.get("content", ""))
        return ""
    async def translate(self, text: str, target_lang: str = "zh") -> str:
        return text  # 恒等透传：测试通过输入字符串控制标题相似度
    async def extract_json(self, prompt: str) -> dict:
        return {}   # mock 不抽取；真实 LLM 由 OpenAICompatLLM 完成

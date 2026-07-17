"""按名返回 LLMProvider；默认 mock，openai 惰性 import 并从配置构造。"""
from app.services.llm.base import LLMProvider
from app.services.llm.mock import MockLLM

def get_llm(name: str = "mock") -> LLMProvider:
    if name == "mock":
        return MockLLM()
    if name == "openai":
        from app.services.llm.openai_compat import OpenAICompatLLM
        from app.core.config import settings
        return OpenAICompatLLM(settings.llm_base_url, settings.llm_api_key, settings.llm_model)
    raise ValueError(f"未知 LLM: {name}")

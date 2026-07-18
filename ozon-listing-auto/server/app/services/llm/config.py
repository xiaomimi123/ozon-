"""按 /settings/llm 配置构造 LLMProvider：openai 有 key 则真实, 否则 mock；配置空回退 env。"""
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.services.settings_store import get_category
from app.services.llm.factory import get_llm


async def get_configured_llm(session: AsyncSession):
    conf = await get_category(session, "llm")
    provider = conf.get("llm_provider") or settings.llm_provider
    if provider == "openai":
        base = conf.get("llm_base_url") or settings.llm_base_url
        key = conf.get("llm_api_key") or settings.llm_api_key
        model = conf.get("llm_model") or settings.llm_model
        if key:
            from app.services.llm.openai_compat import OpenAICompatLLM
            return OpenAICompatLLM(base, key, model)
    return get_llm("mock")

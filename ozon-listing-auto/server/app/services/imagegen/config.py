"""按 /settings/imagegen 配置构造 gen ImageProvider：openai_compat/http 真实, 否则 mock；无 key/无配回退 mock。"""
from app.services.settings_store import get_category
from app.services.imagegen.mock import MockImageProvider


async def get_configured_gen_provider(session, *, static_dir):
    conf = await get_category(session, "imagegen")
    provider = conf.get("provider", "mock")
    key = conf.get("img_api_key") or ""
    base = conf.get("img_base_url") or ""
    model = conf.get("img_model") or ""
    if provider == "openai_compat" and key and base:
        from app.services.imagegen.openai_compat import OpenAICompatImageProvider
        return OpenAICompatImageProvider(base, key, model, static_dir=static_dir)
    if provider == "http" and base and conf.get("img_request_template") and conf.get("img_response_path"):
        from app.services.imagegen.http import HttpImageProvider
        return HttpImageProvider(base, key, model, conf["img_request_template"], conf["img_response_path"],
                                 static_dir=static_dir)
    return MockImageProvider()

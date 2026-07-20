"""1688/货源配置读取：/settings/sources(Fernet 存)合并默认；JSON 串字段解析为 dict/list。"""
import json
from app.services.settings_store import get_category

DEFAULT_SOURCE_CONF = {
    "ali1688_image_search_url": "", "ali1688_keyword_search_url": "",
    "ali1688_method": "GET", "ali1688_extra_params": {}, "ali1688_extra_headers": {},
    "ali1688_offer_list_path": "data.offerList",
    "import_token": "", "import_1688_list_path": "",
}
_JSON_FIELDS = ("ali1688_extra_params", "ali1688_extra_headers")


async def get_source_conf(session) -> dict:
    raw = await get_category(session, "sources")
    conf = dict(DEFAULT_SOURCE_CONF)
    for k in ("ali1688_image_search_url", "ali1688_keyword_search_url", "ali1688_method", "ali1688_offer_list_path",
              "import_token", "import_1688_list_path"):
        if raw.get(k):
            conf[k] = raw[k]
    for k in _JSON_FIELDS:
        if raw.get(k):
            try:
                v = json.loads(raw[k])
                conf[k] = v if isinstance(v, (dict, list)) else DEFAULT_SOURCE_CONF[k]
            except (ValueError, TypeError):
                conf[k] = DEFAULT_SOURCE_CONF[k]
    return conf

"""1688/货源配置读取：/settings/sources(Fernet 存)合并默认；JSON 串字段解析为 dict/list。"""
import json
from app.services.settings_store import get_category

# 与 parser_import.DEFAULT_IMPORT_PATHS 的 key 对应, 生成 import_1688_{k}_path 配置键
_IMPORT_PATH_FIELDS = ("list", "offer_id", "title", "price", "image", "shop", "detail_url", "sales")
_IMPORT_PATH_KEYS = tuple(f"import_1688_{k}_path" for k in _IMPORT_PATH_FIELDS)

DEFAULT_SOURCE_CONF = {
    "ali1688_image_search_url": "", "ali1688_keyword_search_url": "",
    "ali1688_method": "GET", "ali1688_extra_params": {}, "ali1688_extra_headers": {},
    "ali1688_offer_list_path": "data.offerList",
    "import_token": "",
    **{k: "" for k in _IMPORT_PATH_KEYS},
}
_JSON_FIELDS = ("ali1688_extra_params", "ali1688_extra_headers")


async def get_source_conf(session) -> dict:
    raw = await get_category(session, "sources")
    conf = dict(DEFAULT_SOURCE_CONF)
    for k in ("ali1688_image_search_url", "ali1688_keyword_search_url", "ali1688_method", "ali1688_offer_list_path",
              "import_token", *_IMPORT_PATH_KEYS):
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

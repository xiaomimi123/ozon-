"""爬虫配置读取：合并 settings/crawler(Fernet 存)与默认值，数值解析。供 provider 构造与后续复用。"""
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.settings_store import get_category

DEFAULT_CRAWLER = {"cookie": "", "proxy": "", "timeout": 20.0,
                   "min_delay": 0.3, "max_delay": 1.0, "max_retries": 4}


async def get_crawler_conf(session: AsyncSession) -> dict:
    raw = await get_category(session, "crawler")   # {key: 解密值(str)}
    conf = dict(DEFAULT_CRAWLER)
    if raw.get("cookie"):
        conf["cookie"] = raw["cookie"]
    if raw.get("proxy"):
        conf["proxy"] = raw["proxy"]
    for k, cast in (("timeout", float), ("min_delay", float), ("max_delay", float), ("max_retries", int)):
        if raw.get(k) not in (None, ""):
            try:
                conf[k] = cast(float(raw[k])) if cast is int else cast(raw[k])
            except (ValueError, TypeError):
                pass
    return conf

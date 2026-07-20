"""1688 搜索接口响应 → 简单导入商品 dict（路径可配, 每字段点路径可覆盖）。
默认路径取自 parser_ali 的真实 Zhui-CN 字段(data.offerList/offerId/subject/priceInfo.price/imageUrl/company.name)。
参考其它结构: onebound items.item[](title/price/num_iid/pic_url/seller_nick); 官方 result.products[](productId/subject/price)。
真实响应结构以首跑存下的 ImportCapture.raw 为准, 改配置路径校准即可。"""
import re
from app.services.sources.parser_ali import _dig

DEFAULT_IMPORT_PATHS = {
    "list": "data.offerList", "offer_id": "offerId", "title": "subject",
    "price": "priceInfo.price", "image": "imageUrl", "shop": "company.name",
    "detail_url": "detailUrl", "sales": "monthSold",
}


def _price(v):
    if v is None:
        return None
    m = re.search(r"[\d.]+", str(v))
    return float(m.group()) if m else None


def _int(v):
    if v is None:
        return None
    m = re.search(r"\d+", str(v))
    return int(m.group()) if m else None


def parse_1688_search(payload: dict, paths: dict | None = None) -> list[dict]:
    p = {**DEFAULT_IMPORT_PATHS, **(paths or {})}
    out: list[dict] = []
    if not isinstance(payload, dict):
        return out
    offers = _dig(payload, p["list"])
    for it in offers if isinstance(offers, list) else []:
        if not isinstance(it, dict):
            continue
        offer_id = _dig(it, p["offer_id"])
        if offer_id is None:
            continue
        out.append({
            "offer_id": str(offer_id), "title": _dig(it, p["title"]),
            "price": _price(_dig(it, p["price"])), "image_url": _dig(it, p["image"]),
            "shop_name": _dig(it, p["shop"]), "detail_url": _dig(it, p["detail_url"]),
            "sales": _int(_dig(it, p["sales"])), "raw": it,
        })
    return out

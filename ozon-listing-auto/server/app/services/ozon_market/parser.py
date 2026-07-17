"""composer-api 响应解析：从 widgetStates 中容错抽取商品字段为 OzonProductDTO。"""
import json
import re
from app.services.ozon_market.base import OzonProductDTO


def _parse_price(price_field) -> float | None:
    if not price_field:
        return None
    raw = price_field.get("price") if isinstance(price_field, dict) else price_field
    if raw is None:
        return None
    digits = re.sub(r"[^\d]", "", str(raw))
    return float(digits) if digits else None


def parse_search_widgets(payload: dict) -> list[OzonProductDTO]:
    out: list[OzonProductDTO] = []
    states = payload.get("widgetStates", {})
    for key, value in states.items():
        if "searchResults" not in key:
            continue
        try:
            data = json.loads(value) if isinstance(value, str) else value
        except (json.JSONDecodeError, TypeError):
            continue
        for it in data.get("items", []):
            sku = it.get("sku")
            if sku is None:
                continue
            images = it.get("images", []) or []
            out.append(OzonProductDTO(
                sku=str(sku),
                title=it.get("title"),
                price=_parse_price(it.get("price")),
                main_image_url=images[0] if images else None,
                images=[str(i) for i in images],
                raw=it,
            ))
    return out

"""composer-api 响应解析：从 widgetStates 中容错抽取商品字段为 OzonProductDTO。

真实 Ozon composer-api 结构（浏览器实抓验证）：
- 商品挂在 widgetStates 里名字包含 "tileGrid" 或 "searchResults" 的 key 下（
  真实抓包见到的 key 形如 "tileGridDesktop-3669724-default-2"）。
- 该 key 对应的 value 是 JSON **字符串**，需 json.loads 后取 .items 列表。
- 每个 item：
  - item["sku"] 数字 sku。
  - item["action"]["link"] 是相对路径商品链接，需拼上 https://www.ozon.ru。
  - item["tileImage"]["items"][]["image"]["link"] 是图片 URL 列表。
  - item["mainState"] 是原子（atom）列表，按 "type" 分派：
    - "textDS": atom["textDS"]["text"]，其中 testInfo.automatizationId == "tile-name"
      的那条是商品标题（其余是库存/杂项文案，忽略）。
    - "priceV2": atom["priceV2"]["price"] 是 [{"text","textStyle"}] 列表，取
      textStyle == "PRICE" 的一条作为当前价格（去除非数字字符后转 float）。
    - "labelListV2": atom["labelListV2"]["items"] 里的 text 值扫描：第一个形如
      "4.9" 的 0~5 小数是评分，第一个去空格后为纯数字的文本是评价数。
- 对任何缺失字段均容错为 None/空，不抛异常。
"""
import json
import re
from app.services.ozon_market.base import OzonProductDTO

_OZON_HOST = "https://www.ozon.ru"


def _find_price_v2(main_state: list) -> dict | None:
    """在 mainState 原子列表中定位 priceV2 原子，返回其内层字典。"""
    for atom in main_state:
        if isinstance(atom, dict) and atom.get("type") == "priceV2":
            price_v2 = atom.get("priceV2")
            if isinstance(price_v2, dict):
                return price_v2
    return None


def _extract_price(price_v2: dict | None) -> float | None:
    """从 priceV2 原子中提取当前售价（textStyle == "PRICE" 的条目）。"""
    if not isinstance(price_v2, dict):
        return None
    for entry in price_v2.get("price") or []:
        if isinstance(entry, dict) and entry.get("textStyle") == "PRICE":
            digits = re.sub(r"[^\d]", "", str(entry.get("text") or ""))
            return float(digits) if digits else None
    return None


def _extract_title(main_state: list) -> str | None:
    """在 mainState 中找 automatizationId == "tile-name" 的 textDS 原子作为标题。"""
    for atom in main_state:
        if not isinstance(atom, dict) or atom.get("type") != "textDS":
            continue
        text_ds = atom.get("textDS") or {}
        test_info = text_ds.get("testInfo") or {}
        if test_info.get("automatizationId") == "tile-name":
            return text_ds.get("text")
    return None


def _extract_rating_reviews(main_state: list) -> tuple[float | None, int | None]:
    """扫描所有 labelListV2 原子的 text 项：首个 0~5 小数为评分，首个纯整数为评价数。"""
    rating: float | None = None
    reviews: int | None = None
    for atom in main_state:
        if not isinstance(atom, dict) or atom.get("type") != "labelListV2":
            continue
        items = (atom.get("labelListV2") or {}).get("items") or []
        for it in items:
            if not isinstance(it, dict) or it.get("type") != "text":
                continue
            text = (it.get("text") or {}).get("text")
            if not text:
                continue
            if rating is None and ("." in text or "," in text):
                try:
                    val = float(text.replace(",", "."))
                except ValueError:
                    val = None
                if val is not None and 0 <= val <= 5:
                    rating = val
                    continue
            if reviews is None:
                compact = text.replace(" ", "").replace("\xa0", "")
                if compact.isdigit():
                    reviews = int(compact)
    return rating, reviews


def _extract_images(item: dict) -> list[str]:
    """从 tileImage.items[].image.link 收集全部图片 URL。"""
    tile_image = item.get("tileImage") or {}
    result = []
    for entry in tile_image.get("items") or []:
        link = ((entry or {}).get("image") or {}).get("link")
        if link:
            result.append(str(link))
    return result


def _extract_product_url(item: dict) -> str | None:
    """从 action.link 拼出绝对商品 URL（真实响应中该字段是相对路径）。"""
    link = (item.get("action") or {}).get("link")
    if not link:
        return None
    link = str(link)
    return link if link.startswith("http") else _OZON_HOST + link


def parse_search_widgets(payload: dict) -> list[OzonProductDTO]:
    out: list[OzonProductDTO] = []
    states = payload.get("widgetStates") or {}
    for key, value in states.items():
        if "tileGrid" not in key and "searchResults" not in key:
            continue
        try:
            data = json.loads(value) if isinstance(value, str) else value
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(data, dict):
            continue
        for item in data.get("items") or []:
            if not isinstance(item, dict):
                continue
            sku = item.get("sku")
            if sku is None:
                continue
            main_state = item.get("mainState") or []
            rating, reviews_count = _extract_rating_reviews(main_state)
            images = _extract_images(item)
            out.append(OzonProductDTO(
                sku=str(sku),
                title=_extract_title(main_state),
                price=_extract_price(_find_price_v2(main_state)),
                rating=rating,
                reviews_count=reviews_count,
                main_image_url=images[0] if images else None,
                images=images,
                product_url=_extract_product_url(item),
                raw=item,
            ))
    return out

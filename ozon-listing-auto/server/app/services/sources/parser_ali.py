"""1688 图搜返回 → SupplyCandidateDTO 解析（字段参考 Zhui-CN；容错缺字段）。"""
import re
from app.services.sources.base import SupplyCandidateDTO


def _price(v) -> float | None:
    if v is None:
        return None
    m = re.search(r"[\d.]+", str(v))
    return float(m.group()) if m else None


def _rate(v) -> float | None:
    """百分比字符串（如 "45.45%"）→ 小数（0.4545）。"""
    if v is None:
        return None
    m = re.search(r"[\d.]+", str(v))
    return round(float(m.group()) / 100, 4) if m else None


def _dig(obj, path: str):
    cur = obj
    for part in path.split("."):
        if isinstance(cur, dict):
            cur = cur.get(part)
        elif isinstance(cur, list):
            try:
                cur = cur[int(part)]
            except (ValueError, IndexError):
                return None
        else:
            return None
        if cur is None:
            return None
    return cur


def parse_offers(payload: dict, offer_list_path: str = "data.offerList") -> list[SupplyCandidateDTO]:
    """解析 1688 图搜/关键词搜索返回 JSON，offer 列表所在路径可配置，容错缺字段。"""
    out: list[SupplyCandidateDTO] = []
    if not isinstance(payload, dict):
        return out
    offers = _dig(payload, offer_list_path)
    for it in offers if isinstance(offers, list) else []:
        if not isinstance(it, dict):
            continue
        offer_id = it.get("offerId")
        if offer_id is None:
            continue
        comp = it.get("company", {}) or {}
        info = {}
        if comp:
            info = {"credit_level": comp.get("creditLevel"), "reg_capital": comp.get("regCapital"),
                    "province": comp.get("province"), "city": comp.get("city"),
                    "repurchase_rate": _rate(comp.get("repurchaseRate")),
                    "position_labels": comp.get("positionLabels", []), "scores": comp.get("scores", {})}
        out.append(SupplyCandidateDTO(
            platform="ali1688", offer_id=str(offer_id), title=it.get("subject"),
            price=_price((it.get("priceInfo") or {}).get("price")), currency="CNY",
            quantity_begin=it.get("quantityBegin"), image_url=it.get("imageUrl"),
            detail_url=it.get("detailUrl"), supplier_name=comp.get("name"),
            supplier_info={k: v for k, v in info.items() if v is not None}, raw=it,
        ))
    return out


def parse_image_search(payload: dict) -> list[SupplyCandidateDTO]:
    """解析 1688 拍立淘图搜（或关键词搜索）返回 JSON，容错缺字段（向后兼容，固定默认路径）。"""
    return parse_offers(payload, "data.offerList")

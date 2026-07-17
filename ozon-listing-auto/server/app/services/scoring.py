"""五维评分引擎（图45/标题20/属性15/价格5/供应商15）+ tier。mock 下确定性。"""
import difflib
import math
from dataclasses import dataclass, field

DEFAULT_WEIGHTS = {"image": 0.45, "title": 0.20, "attr": 0.15, "price": 0.05, "supplier": 0.15}
DEFAULT_TIER = {"tier_auto": 85.0, "tier_review": 70.0}
_CREDIT = {"AAA": 30.0, "AA": 24.0, "A": 18.0}

@dataclass
class ScoreResult:
    image: float; title: float; attr: float; price: float; supplier: float
    total: float; tier: str; detail: dict = field(default_factory=dict)

def _cosine(a, b) -> float:
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)); nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0

def _image_score(ozon_emb, cand_emb) -> float:
    return max(0.0, _cosine(ozon_emb, cand_emb)) * 100.0

def _title_score(translated: str, cand_title: str) -> float:
    if not translated or not cand_title:
        return 0.0
    return difflib.SequenceMatcher(None, translated, cand_title).ratio() * 100.0

def _attr_score(ozon_attrs: dict, extracted: dict) -> float:
    if not ozon_attrs:
        return 0.0
    if not extracted:
        return 0.0
    hit = 0
    for k, v in ozon_attrs.items():
        if k in extracted and str(extracted[k]).lower() == str(v).lower():
            hit += 1
    return hit / len(ozon_attrs) * 100.0

def _price_score(price, price_range=None) -> float:
    if price is None or price <= 0:
        return 0.0
    if price_range:
        lo, hi = price_range
        return 100.0 if lo <= price <= hi else 40.0
    return 80.0

def _supplier_score(info: dict) -> float:
    if not info:
        return 0.0
    s = 0.0
    rr = info.get("repurchase_rate")
    if rr is not None:
        s += min(max(float(rr), 0.0), 1.0) * 40.0
    s += _CREDIT.get(info.get("credit_level"), 10.0 if info.get("credit_level") else 0.0)
    scores = info.get("scores") or {}
    vals = [v for v in scores.values() if isinstance(v, (int, float))]
    if vals:
        s += (sum(vals) / len(vals)) / 5.0 * 30.0
    return min(s, 100.0)

def compute_tier(total: float, tier_auto: float, tier_review: float) -> str:
    if total >= tier_auto:
        return "auto"
    if total >= tier_review:
        return "review"
    return "rejected"

async def score_candidate(ozon_embedding, ozon_title, ozon_attributes, candidate, *,
                          llm, weights=None, thresholds=None, price_range=None) -> ScoreResult:
    w = {**DEFAULT_WEIGHTS, **(weights or {})}
    th = {**DEFAULT_TIER, **(thresholds or {})}
    image = _image_score(ozon_embedding, getattr(candidate, "embedding", None))
    translated = await llm.translate(ozon_title or "", "zh")
    title = _title_score(translated, getattr(candidate, "title", "") or "")
    extracted = await llm.extract_json(f"从商品标题抽取结构化属性(JSON): {getattr(candidate, 'title', '')}")
    attr = _attr_score(ozon_attributes or {}, extracted)
    price = _price_score(getattr(candidate, "price", None), price_range)
    supplier = _supplier_score(getattr(candidate, "supplier_info", None) or {})
    total = (w["image"] * image + w["title"] * title + w["attr"] * attr
             + w["price"] * price + w["supplier"] * supplier)
    tier = compute_tier(total, th["tier_auto"], th["tier_review"])
    detail = {"image": image, "title": title, "attr": attr, "price": price, "supplier": supplier,
              "translated_title": translated}
    return ScoreResult(image=image, title=title, attr=attr, price=price, supplier=supplier,
                       total=total, tier=tier, detail=detail)

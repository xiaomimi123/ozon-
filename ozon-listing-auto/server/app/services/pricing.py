"""定价引擎：内置毛利率反推 + simpleeval 自定义公式 + 最低价保护(§5.8)。"""
from dataclasses import dataclass, field

DEFAULT_PRICING = {"mode": "builtin", "commission_rate": 0.15, "fulfillment_rate": 0.10,
                   "fx": 13.0, "target_margin": 0.20, "logistics": 5.0, "min_price": 0.0,
                   "strike_coeff": 1.3, "formula": ""}
_ALLOWED = ("cost", "logistics", "commission_rate", "fulfillment_rate", "fx", "weight", "target_margin", "min_price")

@dataclass
class PriceResult:
    price: float
    cost: float
    margin: float
    strike: float | None
    blocked: bool
    detail: dict = field(default_factory=dict)

def _builtin(cost_cny: float, p: dict) -> tuple[float, float, float, bool]:
    logistics = float(p.get("logistics", 5.0))
    landed = cost_cny + logistics
    denom = 1.0 - float(p.get("target_margin", 0.2)) - float(p.get("commission_rate", 0.15)) - float(p.get("fulfillment_rate", 0.10))
    if denom <= 0:
        return 0.0, landed, 0.0, True
    price = landed / denom * float(p.get("fx", 13.0))
    return price, landed, float(p.get("target_margin", 0.2)), False

def _formula(cost_cny: float, weight, p: dict) -> tuple[float, bool]:
    try:
        from simpleeval import SimpleEval
        se = SimpleEval(names={
            "cost": cost_cny, "logistics": float(p.get("logistics", 5.0)),
            "commission_rate": float(p.get("commission_rate", 0.15)),
            "fulfillment_rate": float(p.get("fulfillment_rate", 0.10)),
            "fx": float(p.get("fx", 13.0)), "weight": float(weight) if weight else 0.0,
            "target_margin": float(p.get("target_margin", 0.2)), "min_price": float(p.get("min_price", 0.0))})
        se.functions = {}   # 禁函数(含 __import__ 等)
        val = float(se.eval(str(p.get("formula", "")) or "0"))
        return val, False
    except Exception:       # noqa: BLE001  求值失败/被禁 → 安全兜底
        return 0.0, True

def price_candidate(cost_cny: float, weight, params: dict | None = None) -> PriceResult:
    p = {**DEFAULT_PRICING, **(params or {})}
    landed = cost_cny + float(p.get("logistics", 5.0))
    if p.get("mode") == "formula":
        price, blocked = _formula(cost_cny, weight, p)
        margin = float(p.get("target_margin", 0.2))
    else:
        price, landed, margin, blocked = _builtin(cost_cny, p)
    min_price = float(p.get("min_price", 0.0))
    if not blocked and (price <= 0 or price < min_price):
        blocked = True
    strike = round(price * float(p.get("strike_coeff", 1.3)), 2) if price > 0 else None
    return PriceResult(price=round(price, 2), cost=round(landed, 2), margin=margin, strike=strike,
                       blocked=blocked, detail={"denom_mode": p.get("mode"), "fx": p.get("fx")})

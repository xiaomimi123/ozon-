import pytest
from app.services.pricing import price_candidate, DEFAULT_PRICING

def test_builtin_pricing():
    # cost=15, logistics=5 → 到手 20; denom=1-0.2-0.15-0.1=0.55; 售价=20/0.55*13=472.727...
    r = price_candidate(15.0, None, DEFAULT_PRICING)
    assert r.cost == pytest.approx(20.0)
    assert r.price == pytest.approx(20.0 / 0.55 * 13.0, abs=1e-2)
    assert r.margin == pytest.approx(0.20)
    assert r.strike == pytest.approx(r.price * 1.3, abs=1e-2)
    assert r.blocked is False

def test_min_price_protection():
    params = {**DEFAULT_PRICING, "min_price": 1e9}   # 极高最低价 → 拦截
    r = price_candidate(15.0, None, params)
    assert r.blocked is True

def test_denom_guard():
    params = {**DEFAULT_PRICING, "target_margin": 0.9, "commission_rate": 0.2}  # denom<0
    r = price_candidate(15.0, None, params)
    assert r.blocked is True

def test_formula_mode():
    params = {**DEFAULT_PRICING, "mode": "formula", "formula": "cost * fx * 2"}
    r = price_candidate(10.0, None, params)
    assert r.price == pytest.approx(10.0 * 13.0 * 2)
    assert r.blocked is False

def test_formula_safe_no_arbitrary_code():
    params = {**DEFAULT_PRICING, "mode": "formula", "formula": "__import__('os').system('echo x')"}
    r = price_candidate(10.0, None, params)
    assert r.blocked is True   # 求值失败/被禁 → 安全兜底(blocked)

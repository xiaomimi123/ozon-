import pytest
from app.services.scoring import (score_candidate, compute_tier, _supplier_score,
                                  _image_score, DEFAULT_WEIGHTS)
from app.services.llm.mock import MockLLM
from app.services.sources.base import SupplyCandidateDTO

def test_compute_tier():
    assert compute_tier(90, 85, 70) == "auto"
    assert compute_tier(75, 85, 70) == "review"
    assert compute_tier(50, 85, 70) == "rejected"

def test_image_score_identical_vectors():
    v = [0.1, 0.2, 0.3]
    assert _image_score(v, v) == pytest.approx(100.0, abs=1e-3)
    assert _image_score(v, None) == 0.0

def test_supplier_score():
    s = _supplier_score({"repurchase_rate": 1.0, "credit_level": "AAA", "scores": {"综合": 5.0}})
    assert s == pytest.approx(100.0, abs=1e-6)     # 40 + 30 + 30
    assert _supplier_score({}) == 0.0

@pytest.mark.asyncio
async def test_score_candidate_deterministic():
    # ozon 与候选同图向量、同标题 → 图分/标题分高; mock 抽属性为空 → attr 0
    emb = [0.5] * 512
    cand = SupplyCandidate_stub(embedding=emb, title="无线耳机", price=12.5,
                                supplier_info={"repurchase_rate": 0.5, "credit_level": "AA", "scores": {"综合": 4.0}})
    r = await score_candidate(emb, "无线耳机", {"color": "black"}, cand, llm=MockLLM())
    assert r.image == pytest.approx(100.0, abs=1e-3)
    assert r.title == pytest.approx(100.0, abs=1e-3)     # 恒等翻译 + 同标题
    assert r.attr == 0.0                                  # MockLLM 抽取为空
    assert r.price > 0                                     # 有效正价
    assert 0 < r.supplier < 100
    assert 0 <= r.total <= 100
    assert r.tier in {"auto", "review", "rejected"}

# 简易 stub(避免依赖 DB): 用一个带所需属性的对象
class SupplyCandidate_stub:
    def __init__(self, embedding, title, price, supplier_info):
        self.embedding = embedding; self.title = title; self.price = price
        self.supplier_info = supplier_info

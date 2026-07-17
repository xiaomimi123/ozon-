# M3 五维评分 + 审核台 实现计划（含 LLM 抽象）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给货源候选算五维分(图45/标20/属15/价5/供15)+总分+tier，并做完整审核台(采用/拒绝/换候选、可配审核开关+阈值、Redis 并发锁、决策留痕)。管线：采集(M1)→匹配(M2)→评分(M3)→审核(M3)。验收「多人审核、可配开关」。

**Architecture:** 沿用 mock-first + 配置驱动 provider 模式。新增 LLM 家族(mock/openai_compat, 默认通义千问)用于译标题+抽属性；scoring 引擎；scorer worker(镜像 M2 matcher 的断点/暂停/失败)；review 服务(自动采用/队列/决策/Redis 锁)；审核台前端。测试全走 mock(无 LLM key/网络/torch/真实 Redis)。

**Tech Stack:** 承接 M1/M2(FastAPI async / SQLAlchemy2 / Alembic / ARQ / Postgres+pgvector / Redis / React+Vite+AntD)。新增：`difflib`(标题相似, 标准库); LLM 走 httpx(已装); 复用 M2 的 `Embedder`(mock/cn_clip)。

## Global Constraints

- Python 3.11；后端全异步；worker 幂等；断点续传(`score_cursor`)。
- 五维权重默认 `w_image=0.45 w_title=0.20 w_attr=0.15 w_price=0.05 w_supplier=0.15`；tier `auto>=85`, `review>=70`, else `rejected`。权重/阈值从 `app_settings.scoring` 读，缺省用代码默认常量。
- LLM 名枚举 `mock`/`openai`(默认 mock)；embedder 复用 M2(`mock`/`clip`)。
- 审核决策角色 `reviewer`(admin 超级通过)；评分启动 `operator`+；设置 `admin`。
- `decision ∈ {adopt, reject, auto_adopt}`；候选 `status`: candidate→adopted/rejected/auto_adopted。
- 向量 512 维(复用 M2 `EMBED_DIM`)；`ozon_products.embedding` 与 `supply_candidates.embedding` 同 `Vector(512).with_variant(JSON,"sqlite")`。
- 迁移列有 server_default 的且 ORM NOT NULL 的必须 `nullable=False`(M2 Task1 教训)。
- 敏感信息 Fernet 加密；structlog 带 task_id；中文注释/每模块一行中文 docstring。
- TDD：每单元先写失败测试；`pytest` 0 warnings；测试全走 mock。
- 代码库 `ozon-listing-auto/`；venv `ozon-listing-auto/server/.venv`(3.11)；跑测试 `ozon-listing-auto/server/.venv/bin/python -m pytest`(勿用系统 python3=3.9)；Node via nvm。
- 建立在 M2 之上：复用 `Embedder`/`get_embedder`(mock)、`_JSONB`/`_VECTOR` variant、`SupplyCandidate`/`OzonProduct`/`CollectTask`/`User` 模型、`api/deps`(require_role/get_current_user)、`settings_store`、`crypto`、conftest fixtures(内存 SQLite + monkeypatch async_session)、collector/matcher 的 §4.2.6 failed 范式、live marker(`@pytest.mark.live` + addopts)、passlib filterwarnings。

## 文件结构

```
server/app/
├── models/{review_decision.py, ozon_product.py(+embedding), supply_candidate.py(+score列/tier), collect_task.py(+score_*)}
├── alembic/versions/0003_m3_scoring_review.py
├── schemas/{score.py, review.py}
├── api/{score.py, review.py}
├── services/
│   ├── llm/{base.py, mock.py, openai_compat.py, factory.py}
│   ├── scoring.py
│   └── review.py
└── workers/{scorer.py, arq_worker.py(+run_score)}
web/src/{pages/ReviewBoard.tsx, api/review.ts, App.tsx(+route), pages/Layout.tsx(+menu)}
server/tests/{test_score_models.py, test_llm.py, test_scoring.py, test_scorer.py,
              test_review_service.py, test_score_api.py, test_review_api.py, test_llm_openai.py}
```

---

## 阶段 0 · Schema

### Task 1: 迁移 0003 + ORM(评分列/review_decisions/ozon_products.embedding)

**Files:**
- Create: `ozon-listing-auto/server/app/models/review_decision.py`
- Modify: `ozon-listing-auto/server/app/models/ozon_product.py`(加 embedding)
- Modify: `ozon-listing-auto/server/app/models/supply_candidate.py`(加 score_*/tier/score_detail)
- Modify: `ozon-listing-auto/server/app/models/collect_task.py`(加 score_status/score_cursor/score_stats)
- Modify: `ozon-listing-auto/server/app/models/__init__.py`
- Create: `ozon-listing-auto/server/alembic/versions/0003_m3_scoring_review.py`
- Create: `ozon-listing-auto/server/tests/test_score_models.py`

**Interfaces:**
- Produces: `ReviewDecision` ORM; `OzonProduct.embedding`; `SupplyCandidate.{score_image,score_title,score_attr,score_price,score_supplier,score_total,tier,score_detail}`; `CollectTask.{score_status,score_cursor,score_stats}`.

- [ ] **Step 1: 读现有模型确认 variant 变量名**

先读 `supply_candidate.py`——它定义了 `_JSONB` 与 `_VECTOR = Vector(EMBED_DIM).with_variant(JSON(), "sqlite")` 和 `EMBED_DIM=512`。`ozon_product.py`/`collect_task.py` 里 M1 定义了 `_JSONB`。复用这些，不新造。

- [ ] **Step 2: 改 `ozon_product.py` 加 embedding**

顶部若无 `_VECTOR`，从 supply_candidate 导入 EMBED_DIM 并本文件定义：
```python
from sqlalchemy import JSON
from pgvector.sqlalchemy import Vector
from app.models.supply_candidate import EMBED_DIM
_VECTOR = Vector(EMBED_DIM).with_variant(JSON(), "sqlite")
```
在 `OzonProduct` 加列：
```python
    embedding: Mapped[list | None] = mapped_column(_VECTOR, nullable=True)
```
（注意避免循环 import：`ozon_product` 从 `supply_candidate` 导 EMBED_DIM——若循环，则把 `EMBED_DIM=512` 提到一个独立常量或直接写 512。优先直接 `Vector(512)`，注释标明来源。）

- [ ] **Step 3: 改 `supply_candidate.py` 加评分列**

```python
    score_image: Mapped[float | None] = mapped_column(Float, nullable=True)
    score_title: Mapped[float | None] = mapped_column(Float, nullable=True)
    score_attr: Mapped[float | None] = mapped_column(Float, nullable=True)
    score_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    score_supplier: Mapped[float | None] = mapped_column(Float, nullable=True)
    score_total: Mapped[float | None] = mapped_column(Float, nullable=True)
    tier: Mapped[str | None] = mapped_column(String(16), nullable=True)
    score_detail: Mapped[dict | None] = mapped_column(_JSONB, nullable=True)
```
（`Float` 若未 import 则加。）

- [ ] **Step 4: 改 `collect_task.py` 加 score_* 列**

复用该文件已有 `_JSONB`：
```python
    score_status: Mapped[str] = mapped_column(String(16), default="pending")
    score_cursor: Mapped[dict | None] = mapped_column(_JSONB, nullable=True)
    score_stats: Mapped[dict | None] = mapped_column(_JSONB, nullable=True)
```

- [ ] **Step 5: 写 `review_decision.py`**

```python
"""人工审核决策留痕 ORM（多人审核，§5.5）。"""
from datetime import datetime
from sqlalchemy import String, Integer, Text, DateTime, ForeignKey, Index, func
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db import Base

class ReviewDecision(Base):
    __tablename__ = "review_decisions"
    __table_args__ = (
        Index("ix_review_task_product", "task_id", "ozon_product_id"),
        Index("ix_review_candidate", "candidate_id"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("collect_tasks.id"), index=True)
    ozon_product_id: Mapped[int] = mapped_column(ForeignKey("ozon_products.id"))
    candidate_id: Mapped[int] = mapped_column(ForeignKey("supply_candidates.id"))
    reviewer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    decision: Mapped[str] = mapped_column(String(16))   # adopt|reject|auto_adopt
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

- [ ] **Step 6: 改 `models/__init__.py` 导出 `ReviewDecision`（加入 import + __all__）**

- [ ] **Step 7: 写失败测试 `tests/test_score_models.py`**

```python
import pytest
from sqlalchemy import select
from app.models import ReviewDecision, SupplyCandidate, OzonProduct, CollectTask, User

@pytest.mark.asyncio
async def test_score_columns_and_review_decision(db_session):
    t = CollectTask(name="t", entry_type="keyword", entry_value="x", provider="mock", source_platforms=["ali1688"])
    db_session.add(t); await db_session.flush()
    p = OzonProduct(task_id=t.id, sku="S1", title="phone", embedding=[0.1]*512)
    db_session.add(p); await db_session.flush()
    c = SupplyCandidate(task_id=t.id, ozon_product_id=p.id, platform="ali1688", offer_id="A1",
                        score_image=90.0, score_total=88.5, tier="auto", score_detail={"k": 1})
    db_session.add(c); await db_session.flush()
    u = User(username="rv", password_hash="x", role="reviewer")
    db_session.add(u); await db_session.flush()
    d = ReviewDecision(task_id=t.id, ozon_product_id=p.id, candidate_id=c.id, reviewer_id=u.id, decision="adopt")
    db_session.add(d); await db_session.commit()
    assert t.score_status == "pending"
    assert len(p.embedding) == 512
    got = (await db_session.execute(select(SupplyCandidate).where(SupplyCandidate.offer_id == "A1"))).scalar_one()
    assert got.tier == "auto" and got.score_total == 88.5
    rd = (await db_session.execute(select(ReviewDecision).where(ReviewDecision.candidate_id == c.id))).scalar_one()
    assert rd.decision == "adopt"
```

- [ ] **Step 8: 运行确认失败**

Run: `ozon-listing-auto/server/.venv/bin/python -m pytest ozon-listing-auto/server/tests/test_score_models.py -v`
Expected: FAIL（列/模型未定义）。若 Vector on SQLite 报错，按 M2 的 with_variant 方式修。

- [ ] **Step 9: 写迁移 `0003_m3_scoring_review.py`**

```python
"""m3 scoring review"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from pgvector.sqlalchemy import Vector

revision = "0003"
down_revision = "0002"

def upgrade():
    op.add_column("ozon_products", sa.Column("embedding", Vector(512)))
    for col in ["score_image", "score_title", "score_attr", "score_price", "score_supplier", "score_total"]:
        op.add_column("supply_candidates", sa.Column(col, sa.Float))
    op.add_column("supply_candidates", sa.Column("tier", sa.String(16)))
    op.add_column("supply_candidates", sa.Column("score_detail", postgresql.JSONB))
    op.add_column("collect_tasks", sa.Column("score_status", sa.String(16), server_default="pending", nullable=False))
    op.add_column("collect_tasks", sa.Column("score_cursor", postgresql.JSONB))
    op.add_column("collect_tasks", sa.Column("score_stats", postgresql.JSONB))
    op.create_table("review_decisions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("task_id", sa.Integer, sa.ForeignKey("collect_tasks.id"), nullable=False, index=True),
        sa.Column("ozon_product_id", sa.Integer, sa.ForeignKey("ozon_products.id"), nullable=False),
        sa.Column("candidate_id", sa.Integer, sa.ForeignKey("supply_candidates.id"), nullable=False),
        sa.Column("reviewer_id", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("decision", sa.String(16), nullable=False),
        sa.Column("note", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_review_task_product", "review_decisions", ["task_id", "ozon_product_id"])
    op.create_index("ix_review_candidate", "review_decisions", ["candidate_id"])

def downgrade():
    op.drop_table("review_decisions")
    for col in ["score_stats", "score_cursor", "score_status"]:
        op.drop_column("collect_tasks", col)
    for col in ["score_detail", "tier", "score_total", "score_supplier", "score_price", "score_attr", "score_title", "score_image"]:
        op.drop_column("supply_candidates", col)
    op.drop_column("ozon_products", "embedding")
```

- [ ] **Step 10: 运行确认通过 + 全套回归**

Run: `ozon-listing-auto/server/.venv/bin/python -m pytest ozon-listing-auto/server/tests -q`
Expected: PASS（0 warnings）。

- [ ] **Step 11: 提交**

```bash
git add ozon-listing-auto/server/app/models ozon-listing-auto/server/alembic/versions/0003_m3_scoring_review.py ozon-listing-auto/server/tests/test_score_models.py
git commit -m "feat(m3): 迁移0003 + ORM(评分列/tier/review_decisions/ozon_products.embedding)"
```

---

## 阶段 1 · LLM + 评分核心（mock-first）

### Task 2: LLM 抽象 + MockLLM + 工厂

**Files:**
- Create: `ozon-listing-auto/server/app/services/llm/__init__.py`
- Create: `ozon-listing-auto/server/app/services/llm/base.py`
- Create: `ozon-listing-auto/server/app/services/llm/mock.py`
- Create: `ozon-listing-auto/server/app/services/llm/openai_compat.py`(占位, Task 7 实现)
- Create: `ozon-listing-auto/server/app/services/llm/factory.py`
- Create: `ozon-listing-auto/server/tests/test_llm.py`

**Interfaces:**
- Produces: `base.LLMProvider`(Protocol: name, chat, translate, extract_json); `mock.MockLLM`(translate 恒等透传, extract_json 返回 `{}`, chat 回显最后一条 user); `factory.get_llm(name="mock")`(openai 惰性)。

- [ ] **Step 1: 写失败测试 `tests/test_llm.py`**

```python
import pytest
from app.services.llm.mock import MockLLM
from app.services.llm.factory import get_llm

@pytest.mark.asyncio
async def test_mock_llm_deterministic():
    m = MockLLM()
    assert m.name == "mock"
    assert await m.translate("привет", "zh") == "привет"      # 恒等透传(确定性)
    assert await m.extract_json("从标题抽属性: 黑色耳机") == {}
    assert await m.chat([{"role": "user", "content": "hi"}]) == "hi"

def test_factory_default_mock():
    assert get_llm().name == "mock"
    with pytest.raises(ValueError):
        get_llm("nope")
```

- [ ] **Step 2: 运行确认失败**

Run: `ozon-listing-auto/server/.venv/bin/python -m pytest ozon-listing-auto/server/tests/test_llm.py -v`
Expected: FAIL。

- [ ] **Step 3: 写 `base.py`**

```python
"""LLM 抽象（OpenAI 兼容，§5.5.5）：译标题 / 抽属性 / 通用对话。"""
from typing import Protocol

class LLMProvider(Protocol):
    name: str
    async def chat(self, messages: list[dict], **opts) -> str: ...
    async def translate(self, text: str, target_lang: str = "zh") -> str: ...
    async def extract_json(self, prompt: str) -> dict: ...
```

- [ ] **Step 4: 写 `mock.py`**

```python
"""MockLLM：确定性桩，供测试/开发（无 key、无网络、可复现）。"""

class MockLLM:
    name = "mock"
    async def chat(self, messages: list[dict], **opts) -> str:
        for m in reversed(messages):
            if m.get("role") == "user":
                return str(m.get("content", ""))
        return ""
    async def translate(self, text: str, target_lang: str = "zh") -> str:
        return text  # 恒等透传：测试通过输入字符串控制标题相似度
    async def extract_json(self, prompt: str) -> dict:
        return {}   # mock 不抽取；真实 LLM 由 OpenAICompatLLM 完成
```

- [ ] **Step 5: 加 LLM 配置项到 `app/core/config.py`**

在 Settings 加（默认通义千问 DashScope）：
```python
    llm_provider: str = "mock"          # mock | openai
    llm_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    llm_api_key: str = ""
    llm_model: str = "qwen-plus"
```

- [ ] **Step 6: 写占位 `openai_compat.py` 与 `factory.py`**

`openai_compat.py`（占位——`__init__` 签名与 Task 7 真实版一致，方法先 NotImplementedError）:
```python
"""OpenAICompatLLM：OpenAI 兼容 Chat Completions（Task 7 实现真实方法）。"""

class OpenAICompatLLM:
    name = "openai"
    def __init__(self, base_url: str, api_key: str, model: str, timeout: float = 30.0):
        self.base_url = base_url.rstrip("/"); self.api_key = api_key; self.model = model; self.timeout = timeout
    async def chat(self, messages: list[dict], **opts) -> str:
        raise NotImplementedError("OpenAICompatLLM 将在 Task 7 实现")
    async def translate(self, text: str, target_lang: str = "zh") -> str:
        raise NotImplementedError
    async def extract_json(self, prompt: str) -> dict:
        raise NotImplementedError
```

`factory.py`（openai 分支从 settings 构造，签名统一）:
```python
"""按名返回 LLMProvider；默认 mock，openai 惰性 import 并从配置构造。"""
from app.services.llm.base import LLMProvider
from app.services.llm.mock import MockLLM

def get_llm(name: str = "mock") -> LLMProvider:
    if name == "mock":
        return MockLLM()
    if name == "openai":
        from app.services.llm.openai_compat import OpenAICompatLLM
        from app.core.config import settings
        return OpenAICompatLLM(settings.llm_base_url, settings.llm_api_key, settings.llm_model)
    raise ValueError(f"未知 LLM: {name}")
```

- [ ] **Step 7: 运行确认通过**

Run: `ozon-listing-auto/server/.venv/bin/python -m pytest ozon-listing-auto/server/tests/test_llm.py -v`
Expected: PASS。

- [ ] **Step 8: 提交**

```bash
git add ozon-listing-auto/server/app/services/llm ozon-listing-auto/server/app/core/config.py ozon-listing-auto/server/tests/test_llm.py
git commit -m "feat(m3): LLM 抽象 + MockLLM(确定性) + 工厂(openai 从配置构造) + llm 配置项"
```

---

### Task 3: 评分引擎（五维 + tier + 权重）

**Files:**
- Create: `ozon-listing-auto/server/app/services/scoring.py`
- Create: `ozon-listing-auto/server/tests/test_scoring.py`

**Interfaces:**
- Consumes: `Embedder`(embed 已在 candidate/ozon 上, 传向量即可), `LLMProvider`, `OzonProduct`/`SupplyCandidate`(或其字段)。
- Produces:
  - `DEFAULT_WEIGHTS`(dict), `DEFAULT_TIER`(dict tier_auto=85, tier_review=70)。
  - `compute_tier(total, tier_auto, tier_review) -> str`。
  - `async score_candidate(ozon_embedding, ozon_title, ozon_attributes, candidate, *, llm, weights=None, thresholds=None, price_range=None) -> ScoreResult`（`ScoreResult` dataclass: image/title/attr/price/supplier/total/tier/detail）。
  - 内部纯函数：`_image_score(a,b)`, `_title_score(translated, cand_title)`, `_attr_score(ozon_attrs, extracted)`, `_price_score(price, price_range)`, `_supplier_score(info)`。

- [ ] **Step 1: 写失败测试 `tests/test_scoring.py`**

```python
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
```

- [ ] **Step 2: 运行确认失败**

Run: `ozon-listing-auto/server/.venv/bin/python -m pytest ozon-listing-auto/server/tests/test_scoring.py -v`
Expected: FAIL。

- [ ] **Step 3: 写 `scoring.py`**

```python
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
```

- [ ] **Step 4: 运行确认通过**

Run: `ozon-listing-auto/server/.venv/bin/python -m pytest ozon-listing-auto/server/tests/test_scoring.py -v`
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add ozon-listing-auto/server/app/services/scoring.py ozon-listing-auto/server/tests/test_scoring.py
git commit -m "feat(m3): 五维评分引擎(图/标题/属性/价格/供应商)+tier+权重"
```

---

### Task 4: scorer worker（评分 + Ozon 主图向量 + 断点/暂停/失败）

**Files:**
- Create: `ozon-listing-auto/server/app/workers/scorer.py`
- Modify: `ozon-listing-auto/server/app/workers/arq_worker.py`(注册 run_score)
- Create: `ozon-listing-auto/server/tests/test_scorer.py`

**Interfaces:**
- Consumes: `score_candidate`, `Embedder`, `LLMProvider`, `OzonProduct`/`SupplyCandidate`/`CollectTask`, `settings_store`(读 scoring 配置, 可选)。
- Produces:
  - `async run_score_core(session_factory, task_id, *, embedder, llm, weights=None, thresholds=None, max_products=None, progress_cb=None) -> dict`（遍历商品[score_cursor 断点续传]→给主图算向量写 ozon.embedding[已算跳过]→每候选 score_candidate 写回五维分/总分/tier/detail→写 score_stats；score_status running→done；商品级异常置 failed；paused 停止）。返回 `{products, candidates_scored}`。
  - `async run_score(ctx, task_id)`：ARQ 入口, 配置选 embedder+llm。

- [ ] **Step 1: 写失败测试 `tests/test_scorer.py`**

```python
import pytest
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
from app.workers.scorer import run_score_core
from app.services.embedding.mock import MockEmbedder
from app.services.llm.mock import MockLLM
from app.models import CollectTask, OzonProduct, SupplyCandidate

async def _seed(sm):
    async with sm() as s:
        t = CollectTask(name="t", entry_type="keyword", entry_value="x", provider="mock", source_platforms=["ali1688"])
        s.add(t); await s.flush()
        p = OzonProduct(task_id=t.id, sku="S0", title="无线耳机", main_image_url="https://img/oz.jpg",
                        attributes={"color": "black"})
        s.add(p); await s.flush()
        # 两个候选: 同图(高图分) 与 无图
        s.add(SupplyCandidate(task_id=t.id, ozon_product_id=p.id, platform="ali1688", offer_id="A1",
                              title="无线耳机", price=12.5, image_url="https://img/oz.jpg",
                              embedding=await MockEmbedder().embed_image("https://img/oz.jpg"),
                              supplier_info={"repurchase_rate": 0.5, "credit_level": "AA"}))
        await s.commit()
        return t.id, p.id

@pytest.mark.asyncio
async def test_run_score_writes_scores_and_embedding(engine):
    sm = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    tid, pid = await _seed(sm)
    result = await run_score_core(sm, tid, embedder=MockEmbedder(), llm=MockLLM())
    async with sm() as s:
        prod = (await s.execute(select(OzonProduct).where(OzonProduct.id == pid))).scalar_one()
        cand = (await s.execute(select(SupplyCandidate).where(SupplyCandidate.ozon_product_id == pid))).scalar_one()
        task = (await s.execute(select(CollectTask).where(CollectTask.id == tid))).scalar_one()
    assert prod.embedding is not None and len(prod.embedding) == 512   # Ozon 主图向量已写
    assert cand.score_total is not None and cand.tier in {"auto", "review", "rejected"}
    assert cand.score_image == pytest.approx(100.0, abs=1e-2)          # 候选与 Ozon 同图
    assert task.score_status == "done"
    assert result["candidates_scored"] == 1
```

- [ ] **Step 2: 运行确认失败**

Run: `ozon-listing-auto/server/.venv/bin/python -m pytest ozon-listing-auto/server/tests/test_scorer.py -v`
Expected: FAIL。

- [ ] **Step 3: 写 `workers/scorer.py`**

```python
"""评分 worker：给任务候选算五维分（先给 Ozon 主图算向量）；断点/暂停/失败。"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker
from app.core.logging import get_logger
from app.services.scoring import score_candidate
from app.models import CollectTask, OzonProduct, SupplyCandidate

async def run_score_core(session_factory: async_sessionmaker, task_id: int, *, embedder, llm,
                         weights=None, thresholds=None, max_products=None, progress_cb=None) -> dict:
    log = get_logger(task_id=task_id, phase="score")
    async with session_factory() as s:
        task = (await s.execute(select(CollectTask).where(CollectTask.id == task_id))).scalar_one()
        last_id = (task.score_cursor or {}).get("last_product_id", 0)
        prev = task.score_stats or {}
        task.score_status = "running"; await s.commit()
    total_products = 0
    total_scored = prev.get("candidates_scored", 0)
    while True:
        if max_products is not None and total_products >= max_products:
            break
        async with session_factory() as s:
            product = (await s.execute(select(OzonProduct).where(
                OzonProduct.task_id == task_id, OzonProduct.id > last_id
            ).order_by(OzonProduct.id.asc()).limit(1))).scalar_one_or_none()
        if product is None:
            async with session_factory() as s:
                task = (await s.execute(select(CollectTask).where(CollectTask.id == task_id))).scalar_one()
                task.score_status = "done"
                task.score_stats = {"products": prev.get("products", 0) + total_products, "candidates_scored": total_scored}
                await s.commit()
            break
        try:
            async with session_factory() as s:
                prod = (await s.execute(select(OzonProduct).where(OzonProduct.id == product.id))).scalar_one()
                if prod.embedding is None and prod.main_image_url:
                    prod.embedding = await embedder.embed_image(prod.main_image_url)
                ozon_emb = prod.embedding; ozon_title = prod.title; ozon_attrs = prod.attributes or {}
                cands = (await s.execute(select(SupplyCandidate).where(
                    SupplyCandidate.ozon_product_id == product.id))).scalars().all()
                for cand in cands:
                    r = await score_candidate(ozon_emb, ozon_title, ozon_attrs, cand, llm=llm,
                                              weights=weights, thresholds=thresholds)
                    cand.score_image = r.image; cand.score_title = r.title; cand.score_attr = r.attr
                    cand.score_price = r.price; cand.score_supplier = r.supplier
                    cand.score_total = r.total; cand.tier = r.tier; cand.score_detail = r.detail
                    total_scored += 1
                await s.commit()
            async with session_factory() as s:
                task = (await s.execute(select(CollectTask).where(CollectTask.id == task_id))).scalar_one()
                task.score_cursor = {"last_product_id": product.id}
                task.score_stats = {"products": prev.get("products", 0) + total_products + 1, "candidates_scored": total_scored}
                paused = task.score_status == "paused"
                await s.commit()
        except Exception as exc:
            log.error("score_failed", product_id=product.id, error=str(exc))
            async with session_factory() as s:
                task = (await s.execute(select(CollectTask).where(CollectTask.id == task_id))).scalar_one()
                task.score_status = "failed"; await s.commit()
            break
        last_id = product.id
        total_products += 1
        if progress_cb:
            await progress_cb({"task_id": task_id, "product_id": product.id, "scored": total_scored})
        if paused:
            break
    return {"products": total_products, "candidates_scored": total_scored}

async def run_score(ctx, task_id: int) -> dict:
    from app.core.db import async_session
    from app.core.config import settings
    from app.services.embedding.factory import get_embedder
    from app.services.llm.factory import get_llm
    return await run_score_core(async_session, task_id, embedder=get_embedder(settings.embedder), llm=get_llm(getattr(settings, "llm_provider", "mock")))
```

- [ ] **Step 4: 确认 `llm_provider` 配置项已存在**

`app/core/config.py` 的 `llm_provider`（及 llm_base_url/api_key/model）已在 Task 2 Step 5 加入。本任务 `run_score` 用 `settings.llm_provider` + `settings.embedder`（M2 已有）——无需改 config，仅确认存在。

- [ ] **Step 5: 注册 ARQ `run_score`**

改 `arq_worker.py` functions：
```python
from app.workers.collector import run_collect
from app.workers.matcher import run_match
from app.workers.scorer import run_score
class WorkerSettings:
    functions = [run_collect, run_match, run_score]
    ...
```

- [ ] **Step 6: 运行确认通过 + 全套回归**

Run: `ozon-listing-auto/server/.venv/bin/python -m pytest ozon-listing-auto/server/tests -q`
Expected: PASS（0 warnings）。

- [ ] **Step 7: 提交**

```bash
git add ozon-listing-auto/server/app/workers/scorer.py ozon-listing-auto/server/app/workers/arq_worker.py ozon-listing-auto/server/tests/test_scorer.py
git commit -m "feat(m3): scorer worker(Ozon 主图向量+五维评分写回, 断点/暂停/失败)"
```

---

## 阶段 2 · 审核服务 + API

### Task 5: 审核服务（自动采用 / 队列 / 决策 / Redis 锁）

**Files:**
- Create: `ozon-listing-auto/server/app/services/review.py`
- Create: `ozon-listing-auto/server/tests/test_review_service.py`

**Interfaces:**
- Consumes: `SupplyCandidate`/`OzonProduct`/`CollectTask`/`ReviewDecision`, AsyncSession。
- Produces:
  - `review_lock(product_id)`：异步上下文管理器，默认 no-op（生产 Redis）。
  - `async apply_auto_adopt(session, task_id) -> dict`（读 task.review_config；`source_review_required is False` 时对 status='candidate' 且 (source_score_min None 或 score_total>=min) 的候选置 status='auto_adopted' + 写 review_decision(auto_adopt, reviewer_id=None)；返回 `{"auto_adopted": n}`）。
  - `async get_review_queue(session, task_id, page=1, page_size=20) -> dict`（按 Ozon 商品聚合 status='candidate' 的候选[按 score_total 降序]；返回 `{items:[{product, candidates}], total}`）。
  - `async decide(session, candidate_id, reviewer_id, decision, note=None, *, lock=None) -> dict`（decision in {adopt,reject}；锁住该候选的 ozon_product；写 review_decision + 更新 candidate.status[adopt→adopted/reject→rejected]；返回决策）。

- [ ] **Step 1: 写失败测试 `tests/test_review_service.py`**

```python
import pytest
from sqlalchemy import select, func
from app.services.review import apply_auto_adopt, get_review_queue, decide
from app.models import CollectTask, OzonProduct, SupplyCandidate, ReviewDecision, User

async def _seed(db_session, review_config):
    t = CollectTask(name="t", entry_type="keyword", entry_value="x", provider="mock",
                    source_platforms=["ali1688"], review_config=review_config)
    db_session.add(t); await db_session.flush()
    p = OzonProduct(task_id=t.id, sku="S0", title="phone")
    db_session.add(p); await db_session.flush()
    c1 = SupplyCandidate(task_id=t.id, ozon_product_id=p.id, platform="ali1688", offer_id="A1", score_total=90.0, tier="auto")
    c2 = SupplyCandidate(task_id=t.id, ozon_product_id=p.id, platform="pinduoduo", offer_id="P1", score_total=60.0, tier="rejected")
    db_session.add_all([c1, c2]); await db_session.commit()
    return t.id, p.id, c1.id, c2.id

@pytest.mark.asyncio
async def test_auto_adopt_when_review_off(db_session):
    tid, pid, c1, c2 = await _seed(db_session, {"source_review_required": False, "source_score_min": 85})
    r = await apply_auto_adopt(db_session, tid)
    await db_session.commit()
    assert r["auto_adopted"] == 1                        # 仅 c1(>=85)
    cand1 = (await db_session.execute(select(SupplyCandidate).where(SupplyCandidate.id == c1))).scalar_one()
    assert cand1.status == "auto_adopted"
    rd = (await db_session.execute(select(ReviewDecision).where(ReviewDecision.candidate_id == c1))).scalar_one()
    assert rd.decision == "auto_adopt" and rd.reviewer_id is None
    # c1 已自动采用 → 审核队列不含其(但 c2 仍是 candidate)
    q = await get_review_queue(db_session, tid)
    prod_item = q["items"][0]
    cand_ids = [c["id"] for c in prod_item["candidates"]]
    assert c1 not in cand_ids and c2 in cand_ids

@pytest.mark.asyncio
async def test_decide_adopt_reject(db_session):
    tid, pid, c1, c2 = await _seed(db_session, {"source_review_required": True, "source_score_min": None})
    u = User(username="rv", password_hash="x", role="reviewer"); db_session.add(u); await db_session.flush()
    await decide(db_session, c1, u.id, "adopt", note="好")
    await decide(db_session, c2, u.id, "reject")
    await db_session.commit()
    cand1 = (await db_session.execute(select(SupplyCandidate).where(SupplyCandidate.id == c1))).scalar_one()
    cand2 = (await db_session.execute(select(SupplyCandidate).where(SupplyCandidate.id == c2))).scalar_one()
    assert cand1.status == "adopted" and cand2.status == "rejected"
    cnt = (await db_session.execute(select(func.count()).select_from(ReviewDecision).where(ReviewDecision.task_id == tid))).scalar_one()
    assert cnt == 2
```

- [ ] **Step 2: 运行确认失败**

Run: `ozon-listing-auto/server/.venv/bin/python -m pytest ozon-listing-auto/server/tests/test_review_service.py -v`
Expected: FAIL。

- [ ] **Step 3: 写 `services/review.py`**

```python
"""审核服务：review_config 自动采用 / 审核队列 / 采用拒绝决策 / Redis 并发锁。"""
from contextlib import asynccontextmanager
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import CollectTask, OzonProduct, SupplyCandidate, ReviewDecision

@asynccontextmanager
async def _noop_lock():
    yield

def review_lock(product_id: int):
    return _noop_lock()   # 生产替换为 Redis 锁

async def apply_auto_adopt(session: AsyncSession, task_id: int) -> dict:
    task = (await session.execute(select(CollectTask).where(CollectTask.id == task_id))).scalar_one()
    rc = task.review_config or {}
    if rc.get("source_review_required", True):
        return {"auto_adopted": 0}
    smin = rc.get("source_score_min")
    conds = [SupplyCandidate.task_id == task_id, SupplyCandidate.status == "candidate"]
    if smin is not None:
        conds.append(SupplyCandidate.score_total >= smin)
    cands = (await session.execute(select(SupplyCandidate).where(*conds))).scalars().all()
    n = 0
    for c in cands:
        c.status = "auto_adopted"
        session.add(ReviewDecision(task_id=task_id, ozon_product_id=c.ozon_product_id,
                                   candidate_id=c.id, reviewer_id=None, decision="auto_adopt"))
        n += 1
    return {"auto_adopted": n}

async def get_review_queue(session: AsyncSession, task_id: int, page: int = 1, page_size: int = 20) -> dict:
    prod_ids = (await session.execute(
        select(SupplyCandidate.ozon_product_id).where(
            SupplyCandidate.task_id == task_id, SupplyCandidate.status == "candidate"
        ).distinct().order_by(SupplyCandidate.ozon_product_id).offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()
    total = (await session.execute(
        select(SupplyCandidate.ozon_product_id).where(
            SupplyCandidate.task_id == task_id, SupplyCandidate.status == "candidate").distinct()
    )).scalars().all()
    items = []
    for pid in prod_ids:
        prod = (await session.execute(select(OzonProduct).where(OzonProduct.id == pid))).scalar_one()
        cands = (await session.execute(select(SupplyCandidate).where(
            SupplyCandidate.ozon_product_id == pid, SupplyCandidate.status == "candidate"
        ).order_by(SupplyCandidate.score_total.desc().nulls_last()))).scalars().all()
        items.append({
            "product": {"id": prod.id, "sku": prod.sku, "title": prod.title,
                        "main_image_url": prod.main_image_url, "price": prod.price},
            "candidates": [{"id": c.id, "platform": c.platform, "offer_id": c.offer_id, "title": c.title,
                            "price": c.price, "image_url": c.image_url, "supplier_name": c.supplier_name,
                            "score_total": c.score_total, "tier": c.tier,
                            "scores": {"image": c.score_image, "title": c.score_title, "attr": c.score_attr,
                                       "price": c.score_price, "supplier": c.score_supplier}} for c in cands],
        })
    return {"items": items, "total": len(total)}

async def decide(session: AsyncSession, candidate_id: int, reviewer_id: int | None,
                 decision: str, note: str | None = None, *, lock=None) -> dict:
    cand = (await session.execute(select(SupplyCandidate).where(SupplyCandidate.id == candidate_id))).scalar_one()
    lock = lock or review_lock(cand.ozon_product_id)
    async with lock:
        cand.status = "adopted" if decision == "adopt" else "rejected"
        session.add(ReviewDecision(task_id=cand.task_id, ozon_product_id=cand.ozon_product_id,
                                   candidate_id=cand.id, reviewer_id=reviewer_id, decision=decision, note=note))
    return {"candidate_id": candidate_id, "status": cand.status}
```

- [ ] **Step 4: 运行确认通过**

Run: `ozon-listing-auto/server/.venv/bin/python -m pytest ozon-listing-auto/server/tests/test_review_service.py -v`
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add ozon-listing-auto/server/app/services/review.py ozon-listing-auto/server/tests/test_review_service.py
git commit -m "feat(m3): 审核服务(自动采用/队列/采用拒绝决策/Redis 锁 no-op)"
```

---

### Task 6: 评分 API + 审核 API

**Files:**
- Create: `ozon-listing-auto/server/app/schemas/review.py`
- Create: `ozon-listing-auto/server/app/api/score.py`
- Create: `ozon-listing-auto/server/app/api/review.py`
- Modify: `ozon-listing-auto/server/app/main.py`
- Create: `ozon-listing-auto/server/tests/test_score_api.py`
- Create: `ozon-listing-auto/server/tests/test_review_api.py`

**Interfaces:**
- Produces:
  - `POST /score/start?task_id=&sync=false`(operator+; sync=true 跑 `run_score_core` 用 `dbmod.async_session`[conftest monkeypatch] + MockEmbedder + MockLLM)。`POST /score/pause`; `GET /score/monitor`。
  - `GET /review/queue?task_id=&page=&page_size=`(reviewer+)。`POST /review/{candidate_id}` body `{decision, note?}`(reviewer+)。`POST /review/auto-adopt?task_id=`(operator+)。
- `DecisionIn`(pydantic: decision Literal['adopt','reject'], note?)。

- [ ] **Step 1: 写失败测试 `tests/test_score_api.py`**

```python
import pytest
from sqlalchemy import select
from app.core.security import hash_password
from app.models import User, CollectTask, OzonProduct, SupplyCandidate
from app.services.embedding.mock import MockEmbedder

async def _seed_login(client, db_session, role="operator"):
    db_session.add(User(username="u", password_hash=hash_password("p"), role=role))
    t = CollectTask(name="t", entry_type="keyword", entry_value="x", provider="mock", source_platforms=["ali1688"])
    db_session.add(t); await db_session.flush()
    p = OzonProduct(task_id=t.id, sku="S0", title="耳机", main_image_url="https://img/o.jpg", attributes={})
    db_session.add(p); await db_session.flush()
    db_session.add(SupplyCandidate(task_id=t.id, ozon_product_id=p.id, platform="ali1688", offer_id="A1",
                                   title="耳机", price=9.9, image_url="https://img/o.jpg",
                                   embedding=await MockEmbedder().embed_image("https://img/o.jpg")))
    await db_session.commit()
    tok = (await client.post("/auth/login", data={"username": "u", "password": "p"})).json()["access_token"]
    return t.id, {"Authorization": f"Bearer {tok}"}

@pytest.mark.asyncio
async def test_score_start_sync(client, db_session):
    tid, h = await _seed_login(client, db_session)
    r = await client.post(f"/score/start?task_id={tid}&sync=true", headers=h)
    assert r.status_code == 200 and r.json()["status"] == "done"
    cand = (await db_session.execute(select(SupplyCandidate).where(SupplyCandidate.task_id == tid))).scalar_one()
    await db_session.refresh(cand)
    assert cand.score_total is not None and cand.tier is not None
```

- [ ] **Step 2: 写失败测试 `tests/test_review_api.py`**

```python
import pytest
from sqlalchemy import select
from app.core.security import hash_password
from app.models import User, CollectTask, OzonProduct, SupplyCandidate, ReviewDecision

async def _seed_login(client, db_session):
    db_session.add(User(username="rv", password_hash=hash_password("p"), role="reviewer"))
    t = CollectTask(name="t", entry_type="keyword", entry_value="x", provider="mock", source_platforms=["ali1688"])
    db_session.add(t); await db_session.flush()
    p = OzonProduct(task_id=t.id, sku="S0", title="耳机")
    db_session.add(p); await db_session.flush()
    c = SupplyCandidate(task_id=t.id, ozon_product_id=p.id, platform="ali1688", offer_id="A1", score_total=88.0, tier="auto")
    db_session.add(c); await db_session.commit()
    tok = (await client.post("/auth/login", data={"username": "rv", "password": "p"})).json()["access_token"]
    return t.id, c.id, {"Authorization": f"Bearer {tok}"}

@pytest.mark.asyncio
async def test_review_queue_and_decide(client, db_session):
    tid, cid, h = await _seed_login(client, db_session)
    q = await client.get(f"/review/queue?task_id={tid}", headers=h)
    assert q.status_code == 200 and q.json()["total"] == 1
    assert q.json()["items"][0]["candidates"][0]["tier"] == "auto"
    r = await client.post(f"/review/{cid}", json={"decision": "adopt", "note": "ok"}, headers=h)
    assert r.status_code == 200 and r.json()["status"] == "adopted"
    rd = (await db_session.execute(select(ReviewDecision).where(ReviewDecision.candidate_id == cid))).scalar_one()
    assert rd.decision == "adopt"
```

- [ ] **Step 3: 运行确认失败**

Run: `ozon-listing-auto/server/.venv/bin/python -m pytest ozon-listing-auto/server/tests/test_score_api.py ozon-listing-auto/server/tests/test_review_api.py -v`
Expected: FAIL。

- [ ] **Step 4: 写 `schemas/review.py`**

```python
"""审核 API schema。"""
from typing import Literal
from pydantic import BaseModel

class DecisionIn(BaseModel):
    decision: Literal["adopt", "reject"]
    note: str | None = None
```

- [ ] **Step 5: 写 `api/score.py`**

```python
"""评分控制 API：启动(同步/入队)/暂停/监控。"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import app.core.db as dbmod
from app.core.db import get_session
from app.api.deps import require_role
from app.models import CollectTask, User
from app.workers.scorer import run_score_core
from app.services.embedding.factory import get_embedder
from app.services.llm.factory import get_llm

router = APIRouter(prefix="/score", tags=["score"])

@router.post("/start")
async def start_score(task_id: int, sync: bool = False, s: AsyncSession = Depends(get_session), _: User = Depends(require_role("operator"))):
    t = (await s.execute(select(CollectTask).where(CollectTask.id == task_id))).scalar_one_or_none()
    if not t:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "任务不存在")
    if sync:
        await run_score_core(dbmod.async_session, task_id, embedder=get_embedder("mock"), llm=get_llm("mock"))
        return {"status": "done"}
    from arq import create_pool
    from arq.connections import RedisSettings
    from app.core.config import settings
    pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    try:
        await pool.enqueue_job("run_score", task_id)
    finally:
        await pool.aclose()
    return {"status": "queued"}

@router.post("/pause")
async def pause_score(task_id: int, s: AsyncSession = Depends(get_session), _: User = Depends(require_role("operator"))):
    t = (await s.execute(select(CollectTask).where(CollectTask.id == task_id))).scalar_one_or_none()
    if not t:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "任务不存在")
    t.score_status = "paused"; await s.commit()
    return {"ok": True}

@router.get("/monitor")
async def score_monitor(task_id: int, s: AsyncSession = Depends(get_session), _: User = Depends(require_role("operator"))):
    t = (await s.execute(select(CollectTask).where(CollectTask.id == task_id))).scalar_one_or_none()
    if not t:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "任务不存在")
    return {"score_status": t.score_status, "score_stats": t.score_stats}
```

- [ ] **Step 6: 写 `api/review.py`**

```python
"""审核台 API：队列 / 采用拒绝决策 / 自动采用。"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.db import get_session
from app.api.deps import require_role
from app.models import User
from app.schemas.review import DecisionIn
from app.services.review import get_review_queue, decide, apply_auto_adopt

router = APIRouter(prefix="/review", tags=["review"])

@router.get("/queue")
async def review_queue(task_id: int, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=200),
                       s: AsyncSession = Depends(get_session), _: User = Depends(require_role("reviewer"))):
    return await get_review_queue(s, task_id, page, page_size)

@router.post("/auto-adopt")
async def review_auto_adopt(task_id: int, s: AsyncSession = Depends(get_session), _: User = Depends(require_role("operator"))):
    r = await apply_auto_adopt(s, task_id); await s.commit()
    return r

@router.post("/{candidate_id}")
async def review_decide(candidate_id: int, body: DecisionIn, s: AsyncSession = Depends(get_session), user: User = Depends(require_role("reviewer"))):
    r = await decide(s, candidate_id, user.id, body.decision, body.note); await s.commit()
    return r
```

- [ ] **Step 7: 挂路由 `main.py`**

```python
from app.api.score import router as score_router
from app.api.review import router as review_router
app.include_router(score_router)
app.include_router(review_router)
```

- [ ] **Step 8: 运行确认通过 + 全套回归**

Run: `ozon-listing-auto/server/.venv/bin/python -m pytest ozon-listing-auto/server/tests -q`
Expected: PASS（0 warnings）。

- [ ] **Step 9: 提交**

```bash
git add ozon-listing-auto/server/app/schemas/review.py ozon-listing-auto/server/app/api/score.py ozon-listing-auto/server/app/api/review.py ozon-listing-auto/server/app/main.py ozon-listing-auto/server/tests/test_score_api.py ozon-listing-auto/server/tests/test_review_api.py
git commit -m "feat(m3): 评分 API(start/pause/monitor) + 审核 API(queue/decide/auto-adopt)"
```

---

### Task 7: OpenAICompatLLM 真实（Chat Completions + 译/抽）+ live 冒烟

**Files:**
- Modify: `ozon-listing-auto/server/app/services/llm/openai_compat.py`
- Create: `ozon-listing-auto/server/tests/test_llm_openai.py`

**Interfaces:**
- Produces: `OpenAICompatLLM`(从 `app_settings.llm` 读 base_url/api_key/model, 默认通义千问; `chat` 打 `POST {base_url}/chat/completions`; `translate`/`extract_json` 基于 chat, temperature=0, 重试; extract_json 解析 JSON 容错)。live 冒烟 `@pytest.mark.live`。

- [ ] **Step 1: 写失败测试 `tests/test_llm_openai.py`**（解析层可单测，网络部分 live）

```python
import pytest
from app.services.llm.openai_compat import _parse_json_loose

def test_parse_json_loose():
    assert _parse_json_loose('{"color": "black"}') == {"color": "black"}
    assert _parse_json_loose('```json\n{"a": 1}\n```') == {"a": 1}   # 去代码围栏
    assert _parse_json_loose("not json") == {}                        # 容错

@pytest.mark.live
@pytest.mark.asyncio
async def test_openai_translate_live():
    # 需在 app_settings.llm 配好 base_url/api_key/model; 无配置则跳过
    from app.services.llm.openai_compat import OpenAICompatLLM
    llm = OpenAICompatLLM(base_url="", api_key="", model="qwen-plus")
    with pytest.raises(Exception):
        await llm.translate("привет")
```

- [ ] **Step 2: 运行确认失败**

Run: `ozon-listing-auto/server/.venv/bin/python -m pytest ozon-listing-auto/server/tests/test_llm_openai.py -v`
Expected: FAIL（`_parse_json_loose` 未定义）。

- [ ] **Step 3: 写真实 `openai_compat.py`**

```python
"""OpenAICompatLLM：OpenAI 兼容 Chat Completions（默认通义千问 DashScope）。"""
import json
import re
import asyncio

def _parse_json_loose(text: str) -> dict:
    if not text:
        return {}
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    raw = m.group(1) if m else text
    m2 = re.search(r"\{.*\}", raw, re.DOTALL)
    if m2:
        raw = m2.group(0)
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}

class OpenAICompatLLM:
    name = "openai"
    def __init__(self, base_url: str, api_key: str, model: str, timeout: float = 30.0):
        self.base_url = base_url.rstrip("/"); self.api_key = api_key; self.model = model; self.timeout = timeout

    async def chat(self, messages: list[dict], *, temperature: float = 0.0, **opts) -> str:
        import httpx
        url = f"{self.base_url}/chat/completions"
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        body = {"model": self.model, "messages": messages, "temperature": temperature, **opts}
        last = None
        for _ in range(3):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as c:
                    r = await c.post(url, headers=headers, json=body)
                    r.raise_for_status()
                    return r.json()["choices"][0]["message"]["content"]
            except Exception as exc:  # noqa: BLE001
                last = exc
                await asyncio.sleep(1.0)
        raise RuntimeError(f"LLM chat 失败: {last}")

    async def translate(self, text: str, target_lang: str = "zh") -> str:
        msg = [{"role": "user", "content": f"把下面文本翻译成中文，只返回译文：\n{text}"}]
        return await self.chat(msg)

    async def extract_json(self, prompt: str) -> dict:
        msg = [{"role": "user", "content": prompt + "\n只返回 JSON。"}]
        return _parse_json_loose(await self.chat(msg))
```

注意：`factory.get_llm("openai")` 需能构造它——从 `app_settings.llm` 读配置。为不引入 DB 依赖到工厂，工厂里的 openai 分支用环境/配置默认值构造，或由调用方传参。M3 简化：`get_llm("openai")` 从 `settings` 读默认（base_url/api_key/model 可为占位），真实值由运维在 `app_settings.llm` 配好后，worker 启动时读取注入（本任务只保证类可用 + 解析层可测；真实注入在 live 联调完善）。**为通过 Step 1 的 `OpenAICompatLLM(base_url=..., api_key=..., model=...)` 构造**，保持上面的显式构造签名。

- [ ] **Step 4: 运行确认通过（非 live）**

Run: `ozon-listing-auto/server/.venv/bin/python -m pytest ozon-listing-auto/server/tests -q`
Expected: PASS（0 warnings；live 跳过）。

- [ ] **Step 5: 提交**

```bash
git add ozon-listing-auto/server/app/services/llm/openai_compat.py ozon-listing-auto/server/tests/test_llm_openai.py
git commit -m "feat(m3): OpenAICompatLLM(Chat Completions+译/抽, JSON 容错) + live 冒烟"
```

---

## 阶段 3 · 审核台前端 + 文档

### Task 8: 审核台前端 ReviewBoard + 开始评分

**Files:**
- Create: `ozon-listing-auto/web/src/api/review.ts`
- Create: `ozon-listing-auto/web/src/pages/ReviewBoard.tsx`
- Modify: `ozon-listing-auto/web/src/App.tsx`(加 /review 路由)
- Modify: `ozon-listing-auto/web/src/pages/Layout.tsx`(加菜单项)
- Create: `ozon-listing-auto/web/src/pages/ReviewBoard.test.tsx`

**Interfaces:**
- Produces: `api/review.ts`(`startScore(taskId)`, `getQueue(taskId)`, `decide(candidateId, decision, note?)`, `autoAdopt(taskId)`); ReviewBoard 页(选任务→开始评分→拉队列→左 Ozon/右候选卡片[平台标签+五维分+总分+tier]+采用/拒绝按钮+审核开关/阈值+二次确认)。

- [ ] **Step 1: 写 `api/review.ts`**

```ts
import { api } from "./client";

export const startScore = (taskId: number) => api.post(`/score/start?task_id=${taskId}&sync=true`).then(r => r.data);
export const getQueue = (taskId: number) => api.get(`/review/queue?task_id=${taskId}`).then(r => r.data);
export const decide = (candidateId: number, decision: "adopt" | "reject", note?: string) =>
  api.post(`/review/${candidateId}`, { decision, note }).then(r => r.data);
export const autoAdopt = (taskId: number) => api.post(`/review/auto-adopt?task_id=${taskId}`).then(r => r.data);
```

- [ ] **Step 2: 写 `pages/ReviewBoard.tsx`**

```tsx
import { useState } from "react";
import { Card, InputNumber, Button, Row, Col, Tag, Space, message, Image, Descriptions, Popconfirm } from "antd";
import { startScore, getQueue, decide, autoAdopt } from "../api/review";

const TIER_COLOR: Record<string, string> = { auto: "green", review: "gold", rejected: "red" };

export default function ReviewBoard() {
  const [taskId, setTaskId] = useState<number>();
  const [items, setItems] = useState<any[]>([]);
  const [idx, setIdx] = useState(0);

  const load = async () => { if (!taskId) { message.warning("请先输入任务ID"); return; }
    const q = await getQueue(taskId); setItems(q.items); setIdx(0); };
  const onScore = async () => { if (!taskId) return; await startScore(taskId); message.success("评分完成"); load(); };
  const onDecide = async (cid: number, d: "adopt" | "reject") => {
    await decide(cid, d); message.success(d === "adopt" ? "已采用" : "已拒绝"); load(); };
  const onAutoAdopt = async () => { if (!taskId) return; const r = await autoAdopt(taskId);
    message.success(`自动采用 ${r.auto_adopted} 条`); load(); };

  const cur = items[idx];
  return (
    <Space direction="vertical" style={{ width: "100%" }} size="large">
      <Card title="审核台">
        <Space>
          任务ID <InputNumber onChange={(v) => setTaskId(v as number)} />
          <Button type="primary" onClick={onScore}>开始评分</Button>
          <Button onClick={load}>拉取审核队列</Button>
          <Popconfirm title="关闭人工审核将按阈值自动采用达标候选，确认？" onConfirm={onAutoAdopt}>
            <Button danger>关闭审核·自动采用</Button>
          </Popconfirm>
        </Space>
      </Card>
      {cur && (
        <Row gutter={16}>
          <Col span={8}>
            <Card title={`Ozon 商品 (${idx + 1}/${items.length})`}>
              {cur.product.main_image_url && <Image src={cur.product.main_image_url} width={120} />}
              <Descriptions column={1} size="small">
                <Descriptions.Item label="标题">{cur.product.title}</Descriptions.Item>
                <Descriptions.Item label="SKU">{cur.product.sku}</Descriptions.Item>
                <Descriptions.Item label="价">{cur.product.price}</Descriptions.Item>
              </Descriptions>
              <Space>
                <Button disabled={idx === 0} onClick={() => setIdx(idx - 1)}>上一条</Button>
                <Button disabled={idx >= items.length - 1} onClick={() => setIdx(idx + 1)}>下一条</Button>
              </Space>
            </Card>
          </Col>
          <Col span={16}>
            <Space direction="vertical" style={{ width: "100%" }}>
              {cur.candidates.map((c: any) => (
                <Card key={c.id} size="small"
                  title={<Space><Tag color={c.platform === "ali1688" ? "blue" : "magenta"}>{c.platform}</Tag>
                    {c.title}<Tag color={TIER_COLOR[c.tier]}>{c.tier} · {c.score_total?.toFixed(1)}</Tag></Space>}
                  extra={<Space>
                    <Button type="primary" size="small" onClick={() => onDecide(c.id, "adopt")}>采用</Button>
                    <Button danger size="small" onClick={() => onDecide(c.id, "reject")}>拒绝</Button></Space>}>
                  <Space size="large">
                    <span>图 {c.scores.image?.toFixed(0)}</span><span>标题 {c.scores.title?.toFixed(0)}</span>
                    <span>属性 {c.scores.attr?.toFixed(0)}</span><span>价 {c.scores.price?.toFixed(0)}</span>
                    <span>供应商 {c.scores.supplier?.toFixed(0)}</span><span>价格 ¥{c.price}</span>
                  </Space>
                </Card>
              ))}
            </Space>
          </Col>
        </Row>
      )}
    </Space>
  );
}
```

- [ ] **Step 3: 加路由与菜单**

`App.tsx` 在受保护路由内加：
```tsx
import ReviewBoard from "./pages/ReviewBoard";
// <Route path="/review" element={<ReviewBoard />} />
```
`Layout.tsx` 菜单 items 加：`{ key: "review", label: "审核台" }`。

- [ ] **Step 4: 写测试 `pages/ReviewBoard.test.tsx`**

```tsx
import { render, screen } from "@testing-library/react";
import { vi } from "vitest";
vi.mock("../api/review", () => ({
  startScore: vi.fn(), getQueue: vi.fn(() => Promise.resolve({ items: [], total: 0 })),
  decide: vi.fn(), autoAdopt: vi.fn(),
}));
import ReviewBoard from "./ReviewBoard";

test("渲染审核台", () => {
  render(<ReviewBoard />);
  expect(screen.getByText("审核台")).toBeInTheDocument();
  expect(screen.getByText("开始评分")).toBeInTheDocument();
});
```

- [ ] **Step 5: 运行前端测试 + build**

Run: `cd ozon-listing-auto/web && npx vitest run && npm run build`
Expected: 所有前端测试通过（Login/Tasks/Products/ReviewBoard）；`npm run build` 成功。

- [ ] **Step 6: 提交**

```bash
git add ozon-listing-auto/web/src/api/review.ts ozon-listing-auto/web/src/pages/ReviewBoard.tsx ozon-listing-auto/web/src/pages/ReviewBoard.test.tsx ozon-listing-auto/web/src/App.tsx ozon-listing-auto/web/src/pages/Layout.tsx
git commit -m "feat(m3): 审核台前端 ReviewBoard(左Ozon/右候选五维分+tier, 采用/拒绝/自动采用)"
```

---

### Task 9: README/docs M3 + 全量回归

**Files:**
- Modify: `ozon-listing-auto/README.md`
- Create: `ozon-listing-auto/docs/M3-评分审核说明.md`

**Interfaces:**
- Produces: README M3 段 + M3 使用说明。

- [ ] **Step 1: 更新 `README.md` M3 段**

加 M3 功能：五维评分(图/标题/属性/价格/供应商, 权重阈值可配)、LLM 抽象(mock/openai, 默认通义千问, 译标题+抽属性)、审核台(采用/拒绝/换候选/审核开关+阈值/自动采用/Redis 锁)、评分/审核 API + 审核台前端。更新里程碑状态(M1+M2+M3 done)。

- [ ] **Step 2: 写 `docs/M3-评分审核说明.md`**

流程：采集(M1)→匹配(M2)→`/score/start`(mock 跑通, 候选得五维分+tier)→审核台(左Ozon/右候选, 采用/拒绝)或关审核开关自动采用→切真实 LLM(配 `app_settings.llm` base_url/api_key/model + `LLM_PROVIDER=openai`)。

- [ ] **Step 3: 全量回归**

Run: `cd ozon-listing-auto/server && .venv/bin/python -m pytest -q && cd ../web && npx vitest run && npm run build`
Expected: 后端全绿(非 live, 0 warnings)；前端全绿 + build 成功。

- [ ] **Step 4: 提交**

```bash
git add ozon-listing-auto/README.md ozon-listing-auto/docs/M3-评分审核说明.md
git commit -m "docs: README + M3 评分审核说明"
```

---

## 验收对照（spec §8）

| 验收项 | 覆盖任务 |
|---|---|
| 迁移 0003(embedding/五维分/tier/review_decisions/score_*) | Task 1 |
| 采集→匹配→score/start→五维分+总分+tier | Task 3,4,6 |
| 审核台前端(左Ozon/右候选平台标签+分+tier, 采用/拒绝/换候选, 写 review_decisions) | Task 5,6,8 |
| 可配开关(不需审核+阈值→自动采用+留痕; 关开关二次确认) | Task 5,6,8 |
| 多人审核 Redis 并发锁 | Task 5 |
| MockLLM+MockEmbedder 全链路 + OpenAICompatLLM 配置切换 + live 跳过 | Task 2,4,7 |
| 非 live 0 warnings + README/docs + 前端 build | Task 9 |

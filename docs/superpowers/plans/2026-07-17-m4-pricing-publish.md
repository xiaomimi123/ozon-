# M4 跟卖定价 + 挂靠上架 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 对已采用货源候选定价(内置公式/自定义 simpleeval + 最低价保护)→生成跟卖草稿→人工确认闸门→调 Ozon Seller API(mock-first) 挂靠到目标商品卡。验收「跟卖草稿→测试店成功挂靠」。管线：审核采用(M3)→定价+草稿→确认→挂靠(M4)。M4 直接挂靠、无节奏(节奏 M5)。

**Architecture:** 沿用 mock-first + 配置驱动 provider 模式。新增 pricing 引擎; OzonSellerProvider 抽象(mock/real, real live 默认跳过); listing_builder(已采用候选+定价→草稿); publisher(确认草稿→挂靠→回写); shops 店铺凭据表; 前端 ListingReview/Shops/定价设置。测试全走 mock(无真实 Ozon/网络/key)。

**Tech Stack:** 承接 M1-M3(FastAPI async / SQLAlchemy2 / Alembic / ARQ / Postgres+pgvector / Redis / React+Vite+AntD)。新增 `simpleeval`(安全公式求值); Ozon 写入走 httpx(已装, real 层)。

## Global Constraints

- Python 3.11；后端全异步；worker 幂等。
- 定价参数默认 `DEFAULT_PRICING`(mode=builtin, commission_rate=0.15, fulfillment_rate=0.10, fx=13.0, target_margin=0.20, logistics=5.0, min_price=0.0, strike_coeff=1.3, formula="")；从 `app_settings.pricing` 读，缺省用默认。
- 内置公式：`到手成本=cost+logistics`; `denom=1-target_margin-commission_rate-fulfillment_rate`(denom<=0 → blocked); `售价(RUB)=到手成本/denom×fx`; `划线价=售价×strike_coeff`; 售价<min_price → blocked。
- 自定义公式用 simpleeval, 变量白名单 {cost,logistics,commission_rate,fulfillment_rate,fx,weight,target_margin,min_price}, 禁任意代码。
- 草稿由 M3 status∈{adopted,auto_adopted} 的候选生成; status: draft|confirmed|publishing|published|failed|below_min; (task_id,candidate_id) 唯一幂等。
- Ozon 写入 mock-first: MockOzonSeller 确定性; RealOzonSeller live 默认跳过。ozon_seller 名枚举 mock/real(默认 mock)。
- 店铺凭据 Fernet 加密(shops.api_key_encrypted); 响应绝不含明文 api_key。
- 角色: shops/settings 管 → admin; build/auto-confirm → operator+; confirm → reviewer+; publish → publisher+; admin 超级通过。
- 敏感信息 Fernet 加密; structlog 带 task_id; 中文注释/每模块一行中文 docstring。
- 迁移列有 server_default 且 ORM NOT NULL 的必须 nullable=False(M2/M3 教训)。向量列复用 with_variant(此里程碑无新向量列)。
- TDD; pytest 0 warnings; 测试全走 mock(无真实 Ozon/网络/key/torch)。
- 代码库 `ozon-listing-auto/`; venv `ozon-listing-auto/server/.venv`(3.11); 跑测试 `ozon-listing-auto/server/.venv/bin/python -m pytest`(勿用系统 python3=3.9); Node via nvm。
- 建立在 M3 之上: 复用 SupplyCandidate/OzonProduct/CollectTask 模型 + candidate.status(adopted/auto_adopted, M3)、candidate.price(CNY, M2)、ozon.weight(M1)、review_config(M1)、candidate.score_total(M3, listing_score_min 用); api/deps(require_role/get_current_user); settings_store; crypto; conftest(内存 SQLite + monkeypatch async_session); collector/matcher/scorer 的 §4.2.6 failed 范式 + sync=true 用 mock 的 API 范式; live marker; passlib filterwarnings; ConfigDict/Query(ge=1)/HTTP_*_CONTENT 常量。

## 文件结构

```
server/app/
├── models/{shop.py, listing_draft.py, ozon_product.py(+barcode)}
├── alembic/versions/0004_m4_pricing_publish.py
├── schemas/{shop.py, listing.py}
├── api/{shops.py, listing.py}
├── services/
│   ├── pricing.py
│   ├── ozon_seller/{base.py, mock.py, real.py, factory.py}
│   └── listing_builder.py
└── workers/{publisher.py, arq_worker.py(+run_publish)}
web/src/{pages/ListingReview.tsx, pages/Shops.tsx, api/listing.ts, api/shops.ts, App.tsx(+routes), pages/Layout.tsx(+menu)}
server/tests/{test_listing_models.py, test_pricing.py, test_ozon_seller.py, test_listing_builder.py,
              test_publisher.py, test_shops_api.py, test_listing_api.py}
```

---

## 阶段 0 · Schema

### Task 1: 迁移 0004 + ORM(shops / listing_drafts / ozon_products.barcode)

**Files:**
- Create: `ozon-listing-auto/server/app/models/shop.py`
- Create: `ozon-listing-auto/server/app/models/listing_draft.py`
- Modify: `ozon-listing-auto/server/app/models/ozon_product.py`(加 barcode)
- Modify: `ozon-listing-auto/server/app/models/__init__.py`
- Create: `ozon-listing-auto/server/alembic/versions/0004_m4_pricing_publish.py`
- Create: `ozon-listing-auto/server/tests/test_listing_models.py`

**Interfaces:**
- Produces: `Shop` ORM; `ListingDraft` ORM(字段见 spec §3.2); `OzonProduct.barcode`。

**关键:** 复用 M1/M2 的 `_JSONB = JSONB().with_variant(JSON(), "sqlite")`(读现有模型确认变量名)。迁移 NOT NULL: shops.is_active/is_sandbox/created_at/updated_at; listing_drafts.mode/currency/stock_qty/status/created_at/updated_at + FK task_id/ozon_product_id/candidate_id — 均 nullable=False(有 server_default 的加 server_default)。price/cost/margin/barcode/shop_id/scheduled_at/ozon_result/error 保持 nullable。

- [ ] **Step 1: 写 `models/shop.py`**

```python
"""Ozon 店铺凭据 ORM：Client-Id 明文 + Api-Key Fernet 加密。"""
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, LargeBinary, func
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db import Base

class Shop(Base):
    __tablename__ = "shops"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    platform: Mapped[str] = mapped_column(String(16), default="ozon")
    client_id: Mapped[str] = mapped_column(String(128))
    api_key_encrypted: Mapped[bytes] = mapped_column(LargeBinary)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_sandbox: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
```

- [ ] **Step 2: 写 `models/listing_draft.py`**

```python
"""跟卖上架草稿 ORM。"""
from datetime import datetime
from sqlalchemy import String, Integer, Numeric, Text, DateTime, ForeignKey, UniqueConstraint, Index, JSON, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db import Base

_JSONB = JSONB().with_variant(JSON(), "sqlite")

class ListingDraft(Base):
    __tablename__ = "listing_drafts"
    __table_args__ = (
        UniqueConstraint("task_id", "candidate_id", name="uq_draft_candidate"),
        Index("ix_draft_task_status", "task_id", "status"),
        Index("ix_draft_shop", "shop_id"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("collect_tasks.id"), index=True)
    ozon_product_id: Mapped[int] = mapped_column(ForeignKey("ozon_products.id"))
    candidate_id: Mapped[int] = mapped_column(ForeignKey("supply_candidates.id"))
    shop_id: Mapped[int | None] = mapped_column(ForeignKey("shops.id"), nullable=True)
    mode: Mapped[str] = mapped_column(String(8), default="follow")
    target_ozon_sku: Mapped[str | None] = mapped_column(String(64), nullable=True)
    barcode: Mapped[str | None] = mapped_column(String(64), nullable=True)
    price: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(8), default="RUB")
    stock_qty: Mapped[int] = mapped_column(Integer, default=0)
    cost: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    margin: Mapped[float | None] = mapped_column(Numeric(6, 4), nullable=True)
    pricing_detail: Mapped[dict | None] = mapped_column(_JSONB, nullable=True)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="draft")
    ozon_result: Mapped[dict | None] = mapped_column(_JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
```

注意：`Numeric` 列在 SQLite 返回 `Decimal`；测试比较时用 `float(x)` 或 `pytest.approx`。若更省事可用 `Float` 替 `Numeric`——但价格用 Numeric 更准；测试注意类型。

- [ ] **Step 3: 改 `ozon_product.py` 加 barcode**

在 `OzonProduct` 加：
```python
    barcode: Mapped[str | None] = mapped_column(String(64), nullable=True)
```

- [ ] **Step 4: 改 `models/__init__.py` 导出 `Shop`, `ListingDraft`(加 import + __all__)**

- [ ] **Step 5: 写失败测试 `tests/test_listing_models.py`**

```python
import pytest
from sqlalchemy import select
from app.models import Shop, ListingDraft, CollectTask, OzonProduct, SupplyCandidate

@pytest.mark.asyncio
async def test_shop_and_draft(db_session):
    t = CollectTask(name="t", entry_type="keyword", entry_value="x", provider="mock", source_platforms=["ali1688"])
    db_session.add(t); await db_session.flush()
    p = OzonProduct(task_id=t.id, sku="OZSKU1", title="phone", barcode="4600000000001")
    db_session.add(p); await db_session.flush()
    c = SupplyCandidate(task_id=t.id, ozon_product_id=p.id, platform="ali1688", offer_id="A1", status="adopted")
    db_session.add(c); await db_session.flush()
    shop = Shop(name="测试店", client_id="CID", api_key_encrypted=b"x")
    db_session.add(shop); await db_session.flush()
    d = ListingDraft(task_id=t.id, ozon_product_id=p.id, candidate_id=c.id, shop_id=shop.id,
                     target_ozon_sku="OZSKU1", barcode="4600000000001", price=1290.00, cost=20.0, margin=0.2)
    db_session.add(d); await db_session.commit()
    assert shop.is_active is True and shop.is_sandbox is True
    got = (await db_session.execute(select(ListingDraft).where(ListingDraft.candidate_id == c.id))).scalar_one()
    assert got.status == "draft" and got.mode == "follow" and got.currency == "RUB"
    assert float(got.price) == 1290.00
    assert p.barcode == "4600000000001"
```

- [ ] **Step 6: 运行确认失败**

Run: `ozon-listing-auto/server/.venv/bin/python -m pytest ozon-listing-auto/server/tests/test_listing_models.py -v`
Expected: FAIL(模型/列未定义)。

- [ ] **Step 7: 写迁移 `0004_m4_pricing_publish.py`**

```python
"""m4 pricing publish"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0004"
down_revision = "0003"

def upgrade():
    op.create_table("shops",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("platform", sa.String(16), server_default="ozon", nullable=False),
        sa.Column("client_id", sa.String(128), nullable=False),
        sa.Column("api_key_encrypted", sa.LargeBinary, nullable=False),
        sa.Column("is_active", sa.Boolean, server_default=sa.true(), nullable=False),
        sa.Column("is_sandbox", sa.Boolean, server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.add_column("ozon_products", sa.Column("barcode", sa.String(64)))
    op.create_table("listing_drafts",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("task_id", sa.Integer, sa.ForeignKey("collect_tasks.id"), nullable=False, index=True),
        sa.Column("ozon_product_id", sa.Integer, sa.ForeignKey("ozon_products.id"), nullable=False),
        sa.Column("candidate_id", sa.Integer, sa.ForeignKey("supply_candidates.id"), nullable=False),
        sa.Column("shop_id", sa.Integer, sa.ForeignKey("shops.id")),
        sa.Column("mode", sa.String(8), server_default="follow", nullable=False),
        sa.Column("target_ozon_sku", sa.String(64)),
        sa.Column("barcode", sa.String(64)),
        sa.Column("price", sa.Numeric(14, 2)),
        sa.Column("currency", sa.String(8), server_default="RUB", nullable=False),
        sa.Column("stock_qty", sa.Integer, server_default="0", nullable=False),
        sa.Column("cost", sa.Numeric(14, 2)),
        sa.Column("margin", sa.Numeric(6, 4)),
        sa.Column("pricing_detail", postgresql.JSONB),
        sa.Column("scheduled_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(16), server_default="draft", nullable=False),
        sa.Column("ozon_result", postgresql.JSONB),
        sa.Column("error", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("task_id", "candidate_id", name="uq_draft_candidate"),
    )
    op.create_index("ix_draft_task_status", "listing_drafts", ["task_id", "status"])
    op.create_index("ix_draft_shop", "listing_drafts", ["shop_id"])

def downgrade():
    op.drop_table("listing_drafts")
    op.drop_column("ozon_products", "barcode")
    op.drop_table("shops")
```

- [ ] **Step 8: 运行确认通过 + 全套回归**

Run: `ozon-listing-auto/server/.venv/bin/python -m pytest ozon-listing-auto/server/tests -q`
Expected: PASS(0 warnings)。

- [ ] **Step 9: 提交**

```bash
git add ozon-listing-auto/server/app/models ozon-listing-auto/server/alembic/versions/0004_m4_pricing_publish.py ozon-listing-auto/server/tests/test_listing_models.py
git commit -m "feat(m4): 迁移0004 + ORM(shops/listing_drafts/ozon_products.barcode)"
```

---

## 阶段 1 · 定价 + Ozon 写入抽象

### Task 2: 定价引擎（内置公式 + simpleeval 自定义 + 最低价保护）

**Files:**
- Modify: `ozon-listing-auto/server/pyproject.toml`(加 simpleeval)
- Create: `ozon-listing-auto/server/app/services/pricing.py`
- Create: `ozon-listing-auto/server/tests/test_pricing.py`

**Interfaces:**
- Produces: `DEFAULT_PRICING`(dict); `PriceResult`(dataclass: price/cost/margin/strike/blocked/detail); `price_candidate(cost_cny, weight, params) -> PriceResult`。

- [ ] **Step 1: pyproject 加 simpleeval**

`[project].dependencies` 加：
```toml
  "simpleeval>=0.9",
```
安装：`ozon-listing-auto/server/.venv/bin/pip install -e "ozon-listing-auto/server[dev]"`。

- [ ] **Step 2: 写失败测试 `tests/test_pricing.py`**

```python
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
```

- [ ] **Step 3: 运行确认失败**

Run: `ozon-listing-auto/server/.venv/bin/python -m pytest ozon-listing-auto/server/tests/test_pricing.py -v`
Expected: FAIL。

- [ ] **Step 4: 写 `pricing.py`**

```python
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
```

- [ ] **Step 5: 运行确认通过**

Run: `ozon-listing-auto/server/.venv/bin/python -m pytest ozon-listing-auto/server/tests/test_pricing.py -v`
Expected: PASS。

- [ ] **Step 6: 提交**

```bash
git add ozon-listing-auto/server/pyproject.toml ozon-listing-auto/server/app/services/pricing.py ozon-listing-auto/server/tests/test_pricing.py
git commit -m "feat(m4): 定价引擎(内置反推+simpleeval 自定义公式+最低价保护)"
```

---

### Task 3: Ozon 写入抽象（OzonSellerProvider mock/real + 工厂）

**Files:**
- Create: `ozon-listing-auto/server/app/services/ozon_seller/__init__.py`
- Create: `ozon-listing-auto/server/app/services/ozon_seller/base.py`
- Create: `ozon-listing-auto/server/app/services/ozon_seller/mock.py`
- Create: `ozon-listing-auto/server/app/services/ozon_seller/real.py`(占位 real, live)
- Create: `ozon-listing-auto/server/app/services/ozon_seller/factory.py`
- Create: `ozon-listing-auto/server/tests/test_ozon_seller.py`

**Interfaces:**
- Produces: `base.PublishResult`(dataclass); `base.OzonSellerProvider`(Protocol: `create_follow_offer`); `mock.MockOzonSeller`(确定性 ok+ozon id); `real.RealOzonSeller`(httpx, 方法内 import, live); `factory.get_ozon_seller(name="mock")`(real 惰性)。

- [ ] **Step 1: 写失败测试 `tests/test_ozon_seller.py`**

```python
import pytest
from app.services.ozon_seller.factory import get_ozon_seller
from app.services.ozon_seller.base import PublishResult

@pytest.mark.asyncio
async def test_mock_ozon_seller():
    s = get_ozon_seller("mock")
    r = await s.create_follow_offer(client_id="C", api_key="K", target_sku="OZSKU1",
                                    barcode="460", price=1290.0, stock=10, offer_id="A1")
    assert isinstance(r, PublishResult)
    assert r.ok is True and r.status == "published" and r.ozon_product_id == "OZ-A1"

def test_factory_unknown():
    with pytest.raises(ValueError):
        get_ozon_seller("nope")
```

- [ ] **Step 2: 运行确认失败**

Run: `ozon-listing-auto/server/.venv/bin/python -m pytest ozon-listing-auto/server/tests/test_ozon_seller.py -v`
Expected: FAIL。

- [ ] **Step 3: 写 `base.py`**

```python
"""Ozon Seller 写入抽象：跟卖 offer 创建(§5.9 follow 分支)。"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Protocol

@dataclass
class PublishResult:
    ok: bool
    ozon_product_id: str | None
    status: str            # published | pending_review | failed
    raw: dict = field(default_factory=dict)
    error: str | None = None

class OzonSellerProvider(Protocol):
    name: str
    async def create_follow_offer(self, *, client_id: str, api_key: str, target_sku: str,
                                  barcode: str | None, price: float, stock: int, offer_id: str) -> PublishResult: ...
```

- [ ] **Step 4: 写 `mock.py`、`real.py`、`factory.py`**

`mock.py`:
```python
"""MockOzonSeller：确定性挂靠成功，供 mock-first 跑通链路。"""
from app.services.ozon_seller.base import PublishResult

class MockOzonSeller:
    name = "mock"
    async def create_follow_offer(self, *, client_id, api_key, target_sku, barcode, price, stock, offer_id) -> PublishResult:
        return PublishResult(ok=True, ozon_product_id=f"OZ-{offer_id}", status="published",
                             raw={"target_sku": target_sku, "price": price, "stock": stock})
```

`real.py`:
```python
"""RealOzonSeller：以条码/SKU 调 Ozon Seller API 创建跟卖 offer(live 默认跳过, 端点联调时定)。"""
from app.services.ozon_seller.base import PublishResult

_ENDPOINT = "https://api-seller.ozon.ru/v2/product/import"   # 占位; 真实跟卖端点联调时校正

class RealOzonSeller:
    name = "real"
    def __init__(self, timeout: float = 30.0):
        self._timeout = timeout
    async def create_follow_offer(self, *, client_id, api_key, target_sku, barcode, price, stock, offer_id) -> PublishResult:
        import httpx
        headers = {"Client-Id": client_id, "Api-Key": api_key, "Content-Type": "application/json"}
        body = {"items": [{"offer_id": offer_id, "barcode": barcode, "price": str(price),
                           "stock": stock, "sku": target_sku}]}
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as c:
                r = await c.post(_ENDPOINT, headers=headers, json=body)
                r.raise_for_status()
                data = r.json()
            return PublishResult(ok=True, ozon_product_id=str(data.get("result", {}).get("task_id", offer_id)),
                                 status="pending_review", raw=data)
        except Exception as exc:  # noqa: BLE001
            return PublishResult(ok=False, ozon_product_id=None, status="failed", error=str(exc))
```

`factory.py`:
```python
"""按名返回 OzonSellerProvider；默认 mock，real 惰性 import。"""
from app.services.ozon_seller.base import OzonSellerProvider
from app.services.ozon_seller.mock import MockOzonSeller

def get_ozon_seller(name: str = "mock") -> OzonSellerProvider:
    if name == "mock":
        return MockOzonSeller()
    if name == "real":
        from app.services.ozon_seller.real import RealOzonSeller
        return RealOzonSeller()
    raise ValueError(f"未知 ozon_seller: {name}")
```

- [ ] **Step 5: 运行确认通过**

Run: `ozon-listing-auto/server/.venv/bin/python -m pytest ozon-listing-auto/server/tests/test_ozon_seller.py -v`
Expected: PASS。

- [ ] **Step 6: 提交**

```bash
git add ozon-listing-auto/server/app/services/ozon_seller ozon-listing-auto/server/tests/test_ozon_seller.py
git commit -m "feat(m4): Ozon 写入抽象 OzonSellerProvider(mock/real 惰性)+工厂"
```

---

### Task 4: 草稿生成（listing_builder）

**Files:**
- Create: `ozon-listing-auto/server/app/services/listing_builder.py`
- Create: `ozon-listing-auto/server/tests/test_listing_builder.py`

**Interfaces:**
- Consumes: `price_candidate`(Task 2), `SupplyCandidate`/`OzonProduct`/`ListingDraft` 模型。
- Produces: `async build_follow_drafts(session, task_id, *, params=None, shop_id=None) -> dict`（对 status∈{adopted,auto_adopted} 且无草稿的候选，定价→建 ListingDraft(mode=follow, target_ozon_sku=ozon.sku, barcode=ozon.barcode, price/cost/margin/pricing_detail, shop_id, status=below_min if blocked else draft)；(task_id,candidate_id) 幂等；返回 `{built, blocked, skipped}`）。

- [ ] **Step 1: 写失败测试 `tests/test_listing_builder.py`**

```python
import pytest
from sqlalchemy import select
from app.services.listing_builder import build_follow_drafts
from app.services.pricing import DEFAULT_PRICING
from app.models import CollectTask, OzonProduct, SupplyCandidate, ListingDraft

async def _seed(db_session):
    t = CollectTask(name="t", entry_type="keyword", entry_value="x", provider="mock", source_platforms=["ali1688"])
    db_session.add(t); await db_session.flush()
    p = OzonProduct(task_id=t.id, sku="OZSKU1", title="phone", barcode="460", weight=0.3)
    db_session.add(p); await db_session.flush()
    # 一个已采用(adopted), 一个未采用(candidate)
    db_session.add(SupplyCandidate(task_id=t.id, ozon_product_id=p.id, platform="ali1688", offer_id="A1",
                                   price=15.0, status="adopted"))
    db_session.add(SupplyCandidate(task_id=t.id, ozon_product_id=p.id, platform="ali1688", offer_id="A2",
                                   price=20.0, status="candidate"))
    await db_session.commit()
    return t.id, p.id

@pytest.mark.asyncio
async def test_build_only_adopted(db_session):
    tid, pid = await _seed(db_session)
    r = await build_follow_drafts(db_session, tid, params=DEFAULT_PRICING, shop_id=None)
    await db_session.commit()
    assert r["built"] == 1                              # 仅 adopted 生成草稿
    drafts = (await db_session.execute(select(ListingDraft).where(ListingDraft.task_id == tid))).scalars().all()
    assert len(drafts) == 1
    d = drafts[0]
    assert d.mode == "follow" and d.target_ozon_sku == "OZSKU1" and d.barcode == "460"
    assert float(d.price) > 0 and float(d.cost) > 0 and d.status == "draft"
    # 幂等: 再次 build 不新增
    r2 = await build_follow_drafts(db_session, tid, params=DEFAULT_PRICING)
    await db_session.commit()
    assert r2["built"] == 0

@pytest.mark.asyncio
async def test_build_below_min_flagged(db_session):
    tid, pid = await _seed(db_session)
    params = {**DEFAULT_PRICING, "min_price": 1e9}
    r = await build_follow_drafts(db_session, tid, params=params)
    await db_session.commit()
    d = (await db_session.execute(select(ListingDraft).where(ListingDraft.task_id == tid))).scalar_one()
    assert d.status == "below_min"
    assert r["blocked"] == 1
```

- [ ] **Step 2: 运行确认失败**

Run: `ozon-listing-auto/server/.venv/bin/python -m pytest ozon-listing-auto/server/tests/test_listing_builder.py -v`
Expected: FAIL。

- [ ] **Step 3: 写 `listing_builder.py`**

```python
"""跟卖草稿生成：已采用候选 + 定价 → listing_drafts(§5.9)。"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.pricing import price_candidate, DEFAULT_PRICING
from app.models import OzonProduct, SupplyCandidate, ListingDraft

async def build_follow_drafts(session: AsyncSession, task_id: int, *, params: dict | None = None, shop_id: int | None = None) -> dict:
    p = params or DEFAULT_PRICING
    cands = (await session.execute(select(SupplyCandidate).where(
        SupplyCandidate.task_id == task_id, SupplyCandidate.status.in_(("adopted", "auto_adopted"))
    ))).scalars().all()
    built = blocked = skipped = 0
    for c in cands:
        exists = (await session.execute(select(ListingDraft.id).where(
            ListingDraft.task_id == task_id, ListingDraft.candidate_id == c.id))).scalar_one_or_none()
        if exists:
            skipped += 1
            continue
        ozon = (await session.execute(select(OzonProduct).where(OzonProduct.id == c.ozon_product_id))).scalar_one()
        pr = price_candidate(float(c.price) if c.price is not None else 0.0, ozon.weight, p)
        status = "below_min" if pr.blocked else "draft"
        if pr.blocked:
            blocked += 1
        session.add(ListingDraft(
            task_id=task_id, ozon_product_id=ozon.id, candidate_id=c.id, shop_id=shop_id, mode="follow",
            target_ozon_sku=ozon.sku, barcode=ozon.barcode, price=pr.price, currency="RUB",
            stock_qty=0, cost=pr.cost, margin=pr.margin, pricing_detail=pr.detail, status=status))
        built += 1
    return {"built": built, "blocked": blocked, "skipped": skipped}
```

- [ ] **Step 4: 运行确认通过**

Run: `ozon-listing-auto/server/.venv/bin/python -m pytest ozon-listing-auto/server/tests/test_listing_builder.py -v`
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add ozon-listing-auto/server/app/services/listing_builder.py ozon-listing-auto/server/tests/test_listing_builder.py
git commit -m "feat(m4): listing_builder 已采用候选+定价→跟卖草稿(幂等/below_min)"
```

---

### Task 5: publisher（自动确认 + 挂靠上架 follow 分支）

**Files:**
- Create: `ozon-listing-auto/server/app/workers/publisher.py`
- Modify: `ozon-listing-auto/server/app/workers/arq_worker.py`(注册 run_publish)
- Create: `ozon-listing-auto/server/tests/test_publisher.py`

**Interfaces:**
- Consumes: `get_ozon_seller`, `Shop`/`ListingDraft`/`CollectTask` 模型, `crypto.decrypt`。
- Produces:
  - `async apply_auto_confirm(session, task_id) -> dict`（读 task.review_config；`listing_review_required=false` 时 status='draft' 且(listing_score_min 空或候选 score_total≥min)的草稿→status='confirmed'；返回 `{confirmed}`）。
  - `async confirm_draft(session, draft_id) -> dict`（draft→confirmed）。
  - `async run_publish_core(session_factory, task_id, *, seller, max_drafts=None, progress_cb=None) -> dict`（对 status='confirmed' 草稿取 shop 凭据解密→`seller.create_follow_offer`→回写 ozon_result+status(published/failed)+error；返回 `{published, failed}`）。
  - `async run_publish(ctx, task_id)`：ARQ 入口(默认 mock seller)。

- [ ] **Step 1: 写失败测试 `tests/test_publisher.py`**

```python
import json
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
from app.workers.publisher import apply_auto_confirm, run_publish_core, confirm_draft
from app.services.ozon_seller.mock import MockOzonSeller
from app.core.crypto import encrypt
from app.models import CollectTask, OzonProduct, SupplyCandidate, ListingDraft, Shop

async def _seed(sm, review_config, draft_status="draft", score=90.0):
    async with sm() as s:
        t = CollectTask(name="t", entry_type="keyword", entry_value="x", provider="mock",
                        source_platforms=["ali1688"], review_config=review_config)
        s.add(t); await s.flush()
        p = OzonProduct(task_id=t.id, sku="OZSKU1", title="phone", barcode="460")
        s.add(p); await s.flush()
        c = SupplyCandidate(task_id=t.id, ozon_product_id=p.id, platform="ali1688", offer_id="A1",
                            status="adopted", score_total=score)
        s.add(c); await s.flush()
        shop = Shop(name="店", client_id="C", api_key_encrypted=encrypt("SECRET"))
        s.add(shop); await s.flush()
        d = ListingDraft(task_id=t.id, ozon_product_id=p.id, candidate_id=c.id, shop_id=shop.id,
                         mode="follow", target_ozon_sku="OZSKU1", barcode="460", price=1290.0, stock_qty=5,
                         status=draft_status)
        s.add(d); await s.commit()
        return t.id, d.id

@pytest.mark.asyncio
async def test_auto_confirm_when_listing_review_off(engine):
    sm = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    tid, did = await _seed(sm, {"listing_review_required": False, "listing_score_min": 85})
    async with sm() as s:
        r = await apply_auto_confirm(s, tid); await s.commit()
    assert r["confirmed"] == 1
    async with sm() as s:
        d = (await s.execute(select(ListingDraft).where(ListingDraft.id == did))).scalar_one()
    assert d.status == "confirmed"

@pytest.mark.asyncio
async def test_run_publish_mock(engine):
    sm = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    tid, did = await _seed(sm, {"listing_review_required": True}, draft_status="confirmed")
    result = await run_publish_core(sm, tid, seller=MockOzonSeller())
    async with sm() as s:
        d = (await s.execute(select(ListingDraft).where(ListingDraft.id == did))).scalar_one()
    assert result["published"] == 1
    assert d.status == "published"
    assert d.ozon_result and d.ozon_result["ozon_product_id"] == "OZ-A1"
```

- [ ] **Step 2: 运行确认失败**

Run: `ozon-listing-auto/server/.venv/bin/python -m pytest ozon-listing-auto/server/tests/test_publisher.py -v`
Expected: FAIL。

- [ ] **Step 3: 写 `workers/publisher.py`**

```python
"""跟卖上架 worker(follow 分支)：自动确认 + 确认草稿挂靠→回写(§5.9)。M4 直接挂靠, 无节奏。"""
import json
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
from app.core.logging import get_logger
from app.core.crypto import decrypt
from app.services.ozon_seller.factory import get_ozon_seller
from app.models import CollectTask, SupplyCandidate, ListingDraft, Shop

async def apply_auto_confirm(session: AsyncSession, task_id: int) -> dict:
    task = (await session.execute(select(CollectTask).where(CollectTask.id == task_id))).scalar_one()
    rc = task.review_config or {}
    if rc.get("listing_review_required", True):
        return {"confirmed": 0}
    smin = rc.get("listing_score_min")
    drafts = (await session.execute(select(ListingDraft).where(
        ListingDraft.task_id == task_id, ListingDraft.status == "draft"))).scalars().all()
    n = 0
    for d in drafts:
        if smin is not None:
            cand = (await session.execute(select(SupplyCandidate).where(SupplyCandidate.id == d.candidate_id))).scalar_one()
            if cand.score_total is None or float(cand.score_total) < smin:
                continue
        d.status = "confirmed"
        n += 1
    return {"confirmed": n}

async def confirm_draft(session: AsyncSession, draft_id: int) -> dict:
    d = (await session.execute(select(ListingDraft).where(ListingDraft.id == draft_id))).scalar_one()
    if d.status in ("draft",):
        d.status = "confirmed"
    return {"draft_id": draft_id, "status": d.status}

async def run_publish_core(session_factory: async_sessionmaker, task_id: int, *, seller,
                           max_drafts=None, progress_cb=None) -> dict:
    log = get_logger(task_id=task_id, phase="publish")
    published = failed = 0
    async with session_factory() as s:
        drafts = (await s.execute(select(ListingDraft).where(
            ListingDraft.task_id == task_id, ListingDraft.status == "confirmed"))).scalars().all()
        draft_ids = [d.id for d in drafts]
    for i, did in enumerate(draft_ids):
        if max_drafts is not None and i >= max_drafts:
            break
        async with session_factory() as s:
            d = (await s.execute(select(ListingDraft).where(ListingDraft.id == did))).scalar_one()
            shop = (await s.execute(select(Shop).where(Shop.id == d.shop_id))).scalar_one_or_none() if d.shop_id else None
            client_id = shop.client_id if shop else ""
            api_key = decrypt(shop.api_key_encrypted) if shop else ""
            try:
                res = await seller.create_follow_offer(
                    client_id=client_id, api_key=api_key, target_sku=d.target_ozon_sku, barcode=d.barcode,
                    price=float(d.price) if d.price is not None else 0.0, stock=d.stock_qty,
                    offer_id=str((await s.execute(select(SupplyCandidate.offer_id).where(SupplyCandidate.id == d.candidate_id))).scalar_one()))
                if res.ok:
                    d.status = "published"; d.ozon_result = {"ozon_product_id": res.ozon_product_id, "status": res.status}
                    published += 1
                else:
                    d.status = "failed"; d.error = res.error; failed += 1
            except Exception as exc:  # noqa: BLE001
                log.error("publish_failed", draft_id=did, error=str(exc))
                d.status = "failed"; d.error = str(exc); failed += 1
            await s.commit()
        if progress_cb:
            await progress_cb({"task_id": task_id, "draft_id": did, "published": published, "failed": failed})
    return {"published": published, "failed": failed}

async def run_publish(ctx, task_id: int) -> dict:
    from app.core.db import async_session
    return await run_publish_core(async_session, task_id, seller=get_ozon_seller("mock"))
```

- [ ] **Step 4: 注册 ARQ `run_publish`**

改 `arq_worker.py` functions：
```python
from app.workers.collector import run_collect
from app.workers.matcher import run_match
from app.workers.scorer import run_score
from app.workers.publisher import run_publish
class WorkerSettings:
    functions = [run_collect, run_match, run_score, run_publish]
    ...
```

- [ ] **Step 5: 运行确认通过 + 全套回归**

Run: `ozon-listing-auto/server/.venv/bin/python -m pytest ozon-listing-auto/server/tests -q`
Expected: PASS(0 warnings)。

- [ ] **Step 6: 提交**

```bash
git add ozon-listing-auto/server/app/workers/publisher.py ozon-listing-auto/server/app/workers/arq_worker.py ozon-listing-auto/server/tests/test_publisher.py
git commit -m "feat(m4): publisher(自动确认+确认草稿 mock 挂靠→回写 Ozon 商品ID)"
```

---

## 阶段 2 · API

### Task 6: 店铺 CRUD API + 定价设置

**Files:**
- Create: `ozon-listing-auto/server/app/schemas/shop.py`
- Create: `ozon-listing-auto/server/app/api/shops.py`
- Modify: `ozon-listing-auto/server/app/main.py`
- Create: `ozon-listing-auto/server/tests/test_shops_api.py`

**Interfaces:**
- Produces（均 admin）：`POST /shops`(body {name, client_id, api_key, is_sandbox?} → api_key Fernet 加密); `GET /shops`(ShopOut 无 api_key); `PUT /shops/{id}`; `DELETE /shops/{id}`。`ShopOut`: id/name/platform/client_id/is_active/is_sandbox/created_at(无 api_key)。
- 定价设置复用现有 `/settings/{category}`(category='pricing') — 无需新代码。

- [ ] **Step 1: 写失败测试 `tests/test_shops_api.py`**

```python
import pytest
from app.core.security import hash_password
from app.models import User

async def _admin(client, db_session):
    db_session.add(User(username="a", password_hash=hash_password("p"), role="admin"))
    await db_session.commit()
    tok = (await client.post("/auth/login", data={"username": "a", "password": "p"})).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}

@pytest.mark.asyncio
async def test_create_list_shop_no_key_leak(client, db_session):
    h = await _admin(client, db_session)
    r = await client.post("/shops", json={"name": "测试店", "client_id": "CID", "api_key": "SECRETKEY", "is_sandbox": True}, headers=h)
    assert r.status_code == 201
    assert "api_key" not in r.json() and "SECRETKEY" not in str(r.json())
    lst = await client.get("/shops", headers=h)
    assert lst.status_code == 200 and lst.json()[0]["client_id"] == "CID"
    assert "api_key" not in str(lst.json())

@pytest.mark.asyncio
async def test_shop_requires_admin(client, db_session):
    from app.core.security import hash_password
    from app.models import User
    db_session.add(User(username="op", password_hash=hash_password("p"), role="operator"))
    await db_session.commit()
    tok = (await client.post("/auth/login", data={"username": "op", "password": "p"})).json()["access_token"]
    r = await client.post("/shops", json={"name": "x", "client_id": "c", "api_key": "k"},
                          headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 403
```

- [ ] **Step 2: 运行确认失败**

Run: `ozon-listing-auto/server/.venv/bin/python -m pytest ozon-listing-auto/server/tests/test_shops_api.py -v`
Expected: FAIL。

- [ ] **Step 3: 写 `schemas/shop.py`**

```python
"""店铺 API schema(响应不含 api_key)。"""
from datetime import datetime
from pydantic import BaseModel, ConfigDict

class ShopCreate(BaseModel):
    name: str
    client_id: str
    api_key: str
    is_sandbox: bool = True

class ShopUpdate(BaseModel):
    name: str | None = None
    client_id: str | None = None
    api_key: str | None = None
    is_active: bool | None = None
    is_sandbox: bool | None = None

class ShopOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    platform: str
    client_id: str
    is_active: bool
    is_sandbox: bool
    created_at: datetime
```

- [ ] **Step 4: 写 `api/shops.py`**

```python
"""店铺凭据 CRUD(admin)：api_key Fernet 加密, 响应脱敏。"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.db import get_session
from app.core.crypto import encrypt
from app.api.deps import require_role
from app.models import Shop, User
from app.schemas.shop import ShopCreate, ShopUpdate, ShopOut

router = APIRouter(prefix="/shops", tags=["shops"])

@router.post("", response_model=ShopOut, status_code=201)
async def create_shop(body: ShopCreate, s: AsyncSession = Depends(get_session), _: User = Depends(require_role("admin"))):
    shop = Shop(name=body.name, client_id=body.client_id, api_key_encrypted=encrypt(body.api_key), is_sandbox=body.is_sandbox)
    s.add(shop); await s.commit(); await s.refresh(shop)
    return shop

@router.get("", response_model=list[ShopOut])
async def list_shops(s: AsyncSession = Depends(get_session), _: User = Depends(require_role("admin"))):
    return list((await s.execute(select(Shop).order_by(Shop.id.desc()))).scalars().all())

@router.put("/{shop_id}", response_model=ShopOut)
async def update_shop(shop_id: int, body: ShopUpdate, s: AsyncSession = Depends(get_session), _: User = Depends(require_role("admin"))):
    shop = (await s.execute(select(Shop).where(Shop.id == shop_id))).scalar_one_or_none()
    if not shop:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "店铺不存在")
    for f in ("name", "client_id", "is_active", "is_sandbox"):
        v = getattr(body, f)
        if v is not None:
            setattr(shop, f, v)
    if body.api_key is not None:
        shop.api_key_encrypted = encrypt(body.api_key)
    await s.commit(); await s.refresh(shop)
    return shop

@router.delete("/{shop_id}", status_code=204)
async def delete_shop(shop_id: int, s: AsyncSession = Depends(get_session), _: User = Depends(require_role("admin"))):
    shop = (await s.execute(select(Shop).where(Shop.id == shop_id))).scalar_one_or_none()
    if shop:
        await s.delete(shop); await s.commit()
```

- [ ] **Step 5: 挂路由 `main.py`**

```python
from app.api.shops import router as shops_router
app.include_router(shops_router)
```

- [ ] **Step 6: 运行确认通过**

Run: `ozon-listing-auto/server/.venv/bin/python -m pytest ozon-listing-auto/server/tests/test_shops_api.py -v`
Expected: PASS。

- [ ] **Step 7: 提交**

```bash
git add ozon-listing-auto/server/app/schemas/shop.py ozon-listing-auto/server/app/api/shops.py ozon-listing-auto/server/app/main.py ozon-listing-auto/server/tests/test_shops_api.py
git commit -m "feat(m4): 店铺凭据 CRUD API(admin, api_key 加密/脱敏)"
```

---

### Task 7: 上架 API(build/drafts/confirm/auto-confirm/publish/monitor)

**Files:**
- Create: `ozon-listing-auto/server/app/schemas/listing.py`
- Create: `ozon-listing-auto/server/app/api/listing.py`
- Modify: `ozon-listing-auto/server/app/main.py`
- Create: `ozon-listing-auto/server/tests/test_listing_api.py`

**Interfaces:**
- Produces:
  - `POST /listing/build?task_id=&shop_id=`(operator+; 读 app_settings.pricing 参数或默认 → build_follow_drafts)。
  - `GET /listing/drafts?task_id=&status=`(认证; 返回 DraftOut 列表: 进价/售价/毛利率/目标卡/tier/状态)。
  - `POST /listing/{draft_id}/confirm`(reviewer+; confirm_draft)。
  - `POST /listing/auto-confirm?task_id=`(operator+; apply_auto_confirm)。
  - `POST /listing/publish?task_id=&sync=false`(publisher+; sync=true 用 mock seller + dbmod.async_session)。
  - `GET /listing/monitor?task_id=`(认证; 各 status 计数)。
- `DraftOut`: id/task_id/ozon_product_id/candidate_id/target_ozon_sku/platform?/price/cost/margin/currency/stock_qty/status/ozon_result。

- [ ] **Step 1: 写失败测试 `tests/test_listing_api.py`**

```python
import pytest
from sqlalchemy import select
from app.core.security import hash_password
from app.models import User, CollectTask, OzonProduct, SupplyCandidate, Shop, ListingDraft
from app.core.crypto import encrypt

async def _seed_login(client, db_session, role="publisher"):
    db_session.add(User(username="u", password_hash=hash_password("p"), role=role))
    t = CollectTask(name="t", entry_type="keyword", entry_value="x", provider="mock", source_platforms=["ali1688"],
                    review_config={"listing_review_required": True})
    db_session.add(t); await db_session.flush()
    p = OzonProduct(task_id=t.id, sku="OZSKU1", title="phone", barcode="460")
    db_session.add(p); await db_session.flush()
    db_session.add(SupplyCandidate(task_id=t.id, ozon_product_id=p.id, platform="ali1688", offer_id="A1",
                                   price=15.0, status="adopted", score_total=90.0))
    shop = Shop(name="店", client_id="C", api_key_encrypted=encrypt("K"))
    db_session.add(shop); await db_session.commit()
    tok = (await client.post("/auth/login", data={"username": "u", "password": "p"})).json()["access_token"]
    return t.id, shop.id, {"Authorization": f"Bearer {tok}"}

**说明**：build 需 operator+、confirm 需 reviewer+、publish 需 publisher+；单账号跨这三个角色最简单是用 **admin**（`require_role` 里 admin 超级通过所有角色）。因此 `_seed_login` 用 `role="admin"`（上面 `_seed_login` 默认 publisher，测试显式传 admin）。完整链路测试：

```python
@pytest.mark.asyncio
async def test_build_confirm_publish_flow(client, db_session):
    tid, sid, h = await _seed_login(client, db_session, role="admin")
    b = await client.post(f"/listing/build?task_id={tid}&shop_id={sid}", headers=h)
    assert b.status_code == 200 and b.json()["built"] == 1
    drafts = await client.get(f"/listing/drafts?task_id={tid}", headers=h)
    assert drafts.json()[0]["status"] == "draft" and drafts.json()[0]["price"] is not None
    did = drafts.json()[0]["id"]
    c = await client.post(f"/listing/{did}/confirm", headers=h)
    assert c.json()["status"] == "confirmed"
    pub = await client.post(f"/listing/publish?task_id={tid}&sync=true", headers=h)
    assert pub.status_code == 200 and pub.json()["published"] == 1
    d2 = await client.get(f"/listing/drafts?task_id={tid}&status=published", headers=h)
    assert d2.json()[0]["ozon_result"]["ozon_product_id"] == "OZ-A1"
```

- [ ] **Step 2: 运行确认失败**

Run: `ozon-listing-auto/server/.venv/bin/python -m pytest ozon-listing-auto/server/tests/test_listing_api.py -v`
Expected: FAIL。

- [ ] **Step 3: 写 `schemas/listing.py`**

```python
"""上架草稿 API schema。"""
from pydantic import BaseModel, ConfigDict

class DraftOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    task_id: int
    ozon_product_id: int
    candidate_id: int
    target_ozon_sku: str | None
    barcode: str | None
    price: float | None
    cost: float | None
    margin: float | None
    currency: str
    stock_qty: int
    status: str
    ozon_result: dict | None
```
注意：`price`/`cost`/`margin` 是 Numeric→Decimal；Pydantic v2 `float` 字段能从 Decimal 转，但为稳妥在 DraftOut 用 `float | None` 且确认序列化正常（Decimal→float）。若报错，字段改 `Decimal | None` 或在查询处转 float。

- [ ] **Step 4: 写 `api/listing.py`**

```python
"""上架 API：生成草稿/列表/确认/自动确认/挂靠/监控。"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
import app.core.db as dbmod
from app.core.db import get_session
from app.api.deps import require_role, get_current_user
from app.models import CollectTask, ListingDraft, User
from app.schemas.listing import DraftOut
from app.services.listing_builder import build_follow_drafts
from app.services.pricing import DEFAULT_PRICING
from app.services.settings_store import get_category
from app.workers.publisher import apply_auto_confirm, confirm_draft, run_publish_core
from app.services.ozon_seller.factory import get_ozon_seller

router = APIRouter(prefix="/listing", tags=["listing"])

async def _pricing_params(s: AsyncSession) -> dict:
    stored = await get_category(s, "pricing")
    params = {**DEFAULT_PRICING}
    for k, v in stored.items():   # 存的是字符串, 数值字段转 float
        if k in ("mode", "formula"):
            params[k] = v
        else:
            try: params[k] = float(v)
            except (TypeError, ValueError): pass
    return params

@router.post("/build")
async def listing_build(task_id: int, shop_id: int | None = None, s: AsyncSession = Depends(get_session), _: User = Depends(require_role("operator"))):
    t = (await s.execute(select(CollectTask).where(CollectTask.id == task_id))).scalar_one_or_none()
    if not t:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "任务不存在")
    params = await _pricing_params(s)
    r = await build_follow_drafts(s, task_id, params=params, shop_id=shop_id); await s.commit()
    return r

@router.get("/drafts", response_model=list[DraftOut])
async def listing_drafts(task_id: int, status: str | None = None, s: AsyncSession = Depends(get_session), _: User = Depends(get_current_user)):
    conds = [ListingDraft.task_id == task_id]
    if status:
        conds.append(ListingDraft.status == status)
    rows = (await s.execute(select(ListingDraft).where(*conds).order_by(ListingDraft.id.desc()))).scalars().all()
    return [DraftOut.model_validate(r) for r in rows]

@router.post("/{draft_id}/confirm")
async def listing_confirm(draft_id: int, s: AsyncSession = Depends(get_session), _: User = Depends(require_role("reviewer"))):
    d = (await s.execute(select(ListingDraft).where(ListingDraft.id == draft_id))).scalar_one_or_none()
    if not d:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "草稿不存在")
    r = await confirm_draft(s, draft_id); await s.commit()
    return r

@router.post("/auto-confirm")
async def listing_auto_confirm(task_id: int, s: AsyncSession = Depends(get_session), _: User = Depends(require_role("operator"))):
    t = (await s.execute(select(CollectTask).where(CollectTask.id == task_id))).scalar_one_or_none()
    if not t:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "任务不存在")
    r = await apply_auto_confirm(s, task_id); await s.commit()
    return r

@router.post("/publish")
async def listing_publish(task_id: int, sync: bool = False, s: AsyncSession = Depends(get_session), _: User = Depends(require_role("publisher"))):
    t = (await s.execute(select(CollectTask).where(CollectTask.id == task_id))).scalar_one_or_none()
    if not t:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "任务不存在")
    if sync:
        r = await run_publish_core(dbmod.async_session, task_id, seller=get_ozon_seller("mock"))
        return r
    from arq import create_pool
    from arq.connections import RedisSettings
    from app.core.config import settings
    pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    try:
        await pool.enqueue_job("run_publish", task_id)
    finally:
        await pool.aclose()
    return {"status": "queued"}

@router.get("/monitor")
async def listing_monitor(task_id: int, s: AsyncSession = Depends(get_session), _: User = Depends(get_current_user)):
    rows = (await s.execute(select(ListingDraft.status, func.count()).where(
        ListingDraft.task_id == task_id).group_by(ListingDraft.status))).all()
    return {"counts": {status_: cnt for status_, cnt in rows}}
```

- [ ] **Step 5: 挂路由 `main.py`**

```python
from app.api.listing import router as listing_router
app.include_router(listing_router)
```

- [ ] **Step 6: 运行确认通过 + 全套回归**

Run: `ozon-listing-auto/server/.venv/bin/python -m pytest ozon-listing-auto/server/tests -q`
Expected: PASS(0 warnings)。

- [ ] **Step 7: 提交**

```bash
git add ozon-listing-auto/server/app/schemas/listing.py ozon-listing-auto/server/app/api/listing.py ozon-listing-auto/server/app/main.py ozon-listing-auto/server/tests/test_listing_api.py
git commit -m "feat(m4): 上架 API(build/drafts/confirm/auto-confirm/publish/monitor)"
```

---

## 阶段 3 · 前端 + 文档

### Task 8: 前端 ListingReview + Shops + 定价设置

**Files:**
- Create: `ozon-listing-auto/web/src/api/listing.ts`
- Create: `ozon-listing-auto/web/src/api/shops.ts`
- Create: `ozon-listing-auto/web/src/pages/ListingReview.tsx`
- Create: `ozon-listing-auto/web/src/pages/Shops.tsx`
- Modify: `ozon-listing-auto/web/src/App.tsx`(加 /listing /shops 路由)
- Modify: `ozon-listing-auto/web/src/pages/Layout.tsx`(加菜单)
- Create: `ozon-listing-auto/web/src/pages/ListingReview.test.tsx`

**Interfaces:**
- Produces: `api/listing.ts`(build/getDrafts/confirm/autoConfirm/publish); `api/shops.ts`(listShops/createShop/deleteShop); ListingReview 页(选任务+店铺→生成草稿→草稿表[目标卡/进价/售价/毛利率/状态]→确认/挂靠); Shops 页(列表+新增+删除)。

- [ ] **Step 1: 写 `api/listing.ts` 与 `api/shops.ts`**

`api/listing.ts`:
```ts
import { api } from "./client";
export const buildDrafts = (taskId: number, shopId?: number) =>
  api.post(`/listing/build?task_id=${taskId}${shopId ? `&shop_id=${shopId}` : ""}`).then(r => r.data);
export const getDrafts = (taskId: number, status?: string) =>
  api.get(`/listing/drafts?task_id=${taskId}${status ? `&status=${status}` : ""}`).then(r => r.data);
export const confirmDraft = (draftId: number) => api.post(`/listing/${draftId}/confirm`).then(r => r.data);
export const autoConfirm = (taskId: number) => api.post(`/listing/auto-confirm?task_id=${taskId}`).then(r => r.data);
export const publishDrafts = (taskId: number) => api.post(`/listing/publish?task_id=${taskId}&sync=true`).then(r => r.data);
```

`api/shops.ts`:
```ts
import { api } from "./client";
export const listShops = () => api.get("/shops").then(r => r.data);
export const createShop = (body: { name: string; client_id: string; api_key: string; is_sandbox: boolean }) =>
  api.post("/shops", body).then(r => r.data);
export const deleteShop = (id: number) => api.delete(`/shops/${id}`).then(r => r.data);
```

- [ ] **Step 2: 写 `pages/ListingReview.tsx`**

```tsx
import { useState } from "react";
import { Card, InputNumber, Select, Button, Table, Space, Tag, message } from "antd";
import { buildDrafts, getDrafts, confirmDraft, autoConfirm, publishDrafts } from "../api/listing";
import { listShops } from "../api/shops";
import { useEffect } from "react";

const ST: Record<string, string> = { draft: "default", confirmed: "blue", published: "green", failed: "red", below_min: "orange" };

export default function ListingReview() {
  const [taskId, setTaskId] = useState<number>();
  const [shopId, setShopId] = useState<number>();
  const [shops, setShops] = useState<any[]>([]);
  const [rows, setRows] = useState<any[]>([]);
  useEffect(() => { listShops().then(setShops).catch(() => {}); }, []);
  const load = async () => { if (!taskId) { message.warning("请先输入任务ID"); return; } setRows(await getDrafts(taskId)); };
  const onBuild = async () => { if (!taskId) return; const r = await buildDrafts(taskId, shopId); message.success(`生成 ${r.built} 条(拦截 ${r.blocked})`); load(); };
  const onConfirm = async (id: number) => { await confirmDraft(id); message.success("已确认"); load(); };
  const onAuto = async () => { if (!taskId) return; const r = await autoConfirm(taskId); message.success(`自动确认 ${r.confirmed} 条`); load(); };
  const onPublish = async () => { if (!taskId) return; const r = await publishDrafts(taskId); message.success(`挂靠 ${r.published} 条(失败 ${r.failed})`); load(); };

  return (
    <Space direction="vertical" style={{ width: "100%" }} size="large">
      <Card title="上架审核(跟卖草稿)">
        <Space wrap>
          任务ID <InputNumber onChange={(v) => setTaskId(v as number)} />
          店铺 <Select style={{ width: 180 }} allowClear onChange={(v) => setShopId(v)}
            options={shops.map((s) => ({ value: s.id, label: `${s.name}${s.is_sandbox ? "(沙箱)" : ""}` }))} />
          <Button type="primary" onClick={onBuild}>生成草稿</Button>
          <Button onClick={load}>刷新</Button>
          <Button onClick={onAuto}>按开关自动确认</Button>
          <Button danger onClick={onPublish}>挂靠上架</Button>
        </Space>
      </Card>
      <Card title="草稿列表">
        <Table rowKey="id" dataSource={rows} pagination={false}
          columns={[
            { title: "目标卡 SKU", dataIndex: "target_ozon_sku" },
            { title: "进价(到手)", dataIndex: "cost" },
            { title: "售价 RUB", dataIndex: "price" },
            { title: "毛利率", dataIndex: "margin", render: (m) => (m != null ? `${(m * 100).toFixed(1)}%` : "-") },
            { title: "库存", dataIndex: "stock_qty" },
            { title: "状态", dataIndex: "status", render: (s) => <Tag color={ST[s]}>{s}</Tag> },
            { title: "Ozon结果", dataIndex: "ozon_result", render: (r) => r?.ozon_product_id ?? "-" },
            { title: "操作", render: (_, r) => r.status === "draft"
                ? <Button size="small" onClick={() => onConfirm(r.id)}>确认</Button> : null },
          ]} />
      </Card>
    </Space>
  );
}
```

- [ ] **Step 3: 写 `pages/Shops.tsx`**

```tsx
import { useEffect, useState } from "react";
import { Card, Form, Input, Switch, Button, Table, Space, message, Popconfirm } from "antd";
import { listShops, createShop, deleteShop } from "../api/shops";

export default function Shops() {
  const [rows, setRows] = useState<any[]>([]);
  const [form] = Form.useForm();
  const load = () => listShops().then(setRows);
  useEffect(() => { load(); }, []);
  const onCreate = async (v: any) => {
    await createShop({ name: v.name, client_id: v.client_id, api_key: v.api_key, is_sandbox: v.is_sandbox ?? true });
    message.success("已添加店铺"); form.resetFields(); load(); };
  const onDelete = async (id: number) => { await deleteShop(id); message.success("已删除"); load(); };
  return (
    <Space direction="vertical" style={{ width: "100%" }} size="large">
      <Card title="新增 Ozon 店铺">
        <Form form={form} layout="inline" onFinish={onCreate} initialValues={{ is_sandbox: true }}>
          <Form.Item name="name" rules={[{ required: true }]}><Input placeholder="店铺名" /></Form.Item>
          <Form.Item name="client_id" rules={[{ required: true }]}><Input placeholder="Client-Id" /></Form.Item>
          <Form.Item name="api_key" rules={[{ required: true }]}><Input.Password placeholder="Api-Key" /></Form.Item>
          <Form.Item name="is_sandbox" label="沙箱" valuePropName="checked"><Switch /></Form.Item>
          <Button type="primary" htmlType="submit">添加</Button>
        </Form>
      </Card>
      <Card title="店铺列表">
        <Table rowKey="id" dataSource={rows} pagination={false}
          columns={[
            { title: "名称", dataIndex: "name" }, { title: "Client-Id", dataIndex: "client_id" },
            { title: "沙箱", dataIndex: "is_sandbox", render: (b) => (b ? "是" : "否") },
            { title: "启用", dataIndex: "is_active", render: (b) => (b ? "是" : "否") },
            { title: "操作", render: (_, r) => <Popconfirm title="删除?" onConfirm={() => onDelete(r.id)}><Button danger size="small">删除</Button></Popconfirm> },
          ]} />
      </Card>
    </Space>
  );
}
```

- [ ] **Step 4: 加路由与菜单**

`App.tsx` 受保护路由内加：
```tsx
import ListingReview from "./pages/ListingReview";
import Shops from "./pages/Shops";
// <Route path="/listing" element={<ListingReview />} />
// <Route path="/shops" element={<Shops />} />
```
`Layout.tsx` 菜单 items 加：`{ key: "listing", label: "上架审核" }, { key: "shops", label: "店铺管理" }`。

- [ ] **Step 5: 写测试 `pages/ListingReview.test.tsx`**

```tsx
import { render, screen } from "@testing-library/react";
import { vi } from "vitest";
vi.mock("../api/listing", () => ({
  buildDrafts: vi.fn(), getDrafts: vi.fn(() => Promise.resolve([])), confirmDraft: vi.fn(),
  autoConfirm: vi.fn(), publishDrafts: vi.fn(),
}));
vi.mock("../api/shops", () => ({ listShops: vi.fn(() => Promise.resolve([])) }));
import ListingReview from "./ListingReview";

test("渲染上架审核页", () => {
  render(<ListingReview />);
  expect(screen.getByText("上架审核(跟卖草稿)")).toBeInTheDocument();
  expect(screen.getByText("生成草稿")).toBeInTheDocument();
});
```

- [ ] **Step 6: 运行前端测试 + build**

Run: `cd ozon-listing-auto/web && npx vitest run && npm run build`
Expected: 所有前端测试通过(Login/Tasks/Products/ReviewBoard/ListingReview)；`npm run build` 成功。

- [ ] **Step 7: 提交**

```bash
git add ozon-listing-auto/web/src/api/listing.ts ozon-listing-auto/web/src/api/shops.ts ozon-listing-auto/web/src/pages/ListingReview.tsx ozon-listing-auto/web/src/pages/Shops.tsx ozon-listing-auto/web/src/pages/ListingReview.test.tsx ozon-listing-auto/web/src/App.tsx ozon-listing-auto/web/src/pages/Layout.tsx
git commit -m "feat(m4): 前端 ListingReview(草稿确认/挂靠)+店铺管理"
```

---

### Task 9: README/docs M4 + 全量回归

**Files:**
- Modify: `ozon-listing-auto/README.md`
- Create: `ozon-listing-auto/docs/M4-定价上架说明.md`

**Interfaces:**
- Produces: README M4 段 + M4 使用说明。

- [ ] **Step 1: 更新 `README.md` M4 段**

加 M4 功能：跟卖定价(内置反推+simpleeval 自定义公式+最低价保护, 参数 settings/pricing)、Ozon 写入抽象(mock/real, real live 跳过)、草稿生成/确认闸门/自动确认、挂靠上架(mock seller 回写 Ozon 商品ID)、店铺凭据管理、上架 API + ListingReview/Shops 前端。更新里程碑状态(M1-M4 done)。

- [ ] **Step 2: 写 `docs/M4-定价上架说明.md`**

流程：建店铺(/shops, api_key 加密)→配定价参数(/settings/pricing)→采集→匹配→评分→审核采用→/listing/build(定价生成草稿)→草稿确认(人工或自动)→/listing/publish(mock 挂靠, 回写 Ozon 商品ID)→切真实(配 shops 真实凭据 + ozon_seller=real, RealOzonSeller live 联调)。注明 M4 直接挂靠、节奏调度在 M5。

- [ ] **Step 3: 全量回归**

Run: `cd ozon-listing-auto/server && .venv/bin/python -m pytest -q && cd ../web && npx vitest run && npm run build`
Expected: 后端全绿(非 live, 0 warnings)；前端全绿 + build 成功。

- [ ] **Step 4: 提交**

```bash
git add ozon-listing-auto/README.md ozon-listing-auto/docs/M4-定价上架说明.md
git commit -m "docs: README + M4 定价上架说明"
```

---

## 验收对照（spec §8）

| 验收项 | 覆盖任务 |
|---|---|
| 迁移 0004(shops/listing_drafts/ozon_products.barcode) | Task 1 |
| 建店铺(加密/脱敏) + 定价参数 | Task 6 |
| 采集→…→采用→build→草稿有进价/售价/毛利率 + 最低价拦截 | Task 2,4,7 |
| 草稿确认(人工闸门+自动确认) + publish(mock)→published+回写 Ozon 商品ID | Task 3,5,7 |
| 前端 ListingReview(确认/挂靠)+定价设置+店铺管理 | Task 8 |
| MockOzonSeller 全链路 + RealOzonSeller 配置切换 + live 跳过 | Task 3,5 |
| 非 live 0 warnings + README/docs + 前端 build | Task 9 |

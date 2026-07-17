# M2 货源匹配实现计划（1688 + 拼多多 + 账号池 + CLIP 去重）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 纯后端货源匹配管线：Ozon 商品 → 遍历启用平台(1688/拼多多) → 图搜+关键词 → CLIP 向量化 → 跨平台去重 → 落 `supply_candidates`；配 cookie 账号池 + 独立限速/冷却/换号。验收「100 SKU 出双平台候选」。

**Architecture:** 沿用 M1 的抽象+工厂+mock-first。新增 `SourceProvider`（mock/ali1688/pinduoduo）与 `Embedder`（mock/clip）两个配置驱动的家族；CLIP 仅 worker 用。matcher worker 结构镜像 M1 collector（断点续传/暂停/失败）。测试全走 mock（无 torch/网络）。

**Tech Stack:** 承接 M1（FastAPI async / SQLAlchemy 2 / Alembic / ARQ / Postgres+pgvector / Redis）。新增 `pgvector`(python, 基础依赖) 用于 `Vector` 列；可选组 `[ml]=torch(cpu)+cn_clip+pillow`（仅 worker）。真实 provider：1688 httpx+cookie、拼多多 selenium/playwright+代理（均 `@pytest.mark.live` 默认跳过）。

## Global Constraints

- Python 3.11；后端全异步；worker 幂等；断点续传（`match_cursor`）。
- provider 平台枚举：`ali1688` / `pinduoduo`。embedder 名枚举：`mock` / `clip`（默认 mock）。
- 跨平台去重：同一 Ozon 商品候选集内，CLIP 余弦相似度 > `sim_threshold`(默认 0.92, 可配) 折叠为一簇、保留代表；跨平台不同款各成簇都保留。
- 账号 = Fernet 加密 cookie/会话；限速账号级：`min_interval_sec`(默认6) / `daily_limit`(默认200) / 冷却换号；风控不中断任务。
- CLIP 向量 512 维（常量 `EMBED_DIM=512`，MockEmbedder 同维）。
- 拼多多真实实现走 selenium/playwright+代理截流（不逆向 anti_content），**一期先 keyword_search，image_search 占位**；拼多多不稳时任务仅用 1688 完成不阻塞。
- 敏感信息 Fernet 加密，绝不硬编码；structlog 带 task_id；中文注释/每模块一行中文 docstring。
- TDD：每单元先写失败测试；`pytest` 保持 0 warnings；测试全走 mock（无 torch/网络/真实 Redis）。
- 代码库：`ozon-listing-auto/`；venv `ozon-listing-auto/server/.venv`（Python 3.11，`~/.local/bin/python3.11`）；跑测试用 `ozon-listing-auto/server/.venv/bin/python -m pytest`（勿用系统 python3=3.9）。
- 建立在 M1 之上：复用 `core/crypto`(Fernet)、`core/db`、`api/deps`(require_role/get_current_user)、`core/progress`(Broadcaster)、`settings_store`、conftest fixtures、`OzonProduct`/`CollectTask` 模型、`ingest.dedup` 模式、collector 的 §4.2.6 failed 处理范式。

## 文件结构

```
server/app/
├── models/{source_account.py, supply_candidate.py}        # 新增 ORM
├── models/collect_task.py                                  # 增 match_status/match_cursor/match_stats
├── alembic/versions/0002_m2_source_matching.py
├── schemas/{account.py, candidate.py}
├── api/{accounts.py, match.py, candidates.py}
├── services/
│   ├── sources/{base.py, mock.py, ali1688.py, pinduoduo.py, parser_ali.py, factory.py}
│   ├── embedding/{base.py, mock.py, clip.py, factory.py}
│   ├── account_pool.py
│   └── candidate_ingest.py
├── fixtures/source_mock.json
└── workers/{matcher.py, arq_worker.py(增 run_match)}
server/tests/{test_source_models.py, test_source_provider.py, test_mock_source.py,
              test_embedder.py, test_candidate_ingest.py, test_account_pool.py,
              test_matcher.py, test_accounts_api.py, test_match_api.py,
              test_ali_parser.py}
```

---

## 阶段 0 · Schema

### Task 1: 依赖 + 迁移 0002 + ORM 模型（source_accounts / supply_candidates / collect_tasks.match_*）

**Files:**
- Modify: `ozon-listing-auto/server/pyproject.toml`（加 `pgvector` 基础依赖 + 可选组 `[ml]`）
- Create: `ozon-listing-auto/server/app/models/source_account.py`
- Create: `ozon-listing-auto/server/app/models/supply_candidate.py`
- Modify: `ozon-listing-auto/server/app/models/collect_task.py`（加 match_* 列）
- Modify: `ozon-listing-auto/server/app/models/__init__.py`（导出新模型）
- Create: `ozon-listing-auto/server/alembic/versions/0002_m2_source_matching.py`
- Create: `ozon-listing-auto/server/tests/test_source_models.py`

**Interfaces:**
- Produces: ORM `SourceAccount`, `SupplyCandidate`（字段见 spec §3.1/§3.2）；`CollectTask.match_status/match_cursor/match_stats`；常量 `EMBED_DIM=512`（放 `supply_candidate.py`）。

**关键技术点（向量列在 SQLite 测试的兼容）：** pgvector 的 `Vector(512)` 在 SQLite `create_all` 上无法编译（同 M1 的 JSONB 问题）。用 variant：`Vector(EMBED_DIM).with_variant(sa.JSON(), "sqlite")`（Postgres 用真实 vector，SQLite 用 JSON 存 list）。M2 去重在内存按 DTO 向量算余弦，DB 向量列只做存储（M3 才在 Postgres 上做向量查询），故 SQLite 存 JSON 足够。若 `.with_variant` 对 `Vector` 不奏效，退化为自定义 `TypeDecorator`（impl=Vector on pg, JSON on sqlite）——先试 with_variant。

- [ ] **Step 1: pyproject 加依赖**

`[project].dependencies` 增加：
```toml
  "pgvector>=0.3",
```
新增可选组：
```toml
[project.optional-dependencies]
ml = ["torch>=2.2", "cn-clip>=1.5", "pillow>=10.0"]
```
（`dev` 组保持不变。）安装：`ozon-listing-auto/server/.venv/bin/pip install -e "ozon-listing-auto/server[dev]"` 以拉入 pgvector（不装 ml）。

- [ ] **Step 2: 写 `models/source_account.py`**

```python
"""货源平台账号池 ORM：加密 cookie/会话 + 限速/冷却状态。"""
from datetime import datetime, date
from sqlalchemy import String, Integer, Boolean, DateTime, Date, LargeBinary, func
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db import Base

class SourceAccount(Base):
    __tablename__ = "source_accounts"
    id: Mapped[int] = mapped_column(primary_key=True)
    platform: Mapped[str] = mapped_column(String(16), index=True)   # ali1688/pinduoduo
    label: Mapped[str | None] = mapped_column(String(128), nullable=True)
    credentials_encrypted: Mapped[bytes] = mapped_column(LargeBinary)
    status: Mapped[str] = mapped_column(String(16), default="active")  # active/cooldown/disabled
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    daily_used_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    daily_used_count: Mapped[int] = mapped_column(Integer, default=0)
    daily_limit: Mapped[int] = mapped_column(Integer, default=200)
    min_interval_sec: Mapped[int] = mapped_column(Integer, default=6)
    cooldown_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    risk_hits: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
```

- [ ] **Step 3: 写 `models/supply_candidate.py`**

```python
"""货源候选 ORM：跨平台候选 + CLIP 向量 + 去重分组。"""
from datetime import datetime
from sqlalchemy import String, Integer, Float, Boolean, DateTime, ForeignKey, UniqueConstraint, Index, func, JSON
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from pgvector.sqlalchemy import Vector
from app.core.db import Base

EMBED_DIM = 512
_JSONB = JSONB().with_variant(JSON(), "sqlite")
_VECTOR = Vector(EMBED_DIM).with_variant(JSON(), "sqlite")

class SupplyCandidate(Base):
    __tablename__ = "supply_candidates"
    __table_args__ = (
        UniqueConstraint("task_id", "ozon_product_id", "platform", "offer_id", name="uq_candidate"),
        Index("ix_candidate_product", "task_id", "ozon_product_id"),
        Index("ix_candidate_product_platform", "ozon_product_id", "platform"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("collect_tasks.id"), index=True)
    ozon_product_id: Mapped[int] = mapped_column(ForeignKey("ozon_products.id"), index=True)
    platform: Mapped[str] = mapped_column(String(16))
    offer_id: Mapped[str] = mapped_column(String(64))
    title: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    quantity_begin: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quantity_prices: Mapped[list | None] = mapped_column(_JSONB, nullable=True)
    image_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    images: Mapped[list | None] = mapped_column(_JSONB, nullable=True)
    phash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    embedding: Mapped[list | None] = mapped_column(_VECTOR, nullable=True)
    detail_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    supplier_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    supplier_info: Mapped[dict | None] = mapped_column(_JSONB, nullable=True)
    dedup_group: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_representative: Mapped[bool] = mapped_column(Boolean, default=True)
    source_account_id: Mapped[int | None] = mapped_column(ForeignKey("source_accounts.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="candidate")
    raw: Mapped[dict | None] = mapped_column(_JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

- [ ] **Step 4: 改 `models/collect_task.py` 加 match_* 列**

先读 `collect_task.py`——M1 已在其中定义了 `_JSONB = JSONB().with_variant(JSON(), "sqlite")`（用于 source_platforms/cursor/stats 等列）。复用这个已有的 `_JSONB`，在 `CollectTask` 内 `stats` 列之后加：
```python
    match_status: Mapped[str] = mapped_column(String(16), default="pending")   # pending/running/paused/done/failed
    match_cursor: Mapped[dict | None] = mapped_column(_JSONB, nullable=True)
    match_stats: Mapped[dict | None] = mapped_column(_JSONB, nullable=True)
```
（若该文件里的变量名不是 `_JSONB`，用它实际定义的那个 variant 变量；不要新造 `__import__` 之类的写法。）

- [ ] **Step 5: 改 `models/__init__.py` 导出**

```python
from app.models.source_account import SourceAccount
from app.models.supply_candidate import SupplyCandidate, EMBED_DIM
```
并加入 `__all__`。

- [ ] **Step 6: 写失败测试 `tests/test_source_models.py`**

```python
import pytest
from sqlalchemy import select
from app.models import SourceAccount, SupplyCandidate, CollectTask, OzonProduct

@pytest.mark.asyncio
async def test_create_account_and_candidate(db_session):
    t = CollectTask(name="t", entry_type="keyword", entry_value="x", provider="mock", source_platforms=["ali1688"])
    db_session.add(t); await db_session.flush()
    p = OzonProduct(task_id=t.id, sku="SKU1", title="phone")
    db_session.add(p); await db_session.flush()
    acc = SourceAccount(platform="ali1688", credentials_encrypted=b"x", daily_limit=100)
    db_session.add(acc); await db_session.flush()
    c = SupplyCandidate(task_id=t.id, ozon_product_id=p.id, platform="ali1688", offer_id="A1",
                        title="cand", price=9.9, embedding=[0.1] * 512, supplier_info={"repurchase_rate": 0.45})
    db_session.add(c); await db_session.commit()
    assert t.match_status == "pending"
    assert acc.status == "active" and acc.min_interval_sec == 6
    got = (await db_session.execute(select(SupplyCandidate).where(SupplyCandidate.offer_id == "A1"))).scalar_one()
    assert got.is_representative is True and got.supplier_info["repurchase_rate"] == 0.45
    assert len(got.embedding) == 512
```

- [ ] **Step 7: 运行确认失败**

Run: `ozon-listing-auto/server/.venv/bin/python -m pytest ozon-listing-auto/server/tests/test_source_models.py -v`
Expected: FAIL（模型/列未定义）。若报 `Vector` 相关 CompileError on sqlite，说明 with_variant 写法需调整——按上面的 TypeDecorator 退化方案修正。

- [ ] **Step 8: 写迁移 `0002_m2_source_matching.py`**

```python
"""m2 source matching"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from pgvector.sqlalchemy import Vector

revision = "0002"
down_revision = "0001"

def upgrade():
    op.create_table("source_accounts",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("platform", sa.String(16), nullable=False, index=True),
        sa.Column("label", sa.String(128)),
        sa.Column("credentials_encrypted", sa.LargeBinary, nullable=False),
        sa.Column("status", sa.String(16), server_default="active"),
        sa.Column("last_used_at", sa.DateTime(timezone=True)),
        sa.Column("daily_used_date", sa.Date),
        sa.Column("daily_used_count", sa.Integer, server_default="0"),
        sa.Column("daily_limit", sa.Integer, server_default="200"),
        sa.Column("min_interval_sec", sa.Integer, server_default="6"),
        sa.Column("cooldown_until", sa.DateTime(timezone=True)),
        sa.Column("risk_hits", sa.Integer, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table("supply_candidates",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("task_id", sa.Integer, sa.ForeignKey("collect_tasks.id"), nullable=False, index=True),
        sa.Column("ozon_product_id", sa.Integer, sa.ForeignKey("ozon_products.id"), nullable=False, index=True),
        sa.Column("platform", sa.String(16), nullable=False),
        sa.Column("offer_id", sa.String(64), nullable=False),
        sa.Column("title", sa.String(1024)), sa.Column("price", sa.Float), sa.Column("currency", sa.String(8)),
        sa.Column("quantity_begin", sa.Integer), sa.Column("quantity_prices", postgresql.JSONB),
        sa.Column("image_url", sa.String(512)), sa.Column("images", postgresql.JSONB),
        sa.Column("phash", sa.String(64)), sa.Column("embedding", Vector(512)),
        sa.Column("detail_url", sa.String(512)), sa.Column("supplier_name", sa.String(256)),
        sa.Column("supplier_info", postgresql.JSONB),
        sa.Column("dedup_group", sa.Integer), sa.Column("is_representative", sa.Boolean, server_default=sa.true()),
        sa.Column("source_account_id", sa.Integer, sa.ForeignKey("source_accounts.id")),
        sa.Column("status", sa.String(16), server_default="candidate"),
        sa.Column("raw", postgresql.JSONB),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("task_id", "ozon_product_id", "platform", "offer_id", name="uq_candidate"),
    )
    op.create_index("ix_candidate_product", "supply_candidates", ["task_id", "ozon_product_id"])
    op.create_index("ix_candidate_product_platform", "supply_candidates", ["ozon_product_id", "platform"])
    op.add_column("collect_tasks", sa.Column("match_status", sa.String(16), server_default="pending"))
    op.add_column("collect_tasks", sa.Column("match_cursor", postgresql.JSONB))
    op.add_column("collect_tasks", sa.Column("match_stats", postgresql.JSONB))

def downgrade():
    op.drop_column("collect_tasks", "match_stats")
    op.drop_column("collect_tasks", "match_cursor")
    op.drop_column("collect_tasks", "match_status")
    op.drop_table("supply_candidates")
    op.drop_table("source_accounts")
```

- [ ] **Step 9: 运行确认通过 + 全套回归**

Run: `ozon-listing-auto/server/.venv/bin/python -m pytest ozon-listing-auto/server/tests -q`
Expected: PASS（含新 test_source_models，0 warnings）。

- [ ] **Step 10: 提交**

```bash
git add ozon-listing-auto/server/pyproject.toml ozon-listing-auto/server/app/models ozon-listing-auto/server/alembic/versions/0002_m2_source_matching.py ozon-listing-auto/server/tests/test_source_models.py
git commit -m "feat(m2): 迁移0002 + ORM(source_accounts/supply_candidates/collect_tasks.match_*) + pgvector 依赖"
```

---

## 阶段 1 · 抽象与核心（mock-first）

### Task 2: SourceProvider 抽象 + DTO + 工厂 + Mock 最小实现

**Files:**
- Create: `ozon-listing-auto/server/app/services/sources/__init__.py`
- Create: `ozon-listing-auto/server/app/services/sources/base.py`
- Create: `ozon-listing-auto/server/app/services/sources/factory.py`
- Create: `ozon-listing-auto/server/app/services/sources/mock.py`（最小版，Task 3 扩展）
- Create: `ozon-listing-auto/server/tests/test_source_provider.py`

**Interfaces:**
- Produces: `base.SupplyCandidateDTO`（dataclass，字段见 spec §4.1）；`base.SourceProvider`(Protocol：`platform`, `image_search`, `keyword_search`, `fetch_detail`，均 async)；`factory.get_source_provider(platform)`（ali1688/pinduoduo/mock，真实 provider 惰性 import）。

- [ ] **Step 1: 写失败测试 `tests/test_source_provider.py`**

```python
import pytest
from app.services.sources.factory import get_source_provider
from app.services.sources.base import SupplyCandidateDTO

@pytest.mark.asyncio
async def test_factory_returns_mock():
    p = get_source_provider("mock")
    assert p.platform == "mock"
    items = await p.keyword_search("phone", session=None)
    assert items and isinstance(items[0], SupplyCandidateDTO)

def test_factory_unknown_raises():
    with pytest.raises(ValueError):
        get_source_provider("nope")
```

- [ ] **Step 2: 运行确认失败**

Run: `ozon-listing-auto/server/.venv/bin/python -m pytest ozon-listing-auto/server/tests/test_source_provider.py -v`
Expected: FAIL（未定义）。

- [ ] **Step 3: 写 `base.py`**

```python
"""货源 SourceProvider 抽象接口与候选 DTO（对齐开发文档 §5.3）。"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Protocol

@dataclass
class SupplyCandidateDTO:
    platform: str
    offer_id: str
    title: str | None = None
    price: float | None = None
    currency: str | None = None
    quantity_begin: int | None = None
    quantity_prices: list | None = None
    image_url: str | None = None
    images: list[str] = field(default_factory=list)
    detail_url: str | None = None
    supplier_name: str | None = None
    supplier_info: dict = field(default_factory=dict)
    phash: str | None = None
    raw: dict = field(default_factory=dict)

class SourceProvider(Protocol):
    platform: str
    async def image_search(self, image_url: str, *, session) -> list[SupplyCandidateDTO]: ...
    async def keyword_search(self, kw: str, *, session) -> list[SupplyCandidateDTO]: ...
    async def fetch_detail(self, offer_id: str, *, session) -> SupplyCandidateDTO: ...
```

- [ ] **Step 4: 写最小 `mock.py`（Task 3 扩展）**

```python
"""MockSourceProvider：从 fixtures 返回货源候选，供 mock-first 跑通链路。"""
from app.services.sources.base import SupplyCandidateDTO

class MockSourceProvider:
    platform = "mock"
    async def image_search(self, image_url: str, *, session) -> list[SupplyCandidateDTO]:
        return [SupplyCandidateDTO(platform="mock", offer_id="M1", title="示例", price=9.9)]
    async def keyword_search(self, kw: str, *, session) -> list[SupplyCandidateDTO]:
        return await self.image_search("", session=session)
    async def fetch_detail(self, offer_id: str, *, session) -> SupplyCandidateDTO:
        return SupplyCandidateDTO(platform="mock", offer_id=offer_id)
```

- [ ] **Step 5: 写 `factory.py`**

```python
"""按平台名返回 SourceProvider 实现；真实 provider 惰性 import。"""
from app.services.sources.base import SourceProvider
from app.services.sources.mock import MockSourceProvider

def get_source_provider(platform: str) -> SourceProvider:
    if platform == "mock":
        return MockSourceProvider()
    if platform == "ali1688":
        from app.services.sources.ali1688 import Ali1688Provider
        return Ali1688Provider()
    if platform == "pinduoduo":
        from app.services.sources.pinduoduo import PinduoduoProvider
        return PinduoduoProvider()
    raise ValueError(f"未知货源平台: {platform}")
```

- [ ] **Step 6: 运行确认通过**

Run: `ozon-listing-auto/server/.venv/bin/python -m pytest ozon-listing-auto/server/tests/test_source_provider.py -v`
Expected: PASS。

- [ ] **Step 7: 提交**

```bash
git add ozon-listing-auto/server/app/services/sources ozon-listing-auto/server/tests/test_source_provider.py
git commit -m "feat(m2): SourceProvider 抽象 + DTO + 工厂(mock/ali1688/pinduoduo 惰性)"
```

---

### Task 3: MockSourceProvider 完整实现 + fixtures（跨平台近似重复 + 完整供应商字段）

**Files:**
- Modify: `ozon-listing-auto/server/app/services/sources/mock.py`
- Create: `ozon-listing-auto/server/app/fixtures/source_mock.json`
- Create: `ozon-listing-auto/server/tests/test_mock_source.py`

**Interfaces:**
- Consumes: `SupplyCandidateDTO`。
- Produces: `MockSourceProvider(platform=...)` 可指定模拟平台；`keyword_search`/`image_search` 从 fixtures 返回该平台候选。fixtures 覆盖 `ali1688` 与 `pinduoduo` 两组，**刻意含跨平台近似重复图**（相同/相近 `image_url`，供 CLIP 去重测试）+ 不同款，且填充完整 `supplier_info`。

- [ ] **Step 1: 写 fixtures `app/fixtures/source_mock.json`**

```json
{
  "ali1688": [
    {"offer_id": "AL-1", "title": "无线耳机", "price": 12.5, "currency": "CNY", "quantity_begin": 2,
     "quantity_prices": [{"qty": 2, "price": 12.5}, {"qty": 100, "price": 9.9}],
     "image_url": "https://img/earbuds_black.jpg", "detail_url": "https://1688/AL-1",
     "supplier_name": "深圳某电子厂",
     "supplier_info": {"repurchase_rate": 0.45, "credit_level": "AAA", "credit_text": "信用AAA",
        "reg_capital": "500万", "province": "广东", "city": "深圳",
        "position_labels": ["深度验厂", "7×24H响应"], "scores": {"综合": 4.8, "物流": 4.7, "退货": 4.9}, "gmv_price": 100000}},
    {"offer_id": "AL-2", "title": "机械键盘", "price": 45.0, "currency": "CNY", "quantity_begin": 1,
     "image_url": "https://img/keyboard.jpg", "detail_url": "https://1688/AL-2",
     "supplier_name": "东莞某厂", "supplier_info": {"repurchase_rate": 0.30, "credit_level": "AA", "province": "广东"}}
  ],
  "pinduoduo": [
    {"offer_id": "PDD-1", "title": "无线耳机 蓝牙", "price": 13.9, "currency": "CNY",
     "image_url": "https://img/earbuds_black.jpg", "detail_url": "https://pdd/PDD-1",
     "supplier_name": "拼多多店A", "supplier_info": {"scores": {"综合": 4.6}, "province": "浙江"}},
    {"offer_id": "PDD-2", "title": "手机支架", "price": 6.5, "currency": "CNY",
     "image_url": "https://img/phone_stand.jpg", "detail_url": "https://pdd/PDD-2",
     "supplier_name": "拼多多店B", "supplier_info": {"scores": {"综合": 4.3}}}
  ]
}
```
说明：`AL-1` 与 `PDD-1` 用**相同 image_url**（同款跨平台）→ 去重应聚为一簇；`AL-2`/`PDD-2` 各自不同款。

- [ ] **Step 2: 写失败测试 `tests/test_mock_source.py`**

```python
import pytest
from app.services.sources.mock import MockSourceProvider

@pytest.mark.asyncio
async def test_mock_platform_scoped():
    ali = MockSourceProvider(platform="ali1688")
    pdd = MockSourceProvider(platform="pinduoduo")
    a = await ali.keyword_search("耳机", session=None)
    p = await pdd.keyword_search("耳机", session=None)
    assert all(c.platform == "ali1688" for c in a) and len(a) == 2
    assert all(c.platform == "pinduoduo" for c in p) and len(p) == 2
    al1 = next(c for c in a if c.offer_id == "AL-1")
    assert al1.supplier_info["credit_level"] == "AAA" and al1.quantity_begin == 2
    # 跨平台同款: AL-1 与 PDD-1 同图
    pdd1 = next(c for c in p if c.offer_id == "PDD-1")
    assert pdd1.image_url == al1.image_url
```

- [ ] **Step 3: 运行确认失败**

Run: `ozon-listing-auto/server/.venv/bin/python -m pytest ozon-listing-auto/server/tests/test_mock_source.py -v`
Expected: FAIL（当前 mock 不分平台、无 fixtures）。

- [ ] **Step 4: 写完整 `mock.py`**

```python
"""MockSourceProvider：按平台从 fixtures 返回货源候选（含跨平台近似重复样本）。"""
import json
from pathlib import Path
from app.services.sources.base import SupplyCandidateDTO

_DATA = Path(__file__).resolve().parents[2] / "fixtures" / "source_mock.json"

def _load() -> dict:
    return json.loads(_DATA.read_text(encoding="utf-8"))

def _to_dto(platform: str, d: dict) -> SupplyCandidateDTO:
    return SupplyCandidateDTO(
        platform=platform, offer_id=d["offer_id"], title=d.get("title"), price=d.get("price"),
        currency=d.get("currency"), quantity_begin=d.get("quantity_begin"), quantity_prices=d.get("quantity_prices"),
        image_url=d.get("image_url"), images=d.get("images", []), detail_url=d.get("detail_url"),
        supplier_name=d.get("supplier_name"), supplier_info=d.get("supplier_info", {}), raw=d,
    )

class MockSourceProvider:
    def __init__(self, platform: str = "mock"):
        self.platform = platform
        self._all = _load()

    def _candidates(self) -> list[SupplyCandidateDTO]:
        rows = self._all.get(self.platform, [])
        return [_to_dto(self.platform, d) for d in rows]

    async def image_search(self, image_url: str, *, session) -> list[SupplyCandidateDTO]:
        return self._candidates()
    async def keyword_search(self, kw: str, *, session) -> list[SupplyCandidateDTO]:
        return self._candidates()
    async def fetch_detail(self, offer_id: str, *, session) -> SupplyCandidateDTO:
        for c in self._candidates():
            if c.offer_id == offer_id:
                return c
        return SupplyCandidateDTO(platform=self.platform, offer_id=offer_id)
```

注意：`get_source_provider("mock")`（Task 2 工厂）仍需可用 → 工厂里 `MockSourceProvider()` 默认 platform="mock"，其 fixtures 无 "mock" 键 → 返回空。matcher 用 `MockSourceProvider(platform=<真实平台名>)`。为让 Task 2 的 `test_source_provider` 仍绿（它断言 mock keyword_search 返回非空），**在 fixtures 增加一个 `"mock"` 键**，含 1 条简单候选：
```json
  "mock": [{"offer_id": "M1", "title": "示例", "price": 9.9, "image_url": "https://img/m.jpg"}]
```

- [ ] **Step 5: 运行确认通过（新测试 + Task 2 测试仍绿）**

Run: `ozon-listing-auto/server/.venv/bin/python -m pytest ozon-listing-auto/server/tests/test_mock_source.py ozon-listing-auto/server/tests/test_source_provider.py -v`
Expected: PASS。

- [ ] **Step 6: 提交**

```bash
git add ozon-listing-auto/server/app/services/sources/mock.py ozon-listing-auto/server/app/fixtures/source_mock.json ozon-listing-auto/server/tests/test_mock_source.py
git commit -m "feat(m2): MockSourceProvider 完整实现 + fixtures(跨平台近似重复+完整供应商字段)"
```

---

### Task 4: Embedder 抽象 + MockEmbedder + 工厂

**Files:**
- Create: `ozon-listing-auto/server/app/services/embedding/__init__.py`
- Create: `ozon-listing-auto/server/app/services/embedding/base.py`
- Create: `ozon-listing-auto/server/app/services/embedding/mock.py`
- Create: `ozon-listing-auto/server/app/services/embedding/clip.py`（占位，Task 10 实现）
- Create: `ozon-listing-auto/server/app/services/embedding/factory.py`
- Create: `ozon-listing-auto/server/tests/test_embedder.py`

**Interfaces:**
- Produces: `base.Embedder`(Protocol：`dim`, `embed_image`, `embed_images`)；`mock.MockEmbedder`（URL 确定性哈希→归一化 512 维向量，相同 URL 相同向量、不同 URL 近正交）；`factory.get_embedder(name)`（默认 mock；clip 惰性 import）。常量复用 `EMBED_DIM`。

- [ ] **Step 1: 写失败测试 `tests/test_embedder.py`**

```python
import math
import pytest
from app.services.embedding.mock import MockEmbedder
from app.services.embedding.factory import get_embedder

def _cos(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)); nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb)

@pytest.mark.asyncio
async def test_mock_embedder_deterministic_and_normalized():
    e = MockEmbedder()
    v1 = await e.embed_image("https://img/a.jpg")
    v1b = await e.embed_image("https://img/a.jpg")
    v2 = await e.embed_image("https://img/b.jpg")
    assert e.dim == 512 and len(v1) == 512
    assert _cos(v1, v1b) > 0.999          # 相同 URL → 相同向量
    assert _cos(v1, v2) < 0.5             # 不同 URL → 低相似
    assert abs(math.sqrt(sum(x * x for x in v1)) - 1.0) < 1e-6   # 归一化

def test_factory_default_mock():
    assert get_embedder("mock").dim == 512
    with pytest.raises(ValueError):
        get_embedder("nope")
```

- [ ] **Step 2: 运行确认失败**

Run: `ozon-listing-auto/server/.venv/bin/python -m pytest ozon-listing-auto/server/tests/test_embedder.py -v`
Expected: FAIL。

- [ ] **Step 3: 写 `base.py`**

```python
"""图像向量 Embedder 抽象（CLIP）。"""
from typing import Protocol

class Embedder(Protocol):
    dim: int
    async def embed_image(self, image_url: str) -> list[float]: ...
    async def embed_images(self, urls: list[str]) -> list[list[float]]: ...
```

- [ ] **Step 4: 写 `mock.py`**

```python
"""MockEmbedder：对 URL 做确定性哈希 → 归一化 512 维向量，供测试/开发（无模型/网络）。"""
import hashlib
import math
from app.models.supply_candidate import EMBED_DIM

class MockEmbedder:
    dim = EMBED_DIM
    async def embed_image(self, image_url: str) -> list[float]:
        vec: list[float] = []
        i = 0
        seed = (image_url or "").encode()
        while len(vec) < self.dim:
            h = hashlib.sha256(seed + i.to_bytes(4, "big")).digest()
            for b in h:
                vec.append(b / 255.0 - 0.5)
                if len(vec) == self.dim:
                    break
            i += 1
        norm = math.sqrt(sum(x * x for x in vec)) or 1.0
        return [x / norm for x in vec]
    async def embed_images(self, urls: list[str]) -> list[list[float]]:
        return [await self.embed_image(u) for u in urls]
```

- [ ] **Step 5: 写占位 `clip.py` 与 `factory.py`**

`clip.py`:
```python
"""ChineseClipEmbedder：cn_clip ViT-B/16 CPU 推理（Task 10 实现真实版）。"""
from app.models.supply_candidate import EMBED_DIM

class ChineseClipEmbedder:
    dim = EMBED_DIM
    async def embed_image(self, image_url: str) -> list[float]:
        raise NotImplementedError("ChineseClipEmbedder 将在 Task 10 实现真实 CLIP 推理")
    async def embed_images(self, urls: list[str]) -> list[list[float]]:
        raise NotImplementedError
```

`factory.py`:
```python
"""按名返回 Embedder；默认 mock，clip 惰性 import。"""
from app.services.embedding.base import Embedder
from app.services.embedding.mock import MockEmbedder

def get_embedder(name: str = "mock") -> Embedder:
    if name == "mock":
        return MockEmbedder()
    if name == "clip":
        from app.services.embedding.clip import ChineseClipEmbedder
        return ChineseClipEmbedder()
    raise ValueError(f"未知 embedder: {name}")
```

- [ ] **Step 6: 运行确认通过**

Run: `ozon-listing-auto/server/.venv/bin/python -m pytest ozon-listing-auto/server/tests/test_embedder.py -v`
Expected: PASS。

- [ ] **Step 7: 提交**

```bash
git add ozon-listing-auto/server/app/services/embedding ozon-listing-auto/server/tests/test_embedder.py
git commit -m "feat(m2): Embedder 抽象 + MockEmbedder(确定性归一化向量) + 工厂"
```

---

### Task 5: 候选入库 + 跨平台 CLIP 去重（candidate_ingest）

**Files:**
- Create: `ozon-listing-auto/server/app/services/candidate_ingest.py`
- Create: `ozon-listing-auto/server/tests/test_candidate_ingest.py`

**Interfaces:**
- Consumes: `SupplyCandidateDTO`, `Embedder`, `SupplyCandidate` 模型, AsyncSession。
- Produces:
  - `cluster_by_similarity(embeddings: list[list[float]], threshold: float) -> list[int]`（贪心聚簇，返回每条的簇号；相同簇号=近似重复；代表=每簇首条）。
  - `async dedup_and_upsert(session, task_id, ozon_product_id, dtos, embedder, *, threshold=0.92, account_id=None) -> dict`（对每个 DTO 主图取向量→聚簇→标 dedup_group/is_representative→按 `(task_id,ozon_product_id,platform,offer_id)` 幂等 upsert；返回 `{"inserted","skipped","clusters"}`）。

- [ ] **Step 1: 写失败测试 `tests/test_candidate_ingest.py`**

```python
import pytest
from sqlalchemy import select, func
from app.services.candidate_ingest import cluster_by_similarity, dedup_and_upsert
from app.services.sources.base import SupplyCandidateDTO
from app.services.embedding.mock import MockEmbedder
from app.models import SupplyCandidate, CollectTask, OzonProduct

@pytest.mark.asyncio
async def test_cluster_groups_near_duplicates():
    e = MockEmbedder()
    va = await e.embed_image("https://img/x.jpg")
    vb = await e.embed_image("https://img/x.jpg")   # 同图 → 同向量
    vc = await e.embed_image("https://img/y.jpg")   # 不同图
    groups = cluster_by_similarity([va, vb, vc], threshold=0.92)
    assert groups[0] == groups[1]        # 同图同簇
    assert groups[2] != groups[0]        # 不同图不同簇

async def _seed(db_session):
    t = CollectTask(name="t", entry_type="keyword", entry_value="x", provider="mock", source_platforms=["ali1688","pinduoduo"])
    db_session.add(t); await db_session.flush()
    p = OzonProduct(task_id=t.id, sku="S1", title="phone", main_image_url="https://img/oz.jpg")
    db_session.add(p); await db_session.commit()
    return t.id, p.id

@pytest.mark.asyncio
async def test_dedup_and_upsert_cross_platform(db_session):
    tid, pid = await _seed(db_session)
    dtos = [
        SupplyCandidateDTO(platform="ali1688", offer_id="AL-1", image_url="https://img/same.jpg"),
        SupplyCandidateDTO(platform="pinduoduo", offer_id="PDD-1", image_url="https://img/same.jpg"),  # 同款跨平台
        SupplyCandidateDTO(platform="ali1688", offer_id="AL-2", image_url="https://img/other.jpg"),    # 不同款
    ]
    r = await dedup_and_upsert(db_session, tid, pid, dtos, MockEmbedder(), threshold=0.92)
    await db_session.commit()
    rows = (await db_session.execute(select(SupplyCandidate).where(SupplyCandidate.ozon_product_id == pid))).scalars().all()
    assert r["inserted"] == 3                              # 三条都入库(不删, 只标去重)
    reps = [x for x in rows if x.is_representative]
    # 同款跨平台折叠为一簇(一个代表), 不同款单独一簇 → 共 2 簇, 2 个代表
    assert len({x.dedup_group for x in rows}) == 2
    assert len(reps) == 2
    # 幂等: 再来一次不新增
    r2 = await dedup_and_upsert(db_session, tid, pid, dtos, MockEmbedder(), threshold=0.92)
    await db_session.commit()
    assert r2["inserted"] == 0 and r2["skipped"] == 3
```

- [ ] **Step 2: 运行确认失败**

Run: `ozon-listing-auto/server/.venv/bin/python -m pytest ozon-listing-auto/server/tests/test_candidate_ingest.py -v`
Expected: FAIL。

- [ ] **Step 3: 写 `candidate_ingest.py`**

```python
"""货源候选入库：CLIP 向量贪心聚簇跨平台去重 + 幂等 upsert。"""
import math
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.sources.base import SupplyCandidateDTO
from app.models import SupplyCandidate

def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)); nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)

def cluster_by_similarity(embeddings: list[list[float]], threshold: float) -> list[int]:
    """贪心聚簇：每条与已有簇代表比余弦，>阈值归入该簇，否则新簇。返回每条的簇号。"""
    reps: list[tuple[int, list[float]]] = []   # (group_id, rep_vec)
    groups: list[int] = []
    for emb in embeddings:
        assigned = None
        if emb is not None:
            for gid, rep in reps:
                if _cosine(emb, rep) >= threshold:
                    assigned = gid
                    break
        if assigned is None:
            assigned = len(reps)
            reps.append((assigned, emb if emb is not None else []))
        groups.append(assigned)
    return groups

async def dedup_and_upsert(session: AsyncSession, task_id: int, ozon_product_id: int,
                           dtos: list[SupplyCandidateDTO], embedder, *,
                           threshold: float = 0.92, account_id: int | None = None) -> dict:
    embeddings = [await embedder.embed_image(d.image_url) if d.image_url else None for d in dtos]
    groups = cluster_by_similarity(embeddings, threshold)
    seen_rep: set[int] = set()
    inserted = skipped = 0
    for d, emb, gid in zip(dtos, embeddings, groups):
        exists = (await session.execute(select(SupplyCandidate.id).where(
            SupplyCandidate.task_id == task_id, SupplyCandidate.ozon_product_id == ozon_product_id,
            SupplyCandidate.platform == d.platform, SupplyCandidate.offer_id == d.offer_id))).scalar_one_or_none()
        if exists:
            skipped += 1
            continue
        is_rep = gid not in seen_rep
        seen_rep.add(gid)
        session.add(SupplyCandidate(
            task_id=task_id, ozon_product_id=ozon_product_id, platform=d.platform, offer_id=d.offer_id,
            title=d.title, price=d.price, currency=d.currency, quantity_begin=d.quantity_begin,
            quantity_prices=d.quantity_prices, image_url=d.image_url, images=d.images, phash=d.phash,
            embedding=emb, detail_url=d.detail_url, supplier_name=d.supplier_name, supplier_info=d.supplier_info,
            dedup_group=gid, is_representative=is_rep, source_account_id=account_id, raw=d.raw,
        ))
        inserted += 1
    return {"inserted": inserted, "skipped": skipped, "clusters": len(set(groups))}
```

- [ ] **Step 4: 运行确认通过**

Run: `ozon-listing-auto/server/.venv/bin/python -m pytest ozon-listing-auto/server/tests/test_candidate_ingest.py -v`
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add ozon-listing-auto/server/app/services/candidate_ingest.py ozon-listing-auto/server/tests/test_candidate_ingest.py
git commit -m "feat(m2): candidate_ingest 跨平台 CLIP 贪心聚簇去重 + 幂等 upsert"
```

---

### Task 6: 账号池（限速/冷却/换号）

**Files:**
- Create: `ozon-listing-auto/server/app/services/account_pool.py`
- Create: `ozon-listing-auto/server/tests/test_account_pool.py`

**Interfaces:**
- Consumes: `SourceAccount` 模型, AsyncSession, `crypto.decrypt`。
- Produces:
  - `async acquire(session_factory, platform, *, now) -> SourceAccount | None`（选 active、非冷却(`cooldown_until` 空或 < now)、`last_used_at` 为空或 `now-last_used_at >= min_interval_sec`、当日用量 `< daily_limit` 的账号；更新 `last_used_at=now`、当日计数(跨天按 `now.date()` 重置)；提交。无可用返 None）。`now` 由调用方传入（可测；生产传当前时间）。
  - `async report_risk(session_factory, account_id, *, now, cooldown_sec=1800)`（`risk_hits+1`、`cooldown_until=now+cooldown`、`status="cooldown"`）。
  - `get_session_credentials(account) -> dict`（Fernet 解密 credentials_encrypted → dict）。
  - 并发锁：`acquire` 接受可选 `lock=None`（异步上下文管理器）；默认 no-op；生产传 Redis 锁。M2 测试用默认。

- [ ] **Step 1: 写失败测试 `tests/test_account_pool.py`**

```python
import json
import pytest
from datetime import datetime, timezone, timedelta
from app.services.account_pool import acquire, report_risk, get_session_credentials
from app.core.crypto import encrypt
from app.models import SourceAccount

def _acc(**kw):
    base = dict(platform="ali1688", credentials_encrypted=encrypt(json.dumps({"cookie": "c"})),
                status="active", daily_limit=5, min_interval_sec=6, daily_used_count=0)
    base.update(kw)
    return SourceAccount(**base)

@pytest.mark.asyncio
async def test_acquire_respects_interval(engine):
    from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
    sm = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    now = datetime(2026, 7, 17, 12, 0, 0, tzinfo=timezone.utc)
    async with sm() as s:
        s.add(_acc(last_used_at=now - timedelta(seconds=3)))   # 3s前用过, <6s 不可用
        await s.commit()
    got = await acquire(sm, "ali1688", now=now)
    assert got is None
    # 7s 后可用
    got2 = await acquire(sm, "ali1688", now=now + timedelta(seconds=7))
    assert got2 is not None and got2.platform == "ali1688"

@pytest.mark.asyncio
async def test_acquire_daily_limit_and_reset(engine):
    from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
    sm = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    now = datetime(2026, 7, 17, 12, 0, 0, tzinfo=timezone.utc)
    async with sm() as s:
        s.add(_acc(daily_used_count=5, daily_used_date=now.date(), last_used_at=None))  # 已达上限
        await s.commit()
    assert await acquire(sm, "ali1688", now=now) is None
    # 次日重置
    assert await acquire(sm, "ali1688", now=now + timedelta(days=1)) is not None

@pytest.mark.asyncio
async def test_report_risk_sets_cooldown(engine):
    from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
    from sqlalchemy import select
    sm = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    now = datetime(2026, 7, 17, 12, 0, 0, tzinfo=timezone.utc)
    async with sm() as s:
        s.add(_acc(last_used_at=None)); await s.commit()
        aid = (await s.execute(select(SourceAccount.id))).scalar_one()
    await report_risk(sm, aid, now=now, cooldown_sec=1800)
    async with sm() as s:
        acc = (await s.execute(select(SourceAccount).where(SourceAccount.id == aid))).scalar_one()
        assert acc.status == "cooldown" and acc.risk_hits == 1
    assert await acquire(sm, "ali1688", now=now) is None                    # 冷却中不可用
    assert await acquire(sm, "ali1688", now=now + timedelta(seconds=1801)) is not None  # 冷却结束

def test_get_credentials_decrypts():
    acc = _acc()
    assert get_session_credentials(acc)["cookie"] == "c"
```

- [ ] **Step 2: 运行确认失败**

Run: `ozon-listing-auto/server/.venv/bin/python -m pytest ozon-listing-auto/server/tests/test_account_pool.py -v`
Expected: FAIL。

- [ ] **Step 3: 写 `account_pool.py`**

```python
"""货源账号池：按平台取可用账号(限速/日限/冷却), 风控置冷却换号; cookie Fernet 解密。"""
import json
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker
from app.core.crypto import decrypt
from app.models import SourceAccount

@asynccontextmanager
async def _noop_lock():
    yield

def get_session_credentials(account: SourceAccount) -> dict:
    return json.loads(decrypt(account.credentials_encrypted))

async def acquire(session_factory: async_sessionmaker, platform: str, *, now: datetime, lock=None):
    lock = lock or _noop_lock()
    async with lock:
        async with session_factory() as s:
            rows = (await s.execute(select(SourceAccount).where(
                SourceAccount.platform == platform, SourceAccount.status == "active"
            ).order_by(SourceAccount.last_used_at.asc().nulls_first()))).scalars().all()
            for acc in rows:
                if acc.cooldown_until and acc.cooldown_until > now:
                    continue
                if acc.last_used_at and (now - acc.last_used_at).total_seconds() < acc.min_interval_sec:
                    continue
                today = now.date()
                used = acc.daily_used_count if acc.daily_used_date == today else 0
                if used >= acc.daily_limit:
                    continue
                # 命中：更新用量
                acc.last_used_at = now
                acc.daily_used_date = today
                acc.daily_used_count = used + 1
                await s.commit()
                await s.refresh(acc)
                return acc
            return None

async def report_risk(session_factory: async_sessionmaker, account_id: int, *, now: datetime, cooldown_sec: int = 1800):
    async with session_factory() as s:
        acc = (await s.execute(select(SourceAccount).where(SourceAccount.id == account_id))).scalar_one()
        acc.risk_hits += 1
        acc.status = "cooldown"
        acc.cooldown_until = now + timedelta(seconds=cooldown_sec)
        await s.commit()
```

注意：`acquire` 命中后 `status` 保持 active；`report_risk` 才置 cooldown。`acquire` 里冷却判断用 `cooldown_until > now`（不依赖 status，因为冷却结束需自动恢复——可选：命中时若 status=cooldown 且 cooldown_until<=now 则复位 active。为简单，`acquire` 查询限定 `status=="active"`，故 report_risk 置 cooldown 后该账号不再被选，直到有流程复位。**补一步**：在 `acquire` 查询改为不限 status，但在循环内跳过 `status=="disabled"`，并对 `status=="cooldown"` 且 `cooldown_until<=now` 的账号复位 `status="active"` 再使用。见 Step 4。）

- [ ] **Step 4: 修正 acquire 让冷却到期自动恢复**

将 `acquire` 的查询与判断改为：
```python
            rows = (await s.execute(select(SourceAccount).where(
                SourceAccount.platform == platform, SourceAccount.status != "disabled"
            ).order_by(SourceAccount.last_used_at.asc().nulls_first()))).scalars().all()
            for acc in rows:
                if acc.cooldown_until and acc.cooldown_until > now:
                    continue                        # 冷却中
                if acc.status == "cooldown":
                    acc.status = "active"           # 冷却到期, 复位
                if acc.last_used_at and (now - acc.last_used_at).total_seconds() < acc.min_interval_sec:
                    continue
                ...
```
（其余不变。）这样 `test_report_risk_sets_cooldown` 的「冷却结束后可用」成立。

- [ ] **Step 5: 运行确认通过**

Run: `ozon-listing-auto/server/.venv/bin/python -m pytest ozon-listing-auto/server/tests/test_account_pool.py -v`
Expected: PASS。

- [ ] **Step 6: 提交**

```bash
git add ozon-listing-auto/server/app/services/account_pool.py ozon-listing-auto/server/tests/test_account_pool.py
git commit -m "feat(m2): 账号池 acquire(限速/日限/冷却自恢复)+report_risk+cookie 解密"
```

---

### Task 7: matcher worker（遍历商品×平台 → 搜 → 去重入库 → 断点/暂停/失败）

**Files:**
- Create: `ozon-listing-auto/server/app/workers/matcher.py`
- Modify: `ozon-listing-auto/server/app/workers/arq_worker.py`（注册 `run_match`）
- Create: `ozon-listing-auto/server/tests/test_matcher.py`

**Interfaces:**
- Consumes: `get_source_provider`, `account_pool.acquire/report_risk`, `candidate_ingest.dedup_and_upsert`, `OzonProduct`/`CollectTask`, Embedder。
- Produces:
  - `async run_match_core(session_factory, task_id, *, embedder, now_fn=None, max_products=None, progress_cb=None) -> dict`（读 task→遍历其 ozon_products(按 id 升序, `match_cursor` 记录 last_product_id 断点续传)→每商品遍历 `task.source_platforms`→`acquire`→provider `image_search(main_image_url)`+`keyword_search(title)`→`dedup_and_upsert`→写 match_stats/match_cursor→提交；`match_status` running→done；商品级 try/except 置 failed(§4.2.6 范式)；paused 停止）。返回 `{"products","candidates","platforms_skipped"}`。
  - `async run_match(ctx, task_id)`（ARQ 入口，真实 async_session + 配置选中的 embedder）。
- `now_fn`：默认返回当前时间（生产）；测试注入固定时间。provider 用 `get_source_provider(platform)`——mock 模式下用 `MockSourceProvider(platform=platform)`（见下 Step）。

**关键：** matcher 需要按平台拿到"能返回该平台候选"的 provider。mock 模式下 `get_source_provider("ali1688")` 会惰性 import 真实 Ali1688Provider（未实现）。因此 matcher 用**可注入的 provider 工厂**：`run_match_core(..., provider_factory=get_source_provider)`，测试传入返回 `MockSourceProvider(platform=platform)` 的工厂；生产传 `get_source_provider`。这样保持真实/mock 无感切换。

- [ ] **Step 1: 写失败测试 `tests/test_matcher.py`**

```python
import pytest
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
from datetime import datetime, timezone
from app.workers.matcher import run_match_core
from app.services.sources.mock import MockSourceProvider
from app.services.embedding.mock import MockEmbedder
from app.models import CollectTask, OzonProduct, SupplyCandidate, SourceAccount
from app.core.crypto import encrypt
import json

def _provider_factory(platform):        # mock 工厂: 按平台返回 mock provider
    return MockSourceProvider(platform=platform)

def _now():
    return datetime(2026, 7, 17, 12, 0, 0, tzinfo=timezone.utc)

async def _seed(sm, n_products=3):
    async with sm() as s:
        t = CollectTask(name="t", entry_type="keyword", entry_value="x", provider="mock",
                        source_platforms=["ali1688", "pinduoduo"])
        s.add(t); await s.flush()
        for i in range(n_products):
            s.add(OzonProduct(task_id=t.id, sku=f"S{i}", title=f"p{i}", main_image_url=f"https://img/oz{i}.jpg"))
        # 每平台一个账号(min_interval 0 便于连续取)
        for plat in ["ali1688", "pinduoduo"]:
            s.add(SourceAccount(platform=plat, credentials_encrypted=encrypt(json.dumps({"cookie":"c"})),
                                min_interval_sec=0, daily_limit=1000))
        await s.commit()
        return t.id

@pytest.mark.asyncio
async def test_run_match_produces_dual_platform_candidates(engine):
    sm = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    tid = await _seed(sm, n_products=3)
    result = await run_match_core(sm, tid, embedder=MockEmbedder(), now_fn=_now, provider_factory=_provider_factory)
    async with sm() as s:
        rows = (await s.execute(select(SupplyCandidate).where(SupplyCandidate.task_id == tid))).scalars().all()
        task = (await s.execute(select(CollectTask).where(CollectTask.id == tid))).scalar_one()
    platforms = {r.platform for r in rows}
    assert platforms == {"ali1688", "pinduoduo"}       # 双平台候选
    assert task.match_status == "done"
    assert result["products"] == 3

@pytest.mark.asyncio
async def test_run_match_resume(engine):
    sm = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    tid = await _seed(sm, n_products=3)
    await run_match_core(sm, tid, embedder=MockEmbedder(), now_fn=_now, provider_factory=_provider_factory, max_products=1)
    async with sm() as s:
        c1 = (await s.execute(select(func.count()).select_from(SupplyCandidate).where(SupplyCandidate.task_id==tid))).scalar_one()
        task = (await s.execute(select(CollectTask).where(CollectTask.id==tid))).scalar_one()
        assert task.match_cursor is not None
    await run_match_core(sm, tid, embedder=MockEmbedder(), now_fn=_now, provider_factory=_provider_factory)  # 续跑
    async with sm() as s:
        task = (await s.execute(select(CollectTask).where(CollectTask.id==tid))).scalar_one()
        total = (await s.execute(select(func.count()).select_from(SupplyCandidate).where(SupplyCandidate.task_id==tid))).scalar_one()
    assert task.match_status == "done"
    # 3 商品全处理(幂等, 不重复插入)
    assert total >= c1
```

- [ ] **Step 2: 运行确认失败**

Run: `ozon-listing-auto/server/.venv/bin/python -m pytest ozon-listing-auto/server/tests/test_matcher.py -v`
Expected: FAIL。

- [ ] **Step 3: 写 `workers/matcher.py`**

```python
"""货源匹配 worker：遍历商品×启用平台 → 图搜+关键词 → CLIP 去重入库；断点续传/暂停/失败。"""
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker
from app.core.logging import get_logger
from app.services.sources.factory import get_source_provider
from app.services.account_pool import acquire, report_risk, get_session_credentials
from app.services.candidate_ingest import dedup_and_upsert
from app.models import CollectTask, OzonProduct

def _default_now():
    return datetime.now(timezone.utc)

async def run_match_core(session_factory: async_sessionmaker, task_id: int, *, embedder,
                         now_fn=None, provider_factory=None, max_products=None, progress_cb=None) -> dict:
    now_fn = now_fn or _default_now
    provider_factory = provider_factory or get_source_provider
    log = get_logger(task_id=task_id, phase="match")
    async with session_factory() as s:
        task = (await s.execute(select(CollectTask).where(CollectTask.id == task_id))).scalar_one()
        platforms = list(task.source_platforms or [])
        last_id = (task.match_cursor or {}).get("last_product_id", 0)
        task.match_status = "running"; await s.commit()

    total_products = total_candidates = platforms_skipped = 0
    prev = task.match_stats or {}
    total_candidates = prev.get("candidates", 0)
    processed_done = False
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
                task.match_status = "done"
                task.match_stats = {"products": total_products, "candidates": total_candidates, "platforms_skipped": platforms_skipped}
                await s.commit()
            processed_done = True
            break
        try:
            for platform in platforms:
                acc = await acquire(session_factory, platform, now=now_fn())
                if acc is None:
                    platforms_skipped += 1
                    continue
                session_handle = get_session_credentials(acc)
                provider = provider_factory(platform)
                dtos = []
                if product.main_image_url:
                    dtos += await provider.image_search(product.main_image_url, session=session_handle)
                if product.title:
                    dtos += await provider.keyword_search(product.title, session=session_handle)
                async with session_factory() as s:
                    r = await dedup_and_upsert(s, task_id, product.id, dtos, embedder, account_id=acc.id)
                    await s.commit()
                total_candidates += r["inserted"]
            async with session_factory() as s:
                task = (await s.execute(select(CollectTask).where(CollectTask.id == task_id))).scalar_one()
                task.match_cursor = {"last_product_id": product.id}
                task.match_stats = {"products": total_products + 1, "candidates": total_candidates, "platforms_skipped": platforms_skipped}
                paused = task.match_status == "paused"
                await s.commit()
        except Exception as exc:
            log.error("match_failed", product_id=product.id, error=str(exc))
            async with session_factory() as s:
                task = (await s.execute(select(CollectTask).where(CollectTask.id == task_id))).scalar_one()
                task.match_status = "failed"; await s.commit()
            break
        last_id = product.id
        total_products += 1
        if progress_cb:
            await progress_cb({"task_id": task_id, "product_id": product.id, "candidates": total_candidates})
        if paused:
            break
    return {"products": total_products, "candidates": total_candidates, "platforms_skipped": platforms_skipped}

async def run_match(ctx, task_id: int) -> dict:
    from app.core.db import async_session
    from app.services.embedding.factory import get_embedder
    from app.services.settings_store import get_value
    # 读配置选 embedder(默认 mock); 简化: 直接 mock, clip 由配置切换(Task 10 接)
    return await run_match_core(async_session, task_id, embedder=get_embedder("mock"))
```

- [ ] **Step 4: 注册 ARQ `run_match`**

改 `arq_worker.py` 的 `functions`：
```python
from app.workers.collector import run_collect
from app.workers.matcher import run_match
class WorkerSettings:
    functions = [run_collect, run_match]
    ...
```

- [ ] **Step 5: 运行确认通过 + 全套回归**

Run: `ozon-listing-auto/server/.venv/bin/python -m pytest ozon-listing-auto/server/tests -q`
Expected: PASS（0 warnings）。

- [ ] **Step 6: 提交**

```bash
git add ozon-listing-auto/server/app/workers/matcher.py ozon-listing-auto/server/app/workers/arq_worker.py ozon-listing-auto/server/tests/test_matcher.py
git commit -m "feat(m2): matcher worker(商品×平台→搜→CLIP去重入库, 断点/暂停/失败)"
```

---

## 阶段 2 · API

### Task 8: 账号池 CRUD API（cookie 加密存 / 脱敏读）

**Files:**
- Create: `ozon-listing-auto/server/app/schemas/account.py`
- Create: `ozon-listing-auto/server/app/api/accounts.py`
- Modify: `ozon-listing-auto/server/app/main.py`
- Create: `ozon-listing-auto/server/tests/test_accounts_api.py`

**Interfaces:**
- Produces（均 admin）：
  - `POST /accounts` body `{platform, label, credentials(dict), daily_limit?, min_interval_sec?}` → 创建（credentials Fernet 加密存）→ `AccountOut`（**不含 credentials**）。
  - `GET /accounts?platform=` → `list[AccountOut]`（脱敏，含 status/limit/used/cooldown）。
  - `PUT /accounts/{id}` 改 label/daily_limit/min_interval_sec/status（可选 credentials 更新）。
  - `DELETE /accounts/{id}`。
- `AccountOut`：`id,platform,label,status,daily_limit,min_interval_sec,daily_used_count,cooldown_until,risk_hits,created_at`（无凭据）。

- [ ] **Step 1: 写失败测试 `tests/test_accounts_api.py`**

```python
import pytest
from app.core.security import hash_password
from app.models import User

async def _admin(client, db_session):
    db_session.add(User(username="a", password_hash=hash_password("p"), role="admin"))
    await db_session.commit()
    tok = (await client.post("/auth/login", data={"username":"a","password":"p"})).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}

@pytest.mark.asyncio
async def test_create_list_account_no_credential_leak(client, db_session):
    h = await _admin(client, db_session)
    r = await client.post("/accounts", json={"platform":"ali1688","label":"号1","credentials":{"cookie":"secret"}}, headers=h)
    assert r.status_code == 201
    assert "credentials" not in r.json() and "secret" not in str(r.json())
    lst = await client.get("/accounts?platform=ali1688", headers=h)
    assert lst.status_code == 200 and lst.json()[0]["platform"] == "ali1688"
    assert lst.json()[0]["status"] == "active"

@pytest.mark.asyncio
async def test_account_requires_admin(client, db_session):
    from app.core.security import hash_password
    from app.models import User
    db_session.add(User(username="op", password_hash=hash_password("p"), role="operator"))
    await db_session.commit()
    tok = (await client.post("/auth/login", data={"username":"op","password":"p"})).json()["access_token"]
    r = await client.post("/accounts", json={"platform":"ali1688","credentials":{"cookie":"x"}},
                          headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 403
```

- [ ] **Step 2: 运行确认失败**

Run: `ozon-listing-auto/server/.venv/bin/python -m pytest ozon-listing-auto/server/tests/test_accounts_api.py -v`
Expected: FAIL。

- [ ] **Step 3: 写 `schemas/account.py`**

```python
"""账号池 API 的请求/响应 schema（响应不含凭据）。"""
from datetime import datetime
from pydantic import BaseModel, ConfigDict

class AccountCreate(BaseModel):
    platform: str
    label: str | None = None
    credentials: dict
    daily_limit: int = 200
    min_interval_sec: int = 6

class AccountUpdate(BaseModel):
    label: str | None = None
    daily_limit: int | None = None
    min_interval_sec: int | None = None
    status: str | None = None
    credentials: dict | None = None

class AccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    platform: str
    label: str | None
    status: str
    daily_limit: int
    min_interval_sec: int
    daily_used_count: int
    cooldown_until: datetime | None
    risk_hits: int
    created_at: datetime
```

- [ ] **Step 4: 写 `api/accounts.py`**

```python
"""账号池 CRUD（admin）：cookie/会话 Fernet 加密存, 响应脱敏。"""
import json
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.db import get_session
from app.core.crypto import encrypt
from app.api.deps import require_role
from app.models import SourceAccount, User
from app.schemas.account import AccountCreate, AccountUpdate, AccountOut

router = APIRouter(prefix="/accounts", tags=["accounts"])

@router.post("", response_model=AccountOut, status_code=201)
async def create_account(body: AccountCreate, s: AsyncSession = Depends(get_session), _: User = Depends(require_role("admin"))):
    if body.platform not in {"ali1688", "pinduoduo"}:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "非法平台")
    acc = SourceAccount(platform=body.platform, label=body.label,
                        credentials_encrypted=encrypt(json.dumps(body.credentials)),
                        daily_limit=body.daily_limit, min_interval_sec=body.min_interval_sec)
    s.add(acc); await s.commit(); await s.refresh(acc)
    return acc

@router.get("", response_model=list[AccountOut])
async def list_accounts(platform: str | None = None, s: AsyncSession = Depends(get_session), _: User = Depends(require_role("admin"))):
    q = select(SourceAccount)
    if platform:
        q = q.where(SourceAccount.platform == platform)
    return list((await s.execute(q.order_by(SourceAccount.id.desc()))).scalars().all())

@router.put("/{account_id}", response_model=AccountOut)
async def update_account(account_id: int, body: AccountUpdate, s: AsyncSession = Depends(get_session), _: User = Depends(require_role("admin"))):
    acc = (await s.execute(select(SourceAccount).where(SourceAccount.id == account_id))).scalar_one_or_none()
    if not acc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "账号不存在")
    for f in ("label", "daily_limit", "min_interval_sec", "status"):
        v = getattr(body, f)
        if v is not None:
            setattr(acc, f, v)
    if body.credentials is not None:
        acc.credentials_encrypted = encrypt(json.dumps(body.credentials))
    await s.commit(); await s.refresh(acc)
    return acc

@router.delete("/{account_id}", status_code=204)
async def delete_account(account_id: int, s: AsyncSession = Depends(get_session), _: User = Depends(require_role("admin"))):
    acc = (await s.execute(select(SourceAccount).where(SourceAccount.id == account_id))).scalar_one_or_none()
    if acc:
        await s.delete(acc); await s.commit()
```

- [ ] **Step 5: 挂路由 `main.py`**

```python
from app.api.accounts import router as accounts_router
app.include_router(accounts_router)
```

- [ ] **Step 6: 运行确认通过**

Run: `ozon-listing-auto/server/.venv/bin/python -m pytest ozon-listing-auto/server/tests/test_accounts_api.py -v`
Expected: PASS。

- [ ] **Step 7: 提交**

```bash
git add ozon-listing-auto/server/app/schemas/account.py ozon-listing-auto/server/app/api/accounts.py ozon-listing-auto/server/app/main.py ozon-listing-auto/server/tests/test_accounts_api.py
git commit -m "feat(m2): 账号池 CRUD API(admin, cookie 加密存/脱敏读)"
```

---

### Task 9: 匹配 API（start/pause/monitor）+ 候选列表 API + settings/source

**Files:**
- Create: `ozon-listing-auto/server/app/schemas/candidate.py`
- Create: `ozon-listing-auto/server/app/api/match.py`
- Create: `ozon-listing-auto/server/app/api/candidates.py`
- Modify: `ozon-listing-auto/server/app/main.py`
- Modify: `ozon-listing-auto/server/tests/conftest.py`（复用 M1 的 monkeypatch async_session；已就绪，无需改）
- Create: `ozon-listing-auto/server/tests/test_match_api.py`

**Interfaces:**
- Produces：
  - `POST /match/start?task_id=&sync=false`（operator+；sync=true 同步跑 `run_match_core`，embedder=mock、provider_factory 用 mock 工厂——见下）。
  - `POST /match/pause?task_id=`（operator+，置 `match_status="paused"`）。
  - `GET /match/monitor?task_id=`（match_status + match_stats）。
  - `GET /candidates?task_id=&ozon_product_id=&platform=&only_representative=&page=&page_size=` → `{items,total}`。
  - `GET/PUT /settings/source`（admin，复用 settings_store：`sim_threshold`/`embedder`/平台限速默认——非密文可存，用 `is_secret=False`）。

**sync 分支的 provider/embedder：** 测试环境无真实 provider，故 `/match/start?sync=true` 用 mock provider 工厂 + mock embedder。做法：`api/match.py` 从 `app.core.db.async_session`（conftest 已 monkeypatch 到测试库）跑 `run_match_core(async_session, task_id, embedder=get_embedder("mock"), provider_factory=lambda p: MockSourceProvider(platform=p))`。生产 sync=false 入队 `run_match`（真实 provider 由配置）。

- [ ] **Step 1: 写失败测试 `tests/test_match_api.py`**

```python
import pytest
from sqlalchemy import select, func
from app.core.security import hash_password
from app.models import User, CollectTask, OzonProduct, SourceAccount, SupplyCandidate
from app.core.crypto import encrypt
import json

async def _seed_and_login(client, db_session):
    db_session.add(User(username="op", password_hash=hash_password("p"), role="operator"))
    t = CollectTask(name="t", entry_type="keyword", entry_value="x", provider="mock", source_platforms=["ali1688","pinduoduo"])
    db_session.add(t); await db_session.flush()
    db_session.add(OzonProduct(task_id=t.id, sku="S0", title="p0", main_image_url="https://img/oz.jpg"))
    for plat in ["ali1688","pinduoduo"]:
        db_session.add(SourceAccount(platform=plat, credentials_encrypted=encrypt(json.dumps({"cookie":"c"})), min_interval_sec=0))
    await db_session.commit()
    tok = (await client.post("/auth/login", data={"username":"op","password":"p"})).json()["access_token"]
    return t.id, {"Authorization": f"Bearer {tok}"}

@pytest.mark.asyncio
async def test_match_start_sync_produces_candidates(client, db_session):
    tid, h = await _seed_and_login(client, db_session)
    r = await client.post(f"/match/start?task_id={tid}&sync=true", headers=h)
    assert r.status_code == 200 and r.json()["status"] == "done"
    cands = await client.get(f"/candidates?task_id={tid}", headers=h)
    assert cands.json()["total"] > 0
    platforms = {c["platform"] for c in cands.json()["items"]}
    assert platforms == {"ali1688","pinduoduo"}

@pytest.mark.asyncio
async def test_candidates_only_representative_filter(client, db_session):
    tid, h = await _seed_and_login(client, db_session)
    await client.post(f"/match/start?task_id={tid}&sync=true", headers=h)
    reps = await client.get(f"/candidates?task_id={tid}&only_representative=true", headers=h)
    assert all(c["is_representative"] for c in reps.json()["items"])
```

- [ ] **Step 2: 运行确认失败**

Run: `ozon-listing-auto/server/.venv/bin/python -m pytest ozon-listing-auto/server/tests/test_match_api.py -v`
Expected: FAIL。

- [ ] **Step 3: 写 `schemas/candidate.py`**

```python
"""货源候选 API 响应 schema。"""
from datetime import datetime
from pydantic import BaseModel, ConfigDict

class CandidateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    ozon_product_id: int
    platform: str
    offer_id: str
    title: str | None
    price: float | None
    currency: str | None
    quantity_begin: int | None
    image_url: str | None
    detail_url: str | None
    supplier_name: str | None
    supplier_info: dict | None
    dedup_group: int | None
    is_representative: bool
    status: str
```

- [ ] **Step 4: 写 `api/match.py`**

```python
"""货源匹配控制 API：启动(同步/入队)/暂停/监控。"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import app.core.db as dbmod
from app.core.db import get_session
from app.api.deps import require_role
from app.models import CollectTask, User
from app.workers.matcher import run_match_core
from app.services.embedding.factory import get_embedder
from app.services.sources.mock import MockSourceProvider

router = APIRouter(prefix="/match", tags=["match"])

@router.post("/start")
async def start_match(task_id: int, sync: bool = False, s: AsyncSession = Depends(get_session), _: User = Depends(require_role("operator"))):
    t = (await s.execute(select(CollectTask).where(CollectTask.id == task_id))).scalar_one_or_none()
    if not t:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "任务不存在")
    if sync:
        await run_match_core(dbmod.async_session, task_id, embedder=get_embedder("mock"),
                             provider_factory=lambda p: MockSourceProvider(platform=p))
        return {"status": "done"}
    from arq import create_pool
    from arq.connections import RedisSettings
    from app.core.config import settings
    pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    try:
        await pool.enqueue_job("run_match", task_id)
    finally:
        await pool.aclose()
    return {"status": "queued"}

@router.post("/pause")
async def pause_match(task_id: int, s: AsyncSession = Depends(get_session), _: User = Depends(require_role("operator"))):
    t = (await s.execute(select(CollectTask).where(CollectTask.id == task_id))).scalar_one_or_none()
    if not t:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "任务不存在")
    t.match_status = "paused"; await s.commit()
    return {"ok": True}

@router.get("/monitor")
async def match_monitor(task_id: int, s: AsyncSession = Depends(get_session), _: User = Depends(require_role("operator"))):
    t = (await s.execute(select(CollectTask).where(CollectTask.id == task_id))).scalar_one_or_none()
    if not t:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "任务不存在")
    return {"match_status": t.match_status, "match_stats": t.match_stats}
```

- [ ] **Step 5: 写 `api/candidates.py`**

```python
"""货源候选查询 API（分页/按平台/仅代表）。"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.db import get_session
from app.api.deps import get_current_user
from app.models import SupplyCandidate, User
from app.schemas.candidate import CandidateOut

router = APIRouter(prefix="/candidates", tags=["candidates"])

@router.get("")
async def list_candidates(task_id: int, ozon_product_id: int | None = None, platform: str | None = None,
                          only_representative: bool = False, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=200),
                          s: AsyncSession = Depends(get_session), _: User = Depends(get_current_user)):
    conds = [SupplyCandidate.task_id == task_id]
    if ozon_product_id is not None:
        conds.append(SupplyCandidate.ozon_product_id == ozon_product_id)
    if platform:
        conds.append(SupplyCandidate.platform == platform)
    if only_representative:
        conds.append(SupplyCandidate.is_representative.is_(True))
    base = select(SupplyCandidate).where(*conds)
    total = (await s.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    rows = (await s.execute(base.order_by(SupplyCandidate.id.desc()).offset((page-1)*page_size).limit(page_size))).scalars().all()
    return {"items": [CandidateOut.model_validate(r) for r in rows], "total": total}
```

- [ ] **Step 6: 挂路由 `main.py`**

```python
from app.api.match import router as match_router
from app.api.candidates import router as candidates_router
app.include_router(match_router)
app.include_router(candidates_router)
```

- [ ] **Step 7: 运行确认通过 + 全套回归**

Run: `ozon-listing-auto/server/.venv/bin/python -m pytest ozon-listing-auto/server/tests -q`
Expected: PASS（0 warnings）。

- [ ] **Step 8: 提交**

```bash
git add ozon-listing-auto/server/app/schemas/candidate.py ozon-listing-auto/server/app/api/match.py ozon-listing-auto/server/app/api/candidates.py ozon-listing-auto/server/app/main.py ozon-listing-auto/server/tests/test_match_api.py
git commit -m "feat(m2): 匹配 API(start 同步/入队+pause+monitor) + 候选列表 API"
```

（`settings/source` 复用现有 `/settings/{category}` 通用端点即可，无需新代码；阈值/embedder 存 category='source'。若需非密文存储，后续可加 is_secret=False 支持——M2 先用现有加密存亦可。）

---

## 阶段 3 · 真实 provider + Docker + 文档

### Task 10: Ali1688Provider 真实(httpx+cookie 图搜) + ChineseClipEmbedder 真实 + pyproject[ml]

**Files:**
- Create: `ozon-listing-auto/server/app/services/sources/parser_ali.py`
- Modify: `ozon-listing-auto/server/app/services/sources/ali1688.py`
- Modify: `ozon-listing-auto/server/app/services/embedding/clip.py`
- Create: `ozon-listing-auto/server/app/fixtures/ali_search_sample.json`
- Create: `ozon-listing-auto/server/tests/test_ali_parser.py`
- Create: `ozon-listing-auto/server/tests/test_source_live.py`（`@pytest.mark.live` 默认跳过）

**Interfaces:**
- Produces:
  - `parser_ali.parse_image_search(payload) -> list[SupplyCandidateDTO]`（从 1688 图搜返回 JSON 抽字段，参考 Zhui-CN 结构：offer_id/price/起批量/阶梯价/复购率/信用/注册资本/省市/验厂标签/分项评分；容错缺字段）。
  - `Ali1688Provider`（httpx + cookie 会话，拍立淘图搜为主 + 关键词；请求层与解析层分离；真实联调 live 默认跳过）。
  - `ChineseClipEmbedder`（懒加载 cn_clip ViT-B/16 CPU；`embed_image` 下载图→向量 512 维；失败重试）。

- [ ] **Step 1: 准备解析样本 `fixtures/ali_search_sample.json`**

放一段精简的 1688 图搜返回结构（含 2 条商品的最小字段，参考 Zhui-CN 输出）：
```json
{"data": {"offerList": [
  {"offerId": 1001, "subject": "无线耳机", "priceInfo": {"price": "12.50"}, "quantityBegin": 2,
   "company": {"name": "深圳某厂", "creditLevel": "AAA", "regCapital": "500万", "province": "广东", "city": "深圳",
      "repurchaseRate": "45.45%", "positionLabels": ["深度验厂"], "scores": {"comprehensive": 4.8}},
   "detailUrl": "https://1688/1001", "imageUrl": "https://img/e.jpg"},
  {"offerId": 1002, "subject": "键盘", "priceInfo": {"price": "45.00"}, "detailUrl": "https://1688/1002", "imageUrl": "https://img/k.jpg"}
]}}
```
（真实字段名以实际抓包为准；解析器以此样本为契约，联调时同步调整。）

- [ ] **Step 2: 写失败测试 `tests/test_ali_parser.py`**

```python
import json
from pathlib import Path
from app.services.sources.parser_ali import parse_image_search

def _load():
    p = Path(__file__).resolve().parents[1] / "app" / "fixtures" / "ali_search_sample.json"
    return json.loads(p.read_text(encoding="utf-8"))

def test_parse_image_search():
    dtos = parse_image_search(_load())
    assert len(dtos) == 2
    a = next(d for d in dtos if d.offer_id == "1001")
    assert a.platform == "ali1688"
    assert a.price == 12.5 and a.quantity_begin == 2
    assert a.supplier_name == "深圳某厂"
    assert a.supplier_info["credit_level"] == "AAA"
    assert a.supplier_info["repurchase_rate"] == 0.4545        # "45.45%" → 0.4545
    # 缺字段容错
    b = next(d for d in dtos if d.offer_id == "1002")
    assert b.supplier_name is None or isinstance(b.supplier_info, dict)
```

- [ ] **Step 3: 运行确认失败**

Run: `ozon-listing-auto/server/.venv/bin/python -m pytest ozon-listing-auto/server/tests/test_ali_parser.py -v`
Expected: FAIL。

- [ ] **Step 4: 写 `parser_ali.py`**

```python
"""1688 图搜返回 → SupplyCandidateDTO 解析（字段参考 Zhui-CN；容错缺字段）。"""
import re
from app.services.sources.base import SupplyCandidateDTO

def _price(v) -> float | None:
    if v is None:
        return None
    m = re.search(r"[\d.]+", str(v))
    return float(m.group()) if m else None

def _rate(v) -> float | None:
    if v is None:
        return None
    m = re.search(r"[\d.]+", str(v))
    return round(float(m.group()) / 100, 4) if m else None

def parse_image_search(payload: dict) -> list[SupplyCandidateDTO]:
    out: list[SupplyCandidateDTO] = []
    for it in (payload.get("data", {}) or {}).get("offerList", []) or []:
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
```

- [ ] **Step 5: 运行确认通过**

Run: `ozon-listing-auto/server/.venv/bin/python -m pytest ozon-listing-auto/server/tests/test_ali_parser.py -v`
Expected: PASS。

- [ ] **Step 6: 写真实 `ali1688.py`**

```python
"""Ali1688Provider：httpx + cookie 拍立淘图搜为主 + 关键词；请求层与解析层分离。"""
import httpx
from app.services.sources.base import SupplyCandidateDTO
from app.services.sources.parser_ali import parse_image_search

_IMAGE_SEARCH_URL = "https://s.1688.com/youyuan/index.htm"   # 占位, 联调以实际图搜端点为准

class Ali1688Provider:
    platform = "ali1688"
    def __init__(self, timeout: float = 20.0):
        self._timeout = timeout

    def _client(self, session) -> httpx.AsyncClient:
        cookies = (session or {}).get("cookie") if isinstance(session, dict) else None
        headers = {"User-Agent": "Mozilla/5.0"}
        return httpx.AsyncClient(timeout=self._timeout, headers=headers,
                                 cookies={"cookie2": cookies} if cookies else None)

    async def image_search(self, image_url: str, *, session) -> list[SupplyCandidateDTO]:
        async with self._client(session) as c:
            r = await c.get(_IMAGE_SEARCH_URL, params={"imageAddress": image_url})
            r.raise_for_status()
            return parse_image_search(r.json())
    async def keyword_search(self, kw: str, *, session) -> list[SupplyCandidateDTO]:
        async with self._client(session) as c:
            r = await c.get("https://s.1688.com/selloffer/offer_search.htm", params={"keywords": kw})
            r.raise_for_status()
            return parse_image_search(r.json())
    async def fetch_detail(self, offer_id: str, *, session) -> SupplyCandidateDTO:
        return SupplyCandidateDTO(platform="ali1688", offer_id=offer_id)
```

- [ ] **Step 7: 写真实 `clip.py`（懒加载）**

```python
"""ChineseClipEmbedder：cn_clip ViT-B/16 CPU 推理，懒加载，图 URL → 512 维向量。"""
import io
from app.models.supply_candidate import EMBED_DIM

class ChineseClipEmbedder:
    dim = EMBED_DIM
    def __init__(self):
        self._model = None
        self._preprocess = None

    def _load(self):
        if self._model is None:
            import torch
            import cn_clip.clip as clip
            from cn_clip.clip import load_from_name
            self._torch = torch
            self._model, self._preprocess = load_from_name("ViT-B-16", device="cpu")
            self._model.eval()

    async def embed_image(self, image_url: str) -> list[float]:
        import httpx
        from PIL import Image
        self._load()
        async with httpx.AsyncClient(timeout=20.0) as c:
            r = await c.get(image_url); r.raise_for_status()
            img = Image.open(io.BytesIO(r.content)).convert("RGB")
        tensor = self._preprocess(img).unsqueeze(0)
        with self._torch.no_grad():
            feat = self._model.encode_image(tensor)
            feat = feat / feat.norm(dim=-1, keepdim=True)
        return feat[0].tolist()
    async def embed_images(self, urls: list[str]) -> list[list[float]]:
        return [await self.embed_image(u) for u in urls]
```

- [ ] **Step 8: pyproject 确认 `[ml]` 组含 torch/cn_clip/pillow（Task 1 已加）；写 live 冒烟 `tests/test_source_live.py`**

```python
import pytest
from app.services.sources.ali1688 import Ali1688Provider

@pytest.mark.live
@pytest.mark.asyncio
async def test_ali_image_search_live():
    p = Ali1688Provider()
    items = await p.keyword_search("耳机", session=None)
    assert isinstance(items, list)
    print(f"1688 live 采到 {len(items)} 条")
```
（`live` marker 与 `addopts='-m \"not live\"'` 已在 M1 的 pyproject 配置，无需重复。）

- [ ] **Step 9: 运行非 live 全套确认通过**

Run: `ozon-listing-auto/server/.venv/bin/python -m pytest ozon-listing-auto/server/tests -q`
Expected: PASS（0 warnings；live 跳过；未装 torch 也不影响——clip.py 的 torch import 在方法内，非模块顶层）。

- [ ] **Step 10: 提交**

```bash
git add ozon-listing-auto/server/app/services/sources/parser_ali.py ozon-listing-auto/server/app/services/sources/ali1688.py ozon-listing-auto/server/app/services/embedding/clip.py ozon-listing-auto/server/app/fixtures/ali_search_sample.json ozon-listing-auto/server/tests/test_ali_parser.py ozon-listing-auto/server/tests/test_source_live.py
git commit -m "feat(m2): Ali1688Provider(httpx+cookie 图搜)+解析器 + ChineseClipEmbedder(懒加载) + live 冒烟"
```

---

### Task 11: PinduoduoProvider 真实(selenium+代理, 一期关键词)

**Files:**
- Modify: `ozon-listing-auto/server/app/services/sources/pinduoduo.py`
- Create: `ozon-listing-auto/server/tests/test_pdd_provider.py`

**Interfaces:**
- Produces: `PinduoduoProvider`：`keyword_search` 走 selenium/playwright + 代理截获移动端 API 返回 JSON（一期实现关键词）；`image_search` 先 `NotImplementedError`（图搜后补）；解析层独立函数便于测试。真实联调 `@pytest.mark.live` 默认跳过。M2 不引入 selenium 到测试路径——测试只验证「image_search 抛 NotImplementedError」「解析函数对样本 JSON 正确」。

- [ ] **Step 1: 写失败测试 `tests/test_pdd_provider.py`**

```python
import pytest
from app.services.sources.pinduoduo import PinduoduoProvider, parse_pdd_items

@pytest.mark.asyncio
async def test_pdd_image_search_not_implemented_yet():
    p = PinduoduoProvider()
    with pytest.raises(NotImplementedError):
        await p.image_search("https://img/x.jpg", session=None)

def test_parse_pdd_items():
    payload = {"items": [{"goods_id": "G1", "goods_name": "耳机", "min_group_price": 1390,
                          "thumb_url": "https://pdd/g1.jpg", "mall_name": "店A"}]}
    dtos = parse_pdd_items(payload)
    assert len(dtos) == 1
    assert dtos[0].platform == "pinduoduo" and dtos[0].offer_id == "G1"
    assert dtos[0].price == 13.9            # 分→元
    assert dtos[0].supplier_name == "店A"
```

- [ ] **Step 2: 运行确认失败**

Run: `ozon-listing-auto/server/.venv/bin/python -m pytest ozon-listing-auto/server/tests/test_pdd_provider.py -v`
Expected: FAIL。

- [ ] **Step 3: 写 `pinduoduo.py`**

```python
"""PinduoduoProvider：selenium/playwright + 代理截获移动端 API(一期先关键词, 不逆向 anti_content)。"""
from app.services.sources.base import SupplyCandidateDTO

def parse_pdd_items(payload: dict) -> list[SupplyCandidateDTO]:
    """解析截获的拼多多商品 JSON（价格为分, /100 得元）。"""
    out: list[SupplyCandidateDTO] = []
    for it in payload.get("items", []) or []:
        gid = it.get("goods_id")
        if gid is None:
            continue
        price = it.get("min_group_price")
        out.append(SupplyCandidateDTO(
            platform="pinduoduo", offer_id=str(gid), title=it.get("goods_name"),
            price=(price / 100.0) if isinstance(price, (int, float)) else None, currency="CNY",
            image_url=it.get("thumb_url"), detail_url=it.get("detail_url"),
            supplier_name=it.get("mall_name"), supplier_info={}, raw=it,
        ))
    return out

class PinduoduoProvider:
    platform = "pinduoduo"
    async def image_search(self, image_url: str, *, session) -> list[SupplyCandidateDTO]:
        raise NotImplementedError("拼多多图搜一期不做（签名复杂），后续增强；一期用 keyword_search")
    async def keyword_search(self, kw: str, *, session) -> list[SupplyCandidateDTO]:
        # 真实实现: selenium/playwright 打开移动端搜索 + 代理截获返回 JSON → parse_pdd_items
        # 一期真实联调走 live 测试; 此处返回空占位, 避免无 selenium 环境报错
        raise NotImplementedError("拼多多关键词搜索需 selenium+代理环境, 走 live 联调")
    async def fetch_detail(self, offer_id: str, *, session) -> SupplyCandidateDTO:
        return SupplyCandidateDTO(platform="pinduoduo", offer_id=offer_id)
```

说明：M2 拼多多真实抓取依赖 selenium+代理运行环境，不进单测/CI；单测只覆盖解析函数 + 未实现分支。真实 `keyword_search` 的 selenium+截流实现在有代理环境时补（可另起 live 测试）。matcher 在 mock 模式用 `MockSourceProvider("pinduoduo")`，故 M2 全链路 mock 可跑通双平台候选，不受此影响。

- [ ] **Step 4: 运行确认通过**

Run: `ozon-listing-auto/server/.venv/bin/python -m pytest ozon-listing-auto/server/tests/test_pdd_provider.py -v`
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add ozon-listing-auto/server/app/services/sources/pinduoduo.py ozon-listing-auto/server/tests/test_pdd_provider.py
git commit -m "feat(m2): PinduoduoProvider(解析函数+一期关键词占位, selenium+代理 live 补)"
```

---

### Task 12: Docker(worker ML) + README/docs M2 + 全量回归

**Files:**
- Modify: `ozon-listing-auto/server/Dockerfile`（`ARG INSTALL_ML`）
- Modify: `ozon-listing-auto/docker-compose.yml`（worker `build.args: INSTALL_ML=true`）
- Modify: `ozon-listing-auto/README.md`（M2 段）
- Create: `ozon-listing-auto/docs/M2-货源匹配说明.md`

**Interfaces:**
- Produces: worker 镜像装 ML(torch/cn_clip)、api 不装；默认 embedder=mock 可不装 ML 跑通；文档更新。

- [ ] **Step 1: 改 `server/Dockerfile` 支持条件装 ML**

```dockerfile
FROM python:3.11-slim
WORKDIR /app
ARG INSTALL_ML=false
COPY pyproject.toml ./
RUN if [ "$INSTALL_ML" = "true" ]; then pip install --no-cache-dir -e ".[dev,ml]"; else pip install --no-cache-dir -e ".[dev]"; fi
COPY . .
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
```

- [ ] **Step 2: 改 `docker-compose.yml` worker 装 ML**

worker 服务 `build` 改为：
```yaml
  worker:
    build:
      context: ./server
      args:
        INSTALL_ML: "true"
    command: sh -c "arq app.workers.arq_worker.WorkerSettings"
    environment:
      ...(保持原有 DATABASE_URL/REDIS_URL/FERNET_KEY)
      EMBEDDER: ${EMBEDDER:-mock}
    depends_on:
      db: {condition: service_healthy}
      redis: {condition: service_started}
```
（`api` 服务 build 保持默认 INSTALL_ML=false。`.env.example` 增 `EMBEDDER=mock` 一行。）

- [ ] **Step 3: 更新 `README.md` M2 段 + 写 `docs/M2-货源匹配说明.md`**

README 增 M2 功能：双源货源匹配(1688 httpx 图搜 / 拼多多 selenium+代理关键词, 默认 mock)、账号池(cookie 加密)、CLIP 跨平台去重(默认 mock embedder, clip 需 worker ML 镜像)、匹配/候选/账号 API。
`docs/M2-货源匹配说明.md`：流程——建账号(/accounts)→采集(M1)→/match/start(mock 跑通)→/candidates 看双平台候选→切真实(配 cookie + embedder=clip + worker ML)。

- [ ] **Step 4: 全量回归**

Run: `ozon-listing-auto/server/.venv/bin/python -m pytest ozon-listing-auto/server/tests -q`
Expected: PASS（0 warnings；live 跳过）。前端无改动。

- [ ] **Step 5: 提交**

```bash
git add ozon-listing-auto/server/Dockerfile ozon-listing-auto/docker-compose.yml ozon-listing-auto/README.md ozon-listing-auto/docs/M2-货源匹配说明.md ozon-listing-auto/.env.example
git commit -m "feat(m2): Docker worker 装 ML(cn_clip) + README/docs M2"
```

---

## 验收对照（spec §8）

| 验收项 | 覆盖任务 |
|---|---|
| 迁移 0002 建表 + match_* + 向量列 | Task 1 |
| docker compose up(mock) + /accounts CRUD(加密/脱敏) | Task 8, 12 |
| 采集→/match/start→每商品双平台候选落 supply_candidates | Task 3,5,7,9 |
| 跨平台 CLIP 去重(近似折叠代表+双平台不同款保留, 阈值可配) | Task 4,5 |
| 账号池限速/冷却/换号, 风控不中断, 断点/暂停/失败 | Task 6,7 |
| MockEmbedder 全链路 + ChineseClipEmbedder 配置切换 + 真实 provider live 跳过 | Task 4,10,11 |
| 非 live 测试全绿 0 warnings + README/docs | Task 12 |

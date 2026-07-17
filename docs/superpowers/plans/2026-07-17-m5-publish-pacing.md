# M5 上架节奏调度 + Redis 实时进度 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 M4 的"确认后直接挂靠"升级为"确认→排期(scheduled_at)→周期 tick 逐一按节奏挂靠(随机间隔/时段/日限/等审核)"，并把内存 Broadcaster 升级为后端可选(memory/Redis pub/sub)以支持 worker→API 跨进程实时进度，配 PublishMonitor 监控页。验收「逐一按节奏上架、可视」。

**Architecture:** 沿用 mock-first + 配置驱动。新增 publish_pace 表(三级回退); publish_scheduler(plan_schedule 排 scheduled_at + next_active_window); tick_publish(等审核门 + 逐一挂靠); OzonSeller 加 get_product_status; core/progress.py Broadcaster 后端可选(memory 默认/redis pub/sub); PublishMonitor 前端(首个前端 WS 客户端)。测试全走 mock(memory 后端 + mock seller + 注入 now/rng, 无真 Redis/Ozon)。

**Tech Stack:** 承接 M1-M4。progress redis 后端复用已装 `redis`(redis.asyncio)。ARQ cron 用 arq 的 cron。

## Global Constraints

- Python 3.11; 后端全异步; worker 幂等。
- DEFAULT_PACE = {min_interval_sec:60, max_interval_sec:180, daily_limit:200, active_hours:[9,23], wait_ozon_approval:True}。pace 三级回退: 任务 pace → 全局 pace(task_id null) → DEFAULT_PACE。
- 草稿状态流: draft→confirmed→scheduled→publishing→published|pending_review|failed(+M4 的 below_min)。scheduled/pending_review 是新增字符串值(无迁移)。
- plan_schedule 确定性(注入 now + 种子 rng): 每条 cursor += rng.randint(min,max)秒 → next_active_window(落 [start,end) 否则滚下个时段起点) → daily_limit 超额滚次日; 置 scheduled_at + status='scheduled'。
- tick_publish 等审核门: 存在 status='pending_review' → get_product_status: pending→waiting 不推下条; approved→published; rejected→failed。仅无 pending_review 才推下一条到期(scheduled 且 scheduled_at<=now, max_batch=1)。挂靠 ok: wait_ozon_approval 则 pending_review 否则 published。单条失败隔离。
- Broadcaster: `publish(msg)` 按 settings.progress_backend 路由(memory→本地 fan-out; redis→redis.publish("ws:progress")); redis 后端 API lifespan 起订阅任务 fan-out。现有 broadcaster.publish 调用点(M1-M4)无感。测试用 memory。
- ozon_seller 名枚举 mock/real; seller 加 get_product_status(client_id/api_key/ozon_product_id)→approved|pending|rejected; MockOzonSeller 默认 approved, 可注入 pending_ids。
- 角色: pace/schedule → operator+; tick → publisher+; monitor → 认证; admin 超级通过。
- 敏感信息 Fernet; structlog 带 task_id; 中文注释/每模块一行中文 docstring。
- 迁移列有 server_default 且 ORM NOT NULL 的必须 nullable=False(M2-M4 教训)。
- TDD; pytest 0 warnings; 测试全走 mock(无真 Redis/Ozon/网络)。
- 代码库 `ozon-listing-auto/`; venv `ozon-listing-auto/server/.venv`(3.11); 跑测试 `.venv/bin/python -m pytest`(勿用系统 python3=3.9); Node via nvm。
- 建立在 M4 之上: 复用 ListingDraft(status/scheduled_at/shop_id/candidate_id/ozon_result, M4)、Shop(Fernet 凭据)、OzonSellerProvider(create_follow_offer, M4)、crypto.decrypt、run_publish_core 的单条失败隔离范式、CollectTask、api/deps、conftest(内存 SQLite + monkeypatch async_session)、live marker、ConfigDict/Query(ge=1)/HTTP_*_CONTENT。

## 文件结构

```
server/app/
├── models/publish_pace.py
├── alembic/versions/0005_m5_publish_pacing.py
├── schemas/pace.py
├── api/{pace.py, publish.py}
├── core/{progress.py(改造), config.py(+progress_backend)}
├── services/{publish_scheduler.py, ozon_seller/{base.py,mock.py,real.py}(+get_product_status)}
└── workers/{publisher.py(+tick_publish+run_publish_tick), arq_worker.py(+cron)}
web/src/{pages/PublishMonitor.tsx, api/pace.ts, api/publish.ts, App.tsx(+route), pages/Layout.tsx(+menu)}
server/tests/{test_pace_models.py, test_progress_backend.py, test_ozon_seller_status.py,
              test_publish_scheduler.py, test_tick_publish.py, test_pace_api.py, test_publish_api.py}
```

---

## 阶段 0 · Schema + Broadcaster 改造

### Task 1: 迁移 0005 + publish_pace ORM

**Files:**
- Create: `ozon-listing-auto/server/app/models/publish_pace.py`
- Modify: `ozon-listing-auto/server/app/models/__init__.py`
- Create: `ozon-listing-auto/server/alembic/versions/0005_m5_publish_pacing.py`
- Create: `ozon-listing-auto/server/tests/test_pace_models.py`

**Interfaces:**
- Produces: `PublishPace` ORM(task_id null 可, min/max_interval_sec, daily_limit, active_hours jsonb, wait_ozon_approval)。

- [ ] **Step 1: 写 `models/publish_pace.py`**

```python
"""上架节奏配置 ORM(全局默认 task_id=null; 按任务覆盖)。"""
from datetime import datetime
from sqlalchemy import Integer, Boolean, DateTime, ForeignKey, JSON, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db import Base

_JSONB = JSONB().with_variant(JSON(), "sqlite")

class PublishPace(Base):
    __tablename__ = "publish_pace"
    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int | None] = mapped_column(ForeignKey("collect_tasks.id"), nullable=True, index=True)
    min_interval_sec: Mapped[int] = mapped_column(Integer, default=60)
    max_interval_sec: Mapped[int] = mapped_column(Integer, default=180)
    daily_limit: Mapped[int] = mapped_column(Integer, default=200)
    active_hours: Mapped[list] = mapped_column(_JSONB, default=lambda: [9, 23])
    wait_ozon_approval: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
```

- [ ] **Step 2: 改 `models/__init__.py` 导出 `PublishPace`(import + __all__)**

- [ ] **Step 3: 写失败测试 `tests/test_pace_models.py`**

```python
import pytest
from sqlalchemy import select
from app.models import PublishPace, CollectTask

@pytest.mark.asyncio
async def test_publish_pace(db_session):
    t = CollectTask(name="t", entry_type="keyword", entry_value="x", provider="mock", source_platforms=["ali1688"])
    db_session.add(t); await db_session.flush()
    p = PublishPace(task_id=t.id, min_interval_sec=30, max_interval_sec=90, daily_limit=50, active_hours=[8, 22])
    db_session.add(p)
    g = PublishPace(task_id=None)  # 全局默认
    db_session.add(g); await db_session.commit()
    got = (await db_session.execute(select(PublishPace).where(PublishPace.task_id == t.id))).scalar_one()
    assert got.min_interval_sec == 30 and got.active_hours == [8, 22] and got.wait_ozon_approval is True
    assert g.daily_limit == 200 and g.active_hours == [9, 23]
```

- [ ] **Step 4: 运行确认失败**

Run: `ozon-listing-auto/server/.venv/bin/python -m pytest ozon-listing-auto/server/tests/test_pace_models.py -v`
Expected: FAIL。

- [ ] **Step 5: 写迁移 `0005_m5_publish_pacing.py`**

```python
"""m5 publish pacing"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0005"
down_revision = "0004"

def upgrade():
    op.create_table("publish_pace",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("task_id", sa.Integer, sa.ForeignKey("collect_tasks.id"), index=True),
        sa.Column("min_interval_sec", sa.Integer, server_default="60", nullable=False),
        sa.Column("max_interval_sec", sa.Integer, server_default="180", nullable=False),
        sa.Column("daily_limit", sa.Integer, server_default="200", nullable=False),
        sa.Column("active_hours", postgresql.JSONB, server_default="[9, 23]", nullable=False),
        sa.Column("wait_ozon_approval", sa.Boolean, server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

def downgrade():
    op.drop_table("publish_pace")
```

注意 ORM 的 `min_interval_sec` 等是 `Mapped[int]`(NOT NULL)且有 Python `default`；迁移用 `server_default` + `nullable=False` 对齐(active_hours 用 server_default JSON 字符串)。

- [ ] **Step 6: 运行确认通过 + 全套回归**

Run: `ozon-listing-auto/server/.venv/bin/python -m pytest ozon-listing-auto/server/tests -q`
Expected: PASS(0 warnings)。

- [ ] **Step 7: 提交**

```bash
git add ozon-listing-auto/server/app/models/publish_pace.py ozon-listing-auto/server/app/models/__init__.py ozon-listing-auto/server/alembic/versions/0005_m5_publish_pacing.py ozon-listing-auto/server/tests/test_pace_models.py
git commit -m "feat(m5): 迁移0005 + publish_pace ORM(节奏配置)"
```

---

### Task 2: Broadcaster 后端可选（memory / Redis pub/sub）

**Files:**
- Modify: `ozon-listing-auto/server/app/core/config.py`(加 progress_backend)
- Modify: `ozon-listing-auto/server/app/core/progress.py`
- Modify: `ozon-listing-auto/server/app/main.py`(lifespan 起 redis 订阅, 仅 redis 后端)
- Create: `ozon-listing-auto/server/tests/test_progress_backend.py`

**Interfaces:**
- Produces: `Broadcaster.publish(msg)` 后端可选(memory→本地 fan-out; redis→redis.publish); `Broadcaster.connect/disconnect`(不变); `Broadcaster.start_redis_subscriber()`(redis 后端订阅→本地 fan-out); `settings.progress_backend`。

**关键:** 读现有 `core/progress.py`——它有 `Broadcaster`(connect/disconnect/publish 本地 fan-out)与单例 `broadcaster`。改造保持 connect/disconnect 与 publish 的签名不变, publish 内部按后端路由; 内部本地 fan-out 抽成 `_local_broadcast`。M1-M4 的 `broadcaster.publish(...)` 无需改。

- [ ] **Step 1: 读 `core/progress.py` 确认现有结构**

先读该文件, 记录 `Broadcaster` 现有 connect/disconnect/publish 实现(本地 fan-out 逻辑)。

- [ ] **Step 2: 加 config `progress_backend`**

`app/core/config.py` Settings 加：
```python
    progress_backend: str = "memory"   # memory | redis
```

- [ ] **Step 3: 写失败测试 `tests/test_progress_backend.py`**

```python
import pytest
from app.core.progress import Broadcaster

@pytest.mark.asyncio
async def test_memory_backend_local_broadcast(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.progress_backend", "memory", raising=False)
    b = Broadcaster()
    got = []
    class FakeWS:
        async def send_json(self, m): got.append(m)
    b._conns.add(FakeWS())          # 直接注入一个假连接
    await b.publish({"x": 1})
    assert got == [{"x": 1}]         # memory 后端: 直接本地 fan-out

@pytest.mark.asyncio
async def test_redis_backend_routes_to_redis(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.progress_backend", "redis", raising=False)
    published = []
    class FakeRedis:
        async def publish(self, ch, data): published.append((ch, data))
    b = Broadcaster()
    b._redis = FakeRedis()          # 注入假 redis
    local = []
    class FakeWS:
        async def send_json(self, m): local.append(m)
    b._conns.add(FakeWS())
    await b.publish({"y": 2})
    assert published and published[0][0] == "ws:progress"   # redis 后端: 走 redis.publish
    assert local == []                                       # 不直接本地 fan-out(靠订阅回来)
```

（注：测试直接操作 `b._conns`/`b._redis` 内部——实现需暴露这两个属性名。若现有连接集合名不同, 调整测试与实现一致。）

- [ ] **Step 4: 运行确认失败**

Run: `ozon-listing-auto/server/.venv/bin/python -m pytest ozon-listing-auto/server/tests/test_progress_backend.py -v`
Expected: FAIL。

- [ ] **Step 5: 改造 `core/progress.py`**

改造后结构(保持 connect/disconnect 与既有 publish 签名)：
```python
"""WS 进度广播：后端可选(memory 本地 fan-out / redis pub/sub 跨进程)。"""
import json
from app.core.config import settings

CHANNEL = "ws:progress"

class Broadcaster:
    def __init__(self):
        self._conns: set = set()
        self._redis = None

    async def connect(self, ws):
        await ws.accept()
        self._conns.add(ws)

    def disconnect(self, ws):
        self._conns.discard(ws)

    async def _local_broadcast(self, msg: dict):
        dead = []
        for ws in list(self._conns):
            try:
                await ws.send_json(msg)
            except Exception:  # noqa: BLE001
                dead.append(ws)
        for ws in dead:
            self._conns.discard(ws)

    async def _get_redis(self):
        if self._redis is None:
            from redis.asyncio import from_url
            self._redis = from_url(settings.redis_url)
        return self._redis

    async def publish(self, msg: dict):
        if settings.progress_backend == "redis":
            r = await self._get_redis()
            await r.publish(CHANNEL, json.dumps(msg))
        else:
            await self._local_broadcast(msg)

    async def start_redis_subscriber(self):
        """redis 后端: API 侧订阅频道, 收到消息本地 fan-out 到 WS 连接。"""
        r = await self._get_redis()
        pubsub = r.pubsub()
        await pubsub.subscribe(CHANNEL)
        async for message in pubsub.listen():
            if message.get("type") == "message":
                try:
                    await self._local_broadcast(json.loads(message["data"]))
                except Exception:  # noqa: BLE001
                    pass

broadcaster = Broadcaster()
```
（若现有 `Broadcaster` 用 `_lock` 或不同的连接管理, 保留其风格, 仅按上面增加后端路由 + `_local_broadcast` + `_get_redis` + `start_redis_subscriber`; 保证既有 WS 测试与 M1-M4 调用不破。connect/disconnect 若现有是 async/sync, 保持不变。）

- [ ] **Step 6: main.py lifespan 起 redis 订阅(仅 redis 后端)**

在 `main.py` 的 lifespan 内(ensure_admin 之后)加：
```python
    import asyncio
    from app.core.config import settings
    from app.core.progress import broadcaster
    if settings.progress_backend == "redis":
        asyncio.create_task(broadcaster.start_redis_subscriber())
```
（memory 后端不起订阅。测试环境默认 memory, 不受影响。）

- [ ] **Step 7: 运行确认通过 + 全套回归**

Run: `ozon-listing-auto/server/.venv/bin/python -m pytest ozon-listing-auto/server/tests -q`
Expected: PASS(0 warnings; 既有 WS/collect/matcher/scorer 测试仍绿——它们走 memory 后端本地 fan-out)。

- [ ] **Step 8: 提交**

```bash
git add ozon-listing-auto/server/app/core/progress.py ozon-listing-auto/server/app/core/config.py ozon-listing-auto/server/app/main.py ozon-listing-auto/server/tests/test_progress_backend.py
git commit -m "feat(m5): Broadcaster 后端可选(memory/redis pub/sub 跨进程)"
```

---

## 阶段 1 · 调度核心

### Task 3: OzonSeller 加 get_product_status

**Files:**
- Modify: `ozon-listing-auto/server/app/services/ozon_seller/base.py`
- Modify: `ozon-listing-auto/server/app/services/ozon_seller/mock.py`
- Modify: `ozon-listing-auto/server/app/services/ozon_seller/real.py`
- Create: `ozon-listing-auto/server/tests/test_ozon_seller_status.py`

**Interfaces:**
- Produces: `OzonSellerProvider.get_product_status(*, client_id, api_key, ozon_product_id) -> str`(approved|pending|rejected); `MockOzonSeller(pending_ids=None)`(默认 approved, pending_ids 里的返 pending); `RealOzonSeller.get_product_status`(httpx 方法内 import, live)。

- [ ] **Step 1: 写失败测试 `tests/test_ozon_seller_status.py`**

```python
import pytest
from app.services.ozon_seller.mock import MockOzonSeller

@pytest.mark.asyncio
async def test_get_product_status_default_approved():
    s = MockOzonSeller()
    st = await s.get_product_status(client_id="C", api_key="K", ozon_product_id="OZ-A1")
    assert st == "approved"

@pytest.mark.asyncio
async def test_get_product_status_pending_injected():
    s = MockOzonSeller(pending_ids={"OZ-A1"})
    assert await s.get_product_status(client_id="C", api_key="K", ozon_product_id="OZ-A1") == "pending"
    assert await s.get_product_status(client_id="C", api_key="K", ozon_product_id="OZ-A2") == "approved"
```

- [ ] **Step 2: 运行确认失败**

Run: `ozon-listing-auto/server/.venv/bin/python -m pytest ozon-listing-auto/server/tests/test_ozon_seller_status.py -v`
Expected: FAIL。

- [ ] **Step 3: 改 `base.py` 加 Protocol 方法**

在 `OzonSellerProvider` Protocol 加：
```python
    async def get_product_status(self, *, client_id: str, api_key: str, ozon_product_id: str) -> str: ...
```

- [ ] **Step 4: 改 `mock.py`**

```python
"""MockOzonSeller：确定性挂靠成功 + 审核状态(默认 approved, 可注入 pending_ids)。"""
from app.services.ozon_seller.base import PublishResult

class MockOzonSeller:
    name = "mock"
    def __init__(self, pending_ids: set | None = None):
        self._pending = pending_ids or set()
    async def create_follow_offer(self, *, client_id, api_key, target_sku, barcode, price, stock, offer_id) -> PublishResult:
        return PublishResult(ok=True, ozon_product_id=f"OZ-{offer_id}", status="published",
                             raw={"target_sku": target_sku, "price": price, "stock": stock})
    async def get_product_status(self, *, client_id, api_key, ozon_product_id) -> str:
        return "pending" if ozon_product_id in self._pending else "approved"
```

- [ ] **Step 5: 改 `real.py` 加 get_product_status(占位真实, live)**

```python
    async def get_product_status(self, *, client_id, api_key, ozon_product_id) -> str:
        import httpx
        headers = {"Client-Id": client_id, "Api-Key": api_key, "Content-Type": "application/json"}
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as c:
                r = await c.post("https://api-seller.ozon.ru/v2/product/info", headers=headers,
                                 json={"product_id": ozon_product_id})   # 占位, 联调校正
                r.raise_for_status()
                data = r.json()
            # 依 Ozon 返回映射 → approved|pending|rejected; 占位默认 pending
            return "pending"
        except Exception:  # noqa: BLE001
            return "pending"
```

- [ ] **Step 6: 运行确认通过**

Run: `ozon-listing-auto/server/.venv/bin/python -m pytest ozon-listing-auto/server/tests/test_ozon_seller_status.py -v`
Expected: PASS。

- [ ] **Step 7: 提交**

```bash
git add ozon-listing-auto/server/app/services/ozon_seller ozon-listing-auto/server/tests/test_ozon_seller_status.py
git commit -m "feat(m5): OzonSeller 加 get_product_status(mock approved/pending 可注入)"
```

---

### Task 4: 调度器（plan_schedule + next_active_window + get_pace）

**Files:**
- Create: `ozon-listing-auto/server/app/services/publish_scheduler.py`
- Create: `ozon-listing-auto/server/tests/test_publish_scheduler.py`

**Interfaces:**
- Produces: `DEFAULT_PACE`(dict); `async get_pace(session, task_id) -> dict`(任务→全局→默认); `next_active_window(dt, active_hours) -> datetime`; `async plan_schedule(session, task_id, pace, *, now, rng) -> dict`(确认草稿排 scheduled_at, 返回 {scheduled})。

- [ ] **Step 1: 写失败测试 `tests/test_publish_scheduler.py`**

```python
import random
import pytest
from datetime import datetime, timezone
from sqlalchemy import select
from app.services.publish_scheduler import plan_schedule, next_active_window, get_pace, DEFAULT_PACE
from app.models import CollectTask, OzonProduct, SupplyCandidate, ListingDraft, PublishPace

def test_next_active_window():
    ah = [9, 23]
    # 时段内不变
    d = datetime(2026, 7, 18, 10, 0, tzinfo=timezone.utc)
    assert next_active_window(d, ah).hour == 10
    # 时段前(6点)→当日 9点
    d2 = datetime(2026, 7, 18, 6, 0, tzinfo=timezone.utc)
    r2 = next_active_window(d2, ah); assert r2.hour == 9 and r2.day == 18
    # 时段后(23点+)→次日 9点
    d3 = datetime(2026, 7, 18, 23, 30, tzinfo=timezone.utc)
    r3 = next_active_window(d3, ah); assert r3.hour == 9 and r3.day == 19

async def _seed(db_session, n=3):
    t = CollectTask(name="t", entry_type="keyword", entry_value="x", provider="mock", source_platforms=["ali1688"])
    db_session.add(t); await db_session.flush()
    p = OzonProduct(task_id=t.id, sku="OZSKU1", title="phone")
    db_session.add(p); await db_session.flush()
    for i in range(n):
        c = SupplyCandidate(task_id=t.id, ozon_product_id=p.id, platform="ali1688", offer_id=f"A{i}", status="adopted")
        db_session.add(c); await db_session.flush()
        db_session.add(ListingDraft(task_id=t.id, ozon_product_id=p.id, candidate_id=c.id, mode="follow",
                                    target_ozon_sku="OZSKU1", price=100, status="confirmed"))
    await db_session.commit()
    return t.id

@pytest.mark.asyncio
async def test_plan_schedule_spaces_and_advances(db_session):
    tid = await _seed(db_session, n=3)
    now = datetime(2026, 7, 18, 10, 0, tzinfo=timezone.utc)
    rng = random.Random(42)
    r = await plan_schedule(db_session, tid, DEFAULT_PACE, now=now, rng=rng)
    await db_session.commit()
    assert r["scheduled"] == 3
    drafts = (await db_session.execute(select(ListingDraft).where(ListingDraft.task_id == tid).order_by(ListingDraft.scheduled_at))).scalars().all()
    assert all(d.status == "scheduled" and d.scheduled_at is not None for d in drafts)
    # 递增且都晚于 now
    times = [d.scheduled_at for d in drafts]
    assert times[0] > now and times == sorted(times)

@pytest.mark.asyncio
async def test_get_pace_fallback(db_session):
    tid = await _seed(db_session, n=1)
    # 无 pace → DEFAULT
    p0 = await get_pace(db_session, tid)
    assert p0["daily_limit"] == 200
    # 全局 pace
    db_session.add(PublishPace(task_id=None, daily_limit=99)); await db_session.commit()
    p1 = await get_pace(db_session, tid)
    assert p1["daily_limit"] == 99
    # 任务 pace 覆盖
    db_session.add(PublishPace(task_id=tid, daily_limit=5)); await db_session.commit()
    p2 = await get_pace(db_session, tid)
    assert p2["daily_limit"] == 5
```

- [ ] **Step 2: 运行确认失败**

Run: `ozon-listing-auto/server/.venv/bin/python -m pytest ozon-listing-auto/server/tests/test_publish_scheduler.py -v`
Expected: FAIL。

- [ ] **Step 3: 写 `publish_scheduler.py`**

```python
"""上架节奏调度：pace 三级回退 + active_hours 窗口 + plan_schedule 排 scheduled_at(§5.9)。"""
from datetime import datetime, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import PublishPace, ListingDraft

DEFAULT_PACE = {"min_interval_sec": 60, "max_interval_sec": 180, "daily_limit": 200,
                "active_hours": [9, 23], "wait_ozon_approval": True}

def _pace_to_dict(p: PublishPace) -> dict:
    return {"min_interval_sec": p.min_interval_sec, "max_interval_sec": p.max_interval_sec,
            "daily_limit": p.daily_limit, "active_hours": list(p.active_hours or [9, 23]),
            "wait_ozon_approval": p.wait_ozon_approval}

async def get_pace(session: AsyncSession, task_id: int) -> dict:
    row = (await session.execute(select(PublishPace).where(PublishPace.task_id == task_id))).scalar_one_or_none()
    if row:
        return _pace_to_dict(row)
    glob = (await session.execute(select(PublishPace).where(PublishPace.task_id.is_(None)))).scalars().first()
    if glob:
        return _pace_to_dict(glob)
    return dict(DEFAULT_PACE)

def next_active_window(dt: datetime, active_hours) -> datetime:
    start, end = active_hours[0], active_hours[1]
    if dt.hour < start:
        return dt.replace(hour=start, minute=0, second=0, microsecond=0)
    if dt.hour >= end:
        nxt = dt + timedelta(days=1)
        return nxt.replace(hour=start, minute=0, second=0, microsecond=0)
    return dt

async def plan_schedule(session: AsyncSession, task_id: int, pace: dict, *, now: datetime, rng) -> dict:
    drafts = (await session.execute(select(ListingDraft).where(
        ListingDraft.task_id == task_id, ListingDraft.status == "confirmed",
        ListingDraft.scheduled_at.is_(None)).order_by(ListingDraft.id))).scalars().all()
    ah = list(pace.get("active_hours", [9, 23]))
    daily_limit = int(pace.get("daily_limit", 200))
    mn, mx = int(pace.get("min_interval_sec", 60)), int(pace.get("max_interval_sec", 180))
    per_day: dict = {}
    cursor = now
    n = 0
    for d in drafts:
        cursor = cursor + timedelta(seconds=rng.randint(mn, mx))
        cursor = next_active_window(cursor, ah)
        while per_day.get(cursor.date(), 0) >= daily_limit:
            nxt = cursor + timedelta(days=1)
            cursor = nxt.replace(hour=ah[0], minute=0, second=0, microsecond=0)
        d.scheduled_at = cursor
        d.status = "scheduled"
        per_day[cursor.date()] = per_day.get(cursor.date(), 0) + 1
        n += 1
    return {"scheduled": n}
```

- [ ] **Step 4: 运行确认通过**

Run: `ozon-listing-auto/server/.venv/bin/python -m pytest ozon-listing-auto/server/tests/test_publish_scheduler.py -v`
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add ozon-listing-auto/server/app/services/publish_scheduler.py ozon-listing-auto/server/tests/test_publish_scheduler.py
git commit -m "feat(m5): 调度器 plan_schedule(排 scheduled_at)+next_active_window+pace 三级回退"
```

---

### Task 5: tick 上架（等审核门 + 逐一挂靠）

**Files:**
- Modify: `ozon-listing-auto/server/app/workers/publisher.py`(加 tick_publish + run_publish_tick)
- Modify: `ozon-listing-auto/server/app/workers/arq_worker.py`(注册 run_publish_tick + cron)
- Create: `ozon-listing-auto/server/tests/test_tick_publish.py`

**Interfaces:**
- Consumes: `get_pace`(Task 4), `OzonSellerProvider`(create_follow_offer + get_product_status), Shop/ListingDraft/SupplyCandidate, crypto.decrypt, broadcaster。
- Produces:
  - `async tick_publish(session_factory, task_id, *, seller, now, max_batch=1) -> dict`（等审核门→取下一条到期 scheduled→挂靠→published/pending_review/failed；返回 {published, pending_review, failed, waiting}）。
  - `async run_publish_tick(ctx)`：ARQ cron 入口(扫有到期草稿的任务逐个 tick, 真实 seller 按配置)。

- [ ] **Step 1: 写失败测试 `tests/test_tick_publish.py`**

```python
import pytest
from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
from app.workers.publisher import tick_publish
from app.services.ozon_seller.mock import MockOzonSeller
from app.core.crypto import encrypt
from app.models import CollectTask, OzonProduct, SupplyCandidate, ListingDraft, Shop, PublishPace

async def _seed(sm, *, wait_approval=True, sched_offset_sec=-10):
    async with sm() as s:
        t = CollectTask(name="t", entry_type="keyword", entry_value="x", provider="mock", source_platforms=["ali1688"])
        s.add(t); await s.flush()
        s.add(PublishPace(task_id=t.id, wait_ozon_approval=wait_approval, min_interval_sec=1, max_interval_sec=1))
        p = OzonProduct(task_id=t.id, sku="OZSKU1", title="phone", barcode="460")
        s.add(p); await s.flush()
        shop = Shop(name="店", client_id="C", api_key_encrypted=encrypt("K"))
        s.add(shop); await s.flush()
        now = datetime(2026, 7, 18, 12, 0, tzinfo=timezone.utc)
        c = SupplyCandidate(task_id=t.id, ozon_product_id=p.id, platform="ali1688", offer_id="A0", status="adopted")
        s.add(c); await s.flush()
        s.add(ListingDraft(task_id=t.id, ozon_product_id=p.id, candidate_id=c.id, shop_id=shop.id, mode="follow",
                           target_ozon_sku="OZSKU1", barcode="460", price=100, stock_qty=5, status="scheduled",
                           scheduled_at=now + timedelta(seconds=sched_offset_sec)))
        await s.commit()
        return t.id, now

@pytest.mark.asyncio
async def test_tick_publishes_due_draft_pending_review_when_wait(engine):
    sm = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    tid, now = await _seed(sm, wait_approval=True)
    r = await tick_publish(sm, tid, seller=MockOzonSeller(), now=now)
    async with sm() as s:
        d = (await s.execute(select(ListingDraft).where(ListingDraft.task_id == tid))).scalar_one()
    assert r["pending_review"] == 1 and r["published"] == 0
    assert d.status == "pending_review" and d.ozon_result["ozon_product_id"] == "OZ-A0"

@pytest.mark.asyncio
async def test_tick_no_wait_publishes_directly(engine):
    sm = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    tid, now = await _seed(sm, wait_approval=False)
    r = await tick_publish(sm, tid, seller=MockOzonSeller(), now=now)
    async with sm() as s:
        d = (await s.execute(select(ListingDraft).where(ListingDraft.task_id == tid))).scalar_one()
    assert r["published"] == 1 and d.status == "published"

@pytest.mark.asyncio
async def test_tick_not_due_skips(engine):
    sm = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    tid, now = await _seed(sm, wait_approval=False, sched_offset_sec=+3600)  # 未来
    r = await tick_publish(sm, tid, seller=MockOzonSeller(), now=now)
    assert r["published"] == 0

@pytest.mark.asyncio
async def test_tick_approval_gate_blocks_next(engine):
    # 已有一条 pending_review(注入 seller pending) → 不推下一条
    sm = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    tid, now = await _seed(sm, wait_approval=True)
    # 先把已有草稿置 pending_review 并给个 ozon id
    async with sm() as s:
        d = (await s.execute(select(ListingDraft).where(ListingDraft.task_id == tid))).scalar_one()
        d.status = "pending_review"; d.ozon_result = {"ozon_product_id": "OZ-A0", "status": "pending_review"}
        await s.commit()
    r = await tick_publish(sm, tid, seller=MockOzonSeller(pending_ids={"OZ-A0"}), now=now)
    assert r["waiting"] is True and r["published"] == 0
    # seller 返回 approved 时, 该条转 published
    r2 = await tick_publish(sm, tid, seller=MockOzonSeller(), now=now)
    async with sm() as s:
        d = (await s.execute(select(ListingDraft).where(ListingDraft.task_id == tid))).scalar_one()
    assert d.status == "published"
```

- [ ] **Step 2: 运行确认失败**

Run: `ozon-listing-auto/server/.venv/bin/python -m pytest ozon-listing-auto/server/tests/test_tick_publish.py -v`
Expected: FAIL。

- [ ] **Step 3: 写 `tick_publish`（加到 publisher.py）**

在 `workers/publisher.py` 追加：
```python
from datetime import datetime, timezone
from app.services.publish_scheduler import get_pace

async def tick_publish(session_factory, task_id: int, *, seller, now, max_batch: int = 1) -> dict:
    log = get_logger(task_id=task_id, phase="publish_tick")
    published = pending_review = failed = 0
    waiting = False
    async with session_factory() as s:
        pace = await get_pace(s, task_id)
    wait_approval = pace.get("wait_ozon_approval", True)
    # 1) 等审核门
    if wait_approval:
        async with session_factory() as s:
            pend = (await s.execute(select(ListingDraft).where(
                ListingDraft.task_id == task_id, ListingDraft.status == "pending_review"))).scalars().all()
            pend_ids = [d.id for d in pend]
        for did in pend_ids:
            async with session_factory() as s:
                d = (await s.execute(select(ListingDraft).where(ListingDraft.id == did))).scalar_one()
                shop = (await s.execute(select(Shop).where(Shop.id == d.shop_id))).scalar_one_or_none() if d.shop_id else None
                ozon_id = (d.ozon_result or {}).get("ozon_product_id", "")
                try:
                    st = await seller.get_product_status(
                        client_id=(shop.client_id if shop else ""),
                        api_key=(decrypt(shop.api_key_encrypted) if shop else ""), ozon_product_id=ozon_id)
                except Exception as exc:  # noqa: BLE001
                    st = "pending"; log.error("status_poll_failed", draft_id=did, error=str(exc))
                if st == "approved":
                    d.status = "published"
                elif st == "rejected":
                    d.status = "failed"; d.error = "ozon rejected"
                else:
                    waiting = True
                await s.commit()
        if waiting:
            return {"published": 0, "pending_review": 0, "failed": 0, "waiting": True}
    # 2) 取下一条到期
    async with session_factory() as s:
        due = (await s.execute(select(ListingDraft).where(
            ListingDraft.task_id == task_id, ListingDraft.status == "scheduled",
            ListingDraft.scheduled_at <= now).order_by(ListingDraft.scheduled_at).limit(max_batch))).scalars().all()
        due_ids = [d.id for d in due]
    for did in due_ids:
        async with session_factory() as s:
            d = (await s.execute(select(ListingDraft).where(ListingDraft.id == did))).scalar_one()
            try:
                shop = (await s.execute(select(Shop).where(Shop.id == d.shop_id))).scalar_one_or_none() if d.shop_id else None
                offer_id = str((await s.execute(select(SupplyCandidate.offer_id).where(SupplyCandidate.id == d.candidate_id))).scalar_one())
                res = await seller.create_follow_offer(
                    client_id=(shop.client_id if shop else ""), api_key=(decrypt(shop.api_key_encrypted) if shop else ""),
                    target_sku=d.target_ozon_sku, barcode=d.barcode,
                    price=float(d.price) if d.price is not None else 0.0, stock=d.stock_qty, offer_id=offer_id)
                if res.ok:
                    d.ozon_result = {"ozon_product_id": res.ozon_product_id, "status": res.status}
                    d.status = "pending_review" if wait_approval else "published"
                    if wait_approval:
                        pending_review += 1
                    else:
                        published += 1
                else:
                    d.status = "failed"; d.error = res.error; failed += 1
            except Exception as exc:  # noqa: BLE001
                err = str(exc) or exc.__class__.__name__
                d.status = "failed"; d.error = err; failed += 1
            await s.commit()
        await broadcaster.publish({"task_id": task_id, "draft_id": did, "phase": "publish",
                                   "published": published, "pending_review": pending_review, "failed": failed})
    return {"published": published, "pending_review": pending_review, "failed": failed, "waiting": False}

async def run_publish_tick(ctx) -> dict:
    """ARQ cron: 扫有到期 scheduled 草稿的任务, 逐个 tick(真实 seller 按配置)。"""
    from app.core.db import async_session
    from app.core.config import settings
    now = datetime.now(timezone.utc)
    async with async_session() as s:
        task_ids = (await s.execute(select(ListingDraft.task_id).where(
            ListingDraft.status.in_(("scheduled", "pending_review"))).distinct())).scalars().all()
    seller = get_ozon_seller(settings.ozon_seller_provider)
    total = {"published": 0, "pending_review": 0, "failed": 0}
    for tid in task_ids:
        r = await tick_publish(async_session, tid, seller=seller, now=now)
        for k in total:
            total[k] += r.get(k, 0)
    return total
```
（确保 `broadcaster`/`get_ozon_seller`/`select`/`decrypt`/`Shop`/`SupplyCandidate`/`ListingDraft`/`get_logger` 已在 publisher.py 导入; 缺则补 import。`from app.core.progress import broadcaster`。）

- [ ] **Step 4: 注册 ARQ cron**

改 `arq_worker.py`：加入 `run_publish_tick` 到 functions, 并加 cron(每分钟)：
```python
from arq import cron
from app.workers.publisher import run_publish, run_publish_tick
class WorkerSettings:
    functions = [run_collect, run_match, run_score, run_publish, run_publish_tick]
    cron_jobs = [cron(run_publish_tick, minute=set(range(0, 60)))]  # 每分钟
    redis_settings = ...
```
（保持既有 functions/redis_settings; 仅追加 run_publish_tick + cron_jobs。若 arq 版本 cron 签名不同, 用其等价写法每分钟触发。）

- [ ] **Step 5: 运行确认通过 + 全套回归**

Run: `ozon-listing-auto/server/.venv/bin/python -m pytest ozon-listing-auto/server/tests -q`
Expected: PASS(0 warnings)。

- [ ] **Step 6: 提交**

```bash
git add ozon-listing-auto/server/app/workers/publisher.py ozon-listing-auto/server/app/workers/arq_worker.py ozon-listing-auto/server/tests/test_tick_publish.py
git commit -m "feat(m5): tick_publish(等审核门+逐一挂靠)+run_publish_tick cron"
```

---

## 阶段 2 · API

### Task 6: 节奏配置 API（/pace）

**Files:**
- Create: `ozon-listing-auto/server/app/schemas/pace.py`
- Create: `ozon-listing-auto/server/app/api/pace.py`
- Modify: `ozon-listing-auto/server/app/main.py`
- Create: `ozon-listing-auto/server/tests/test_pace_api.py`

**Interfaces:**
- Produces: `GET /pace?task_id=`(operator+; get-or-create: 返回任务 pace, 无则返回全局或默认值, 不落库); `PUT /pace?task_id=`(operator+; upsert 该 task_id 的 pace 行)。`PaceOut`/`PaceіIn`(min/max_interval_sec, daily_limit, active_hours, wait_ozon_approval)。

- [ ] **Step 1: 写失败测试 `tests/test_pace_api.py`**

```python
import pytest
from app.core.security import hash_password
from app.models import User

async def _login(client, db_session, role="operator"):
    db_session.add(User(username="u", password_hash=hash_password("p"), role=role))
    await db_session.commit()
    tok = (await client.post("/auth/login", data={"username":"u","password":"p"})).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}

@pytest.mark.asyncio
async def test_pace_get_default_then_put(client, db_session):
    from app.models import CollectTask
    h = await _login(client, db_session)
    db_session.add(CollectTask(id=1, name="t", entry_type="keyword", entry_value="x", provider="mock", source_platforms=[]))
    await db_session.commit()
    g = await client.get("/pace?task_id=1", headers=h)
    assert g.status_code == 200 and g.json()["daily_limit"] == 200   # 默认
    r = await client.put("/pace?task_id=1", json={"min_interval_sec":30,"max_interval_sec":90,"daily_limit":50,"active_hours":[8,22],"wait_ozon_approval":False}, headers=h)
    assert r.status_code == 200
    g2 = await client.get("/pace?task_id=1", headers=h)
    assert g2.json()["daily_limit"] == 50 and g2.json()["active_hours"] == [8,22] and g2.json()["wait_ozon_approval"] is False
```

- [ ] **Step 2: 运行确认失败**

Run: `ozon-listing-auto/server/.venv/bin/python -m pytest ozon-listing-auto/server/tests/test_pace_api.py -v`
Expected: FAIL。

- [ ] **Step 3: 写 `schemas/pace.py`**

```python
"""节奏配置 API schema。"""
from pydantic import BaseModel

class PaceIn(BaseModel):
    min_interval_sec: int = 60
    max_interval_sec: int = 180
    daily_limit: int = 200
    active_hours: list[int] = [9, 23]
    wait_ozon_approval: bool = True

class PaceOut(PaceIn):
    task_id: int | None = None
```

- [ ] **Step 4: 写 `api/pace.py`**

```python
"""节奏配置 API(operator+)：get-or-default / upsert。"""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.db import get_session
from app.api.deps import require_role
from app.models import PublishPace, User
from app.schemas.pace import PaceIn, PaceOut
from app.services.publish_scheduler import get_pace

router = APIRouter(prefix="/pace", tags=["pace"])

@router.get("", response_model=PaceOut)
async def read_pace(task_id: int | None = None, s: AsyncSession = Depends(get_session), _: User = Depends(require_role("operator"))):
    p = await get_pace(s, task_id) if task_id is not None else await get_pace(s, -1)
    return PaceOut(task_id=task_id, **p)

@router.put("", response_model=PaceOut)
async def write_pace(body: PaceIn, task_id: int | None = None, s: AsyncSession = Depends(get_session), _: User = Depends(require_role("operator"))):
    row = (await s.execute(select(PublishPace).where(PublishPace.task_id == task_id))).scalar_one_or_none()
    if not row:
        row = PublishPace(task_id=task_id); s.add(row)
    row.min_interval_sec = body.min_interval_sec; row.max_interval_sec = body.max_interval_sec
    row.daily_limit = body.daily_limit; row.active_hours = body.active_hours; row.wait_ozon_approval = body.wait_ozon_approval
    await s.commit()
    return PaceOut(task_id=task_id, **body.model_dump())
```
（`get_pace(s, -1)` 对不存在的 task_id 走全局/默认回退——即当 task_id 为空时返回全局或默认。）

- [ ] **Step 5: 挂路由 `main.py`**

```python
from app.api.pace import router as pace_router
app.include_router(pace_router)
```

- [ ] **Step 6: 运行确认通过**

Run: `ozon-listing-auto/server/.venv/bin/python -m pytest ozon-listing-auto/server/tests/test_pace_api.py -v`
Expected: PASS。

- [ ] **Step 7: 提交**

```bash
git add ozon-listing-auto/server/app/schemas/pace.py ozon-listing-auto/server/app/api/pace.py ozon-listing-auto/server/app/main.py ozon-listing-auto/server/tests/test_pace_api.py
git commit -m "feat(m5): 节奏配置 API /pace(get-or-default/upsert)"
```

---

### Task 7: 排期/tick/监控 API（/publish/schedule, /publish/tick, /publish/monitor）

**Files:**
- Create: `ozon-listing-auto/server/app/api/publish.py`
- Modify: `ozon-listing-auto/server/app/main.py`
- Create: `ozon-listing-auto/server/tests/test_publish_api.py`

**Interfaces:**
- Produces:
  - `POST /publish/schedule?task_id=`(operator+; get_pace + plan_schedule(now=当前, rng=Random()) → 返回 {scheduled})。
  - `POST /publish/tick?task_id=&sync=`(publisher+; sync=true → tick_publish(dbmod.async_session, seller=mock, now=当前))。
  - `GET /publish/monitor?task_id=`(认证; 各 status 计数 + 下一条 scheduled_at(ETA) + pace 摘要)。

- [ ] **Step 1: 写失败测试 `tests/test_publish_api.py`**

```python
import pytest
from sqlalchemy import select
from app.core.security import hash_password
from app.models import User, CollectTask, OzonProduct, SupplyCandidate, ListingDraft, Shop
from app.core.crypto import encrypt

async def _seed_login(client, db_session):
    db_session.add(User(username="u", password_hash=hash_password("p"), role="admin"))
    t = CollectTask(name="t", entry_type="keyword", entry_value="x", provider="mock", source_platforms=["ali1688"],
                    review_config={"listing_review_required": True})
    db_session.add(t); await db_session.flush()
    p = OzonProduct(task_id=t.id, sku="OZSKU1", title="phone", barcode="460")
    db_session.add(p); await db_session.flush()
    c = SupplyCandidate(task_id=t.id, ozon_product_id=p.id, platform="ali1688", offer_id="A0", status="adopted")
    db_session.add(c); await db_session.flush()
    shop = Shop(name="店", client_id="C", api_key_encrypted=encrypt("K"))
    db_session.add(shop); await db_session.flush()
    db_session.add(ListingDraft(task_id=t.id, ozon_product_id=p.id, candidate_id=c.id, shop_id=shop.id, mode="follow",
                                target_ozon_sku="OZSKU1", barcode="460", price=100, stock_qty=5, status="confirmed"))
    await db_session.commit()
    tok = (await client.post("/auth/login", data={"username":"u","password":"p"})).json()["access_token"]
    return t.id, {"Authorization": f"Bearer {tok}"}

@pytest.mark.asyncio
async def test_schedule_then_tick_then_monitor(client, db_session):
    tid, h = await _seed_login(client, db_session)
    # 排期(pace 默认 wait_approval=True; 用 pace 关掉等审核以便直接 published)
    await client.put(f"/pace?task_id={tid}", json={"min_interval_sec":1,"max_interval_sec":1,"daily_limit":200,"active_hours":[0,24],"wait_ozon_approval":False}, headers=h)
    sch = await client.post(f"/publish/schedule?task_id={tid}", headers=h)
    assert sch.status_code == 200 and sch.json()["scheduled"] == 1
    d = (await db_session.execute(select(ListingDraft).where(ListingDraft.task_id==tid))).scalar_one()
    await db_session.refresh(d)
    assert d.status == "scheduled" and d.scheduled_at is not None
    # tick(scheduled_at 是 now+1s, 但 tick now=当前——排期时 now 已过 → 到期; 用 sync)
    import asyncio; await asyncio.sleep(1.1)
    tick = await client.post(f"/publish/tick?task_id={tid}&sync=true", headers=h)
    assert tick.status_code == 200 and tick.json()["published"] == 1
    mon = await client.get(f"/publish/monitor?task_id={tid}", headers=h)
    assert mon.json()["counts"]["published"] == 1
```
（注：schedule 用当前 now + 1s 间隔, 排出的 scheduled_at ≈ now+1s; tick 前 sleep 1.1s 保证到期。若不想 sleep, 可让 schedule 端点接受 now 或让 min_interval=0——但 rng.randint(0,0)=0, scheduled_at=now→到期; 把 pace min/max 设 0 更稳。改用 min/max=0 免 sleep。）

- [ ] **Step 2: 运行确认失败**

Run: `ozon-listing-auto/server/.venv/bin/python -m pytest ozon-listing-auto/server/tests/test_publish_api.py -v`
Expected: FAIL。

- [ ] **Step 3: 写 `api/publish.py`**

```python
"""上架排期/tick/监控 API。"""
import random
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
import app.core.db as dbmod
from app.core.db import get_session
from app.api.deps import require_role, get_current_user
from app.models import CollectTask, ListingDraft, User
from app.services.publish_scheduler import get_pace, plan_schedule
from app.workers.publisher import tick_publish
from app.services.ozon_seller.factory import get_ozon_seller

router = APIRouter(prefix="/publish", tags=["publish"])

async def _task_or_404(s: AsyncSession, task_id: int) -> CollectTask:
    t = (await s.execute(select(CollectTask).where(CollectTask.id == task_id))).scalar_one_or_none()
    if not t:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "任务不存在")
    return t

@router.post("/schedule")
async def publish_schedule(task_id: int, s: AsyncSession = Depends(get_session), _: User = Depends(require_role("operator"))):
    await _task_or_404(s, task_id)
    pace = await get_pace(s, task_id)
    r = await plan_schedule(s, task_id, pace, now=datetime.now(timezone.utc), rng=random.Random())
    await s.commit()
    return r

@router.post("/tick")
async def publish_tick(task_id: int, sync: bool = False, s: AsyncSession = Depends(get_session), _: User = Depends(require_role("publisher"))):
    await _task_or_404(s, task_id)
    if sync:
        return await tick_publish(dbmod.async_session, task_id, seller=get_ozon_seller("mock"), now=datetime.now(timezone.utc))
    from arq import create_pool
    from arq.connections import RedisSettings
    from app.core.config import settings
    pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    try:
        await pool.enqueue_job("run_publish_tick")
    finally:
        await pool.aclose()
    return {"status": "queued"}

@router.get("/monitor")
async def publish_monitor(task_id: int, s: AsyncSession = Depends(get_session), _: User = Depends(get_current_user)):
    rows = (await s.execute(select(ListingDraft.status, func.count()).where(
        ListingDraft.task_id == task_id).group_by(ListingDraft.status))).all()
    counts = {st: c for st, c in rows}
    nxt = (await s.execute(select(func.min(ListingDraft.scheduled_at)).where(
        ListingDraft.task_id == task_id, ListingDraft.status == "scheduled"))).scalar_one_or_none()
    pace = await get_pace(s, task_id)
    return {"counts": counts, "next_scheduled_at": nxt.isoformat() if nxt else None, "pace": pace}
```

- [ ] **Step 4: 挂路由 `main.py`**

```python
from app.api.publish import router as publish_router
app.include_router(publish_router)
```

- [ ] **Step 5: 修正测试用 min/max=0 免 sleep(与 Step 1 说明一致)**

把 `test_publish_api.py` 的 pace 改为 `min_interval_sec:0, max_interval_sec:0`, 去掉 `asyncio.sleep`——scheduled_at=now(排期时) < now(tick 时)? 排期与 tick 都在同一请求周期内, tick 的 now 略晚于 schedule 的 now → scheduled_at(=schedule now+0) <= tick now。为绝对稳妥, 断言用 `<=` 语义即可(scheduled_at <= tick now 成立)。最终测试:
```python
    await client.put(f"/pace?task_id={tid}", json={"min_interval_sec":0,"max_interval_sec":0,"daily_limit":200,"active_hours":[0,24],"wait_ozon_approval":False}, headers=h)
    sch = await client.post(f"/publish/schedule?task_id={tid}", headers=h); assert sch.json()["scheduled"] == 1
    tick = await client.post(f"/publish/tick?task_id={tid}&sync=true", headers=h); assert tick.json()["published"] == 1
    mon = await client.get(f"/publish/monitor?task_id={tid}", headers=h); assert mon.json()["counts"]["published"] == 1
```
（active_hours=[0,24] 保证任何时刻都在时段内; min/max=0 使 scheduled_at≈schedule-now, tick-now 更晚故到期。）

- [ ] **Step 6: 运行确认通过 + 全套回归**

Run: `ozon-listing-auto/server/.venv/bin/python -m pytest ozon-listing-auto/server/tests -q`
Expected: PASS(0 warnings)。

- [ ] **Step 7: 提交**

```bash
git add ozon-listing-auto/server/app/api/publish.py ozon-listing-auto/server/app/main.py ozon-listing-auto/server/tests/test_publish_api.py
git commit -m "feat(m5): 排期/tick/监控 API(/publish/schedule /tick /monitor)"
```

---

## 阶段 3 · 前端 + 文档

### Task 8: 前端 PublishMonitor（节奏配置 + 监控 + 实时 WS）

**Files:**
- Create: `ozon-listing-auto/web/src/api/pace.ts`
- Create: `ozon-listing-auto/web/src/api/publish.ts`
- Create: `ozon-listing-auto/web/src/pages/PublishMonitor.tsx`
- Modify: `ozon-listing-auto/web/src/App.tsx`(加 /monitor 路由)
- Modify: `ozon-listing-auto/web/src/pages/Layout.tsx`(加菜单)
- Create: `ozon-listing-auto/web/src/pages/PublishMonitor.test.tsx`

**Interfaces:**
- Produces: `api/pace.ts`(getPace/savePace); `api/publish.ts`(schedule/tick/getMonitor); PublishMonitor 页(节奏配置表单 + 状态统计卡 + 下一条ETA + 开始排期/手动tick 按钮 + WS 实时刷新[断开回退轮询])。

- [ ] **Step 1: 写 `api/pace.ts` 与 `api/publish.ts`**

`api/pace.ts`:
```ts
import { api } from "./client";
export interface Pace { min_interval_sec: number; max_interval_sec: number; daily_limit: number; active_hours: number[]; wait_ozon_approval: boolean; }
export const getPace = (taskId: number) => api.get(`/pace?task_id=${taskId}`).then(r => r.data);
export const savePace = (taskId: number, body: Pace) => api.put(`/pace?task_id=${taskId}`, body).then(r => r.data);
```
`api/publish.ts`:
```ts
import { api } from "./client";
export const schedule = (taskId: number) => api.post(`/publish/schedule?task_id=${taskId}`).then(r => r.data);
export const tick = (taskId: number) => api.post(`/publish/tick?task_id=${taskId}&sync=true`).then(r => r.data);
export const getMonitor = (taskId: number) => api.get(`/publish/monitor?task_id=${taskId}`).then(r => r.data);
```

- [ ] **Step 2: 写 `pages/PublishMonitor.tsx`**

```tsx
import { useEffect, useRef, useState } from "react";
import { Card, Form, InputNumber, Switch, Button, Space, Row, Col, Statistic, Tag, message } from "antd";
import { getPace, savePace, Pace } from "../api/pace";
import { schedule, tick, getMonitor } from "../api/publish";

const STATUSES = ["draft", "confirmed", "scheduled", "pending_review", "published", "failed"];
const LABEL: Record<string, string> = { draft: "草稿", confirmed: "已确认", scheduled: "已排期", pending_review: "审核中", published: "已上架", failed: "失败" };

export default function PublishMonitor() {
  const [taskId, setTaskId] = useState<number>();
  const [mon, setMon] = useState<any>({ counts: {}, next_scheduled_at: null });
  const [form] = Form.useForm();
  const wsRef = useRef<WebSocket | null>(null);

  const loadMon = async () => { if (!taskId) return; setMon(await getMonitor(taskId)); };
  const loadPace = async () => { if (!taskId) return; const p = await getPace(taskId);
    form.setFieldsValue({ ...p, ah0: p.active_hours?.[0] ?? 9, ah1: p.active_hours?.[1] ?? 23 }); };

  useEffect(() => { if (!taskId) return; loadPace(); loadMon();
    // 实时 WS(断开回退轮询)
    let poll: any;
    try {
      const proto = location.protocol === "https:" ? "wss" : "ws";
      const ws = new WebSocket(`${proto}://${location.host}/ws/progress`);
      ws.onmessage = () => loadMon();
      ws.onerror = () => { poll = setInterval(loadMon, 5000); };
      wsRef.current = ws;
    } catch { poll = setInterval(loadMon, 5000); }
    return () => { wsRef.current?.close(); if (poll) clearInterval(poll); };
  }, [taskId]);

  const onSavePace = async (v: any) => {
    const body: Pace = { min_interval_sec: v.min_interval_sec, max_interval_sec: v.max_interval_sec,
      daily_limit: v.daily_limit, active_hours: [v.ah0, v.ah1], wait_ozon_approval: v.wait_ozon_approval };
    await savePace(taskId!, body); message.success("节奏已保存"); };
  const onSchedule = async () => { if (!taskId) return; const r = await schedule(taskId); message.success(`排期 ${r.scheduled} 条`); loadMon(); };
  const onTick = async () => { if (!taskId) return; const r = await tick(taskId); message.success(`本次上架 ${r.published}, 审核中 ${r.pending_review}, 失败 ${r.failed}`); loadMon(); };

  return (
    <Space direction="vertical" style={{ width: "100%" }} size="large">
      <Card title="上架监控 PublishMonitor">
        <Space>任务ID <InputNumber onChange={(v) => setTaskId(v as number)} />
          <Button type="primary" onClick={onSchedule}>开始排期</Button>
          <Button onClick={onTick}>手动上架一条</Button>
          <Button onClick={loadMon}>刷新</Button></Space>
      </Card>
      <Card title="节奏配置">
        <Form form={form} layout="inline" onFinish={onSavePace}
          initialValues={{ min_interval_sec: 60, max_interval_sec: 180, daily_limit: 200, ah0: 9, ah1: 23, wait_ozon_approval: true }}>
          <Form.Item name="min_interval_sec" label="最小间隔(秒)"><InputNumber min={0} /></Form.Item>
          <Form.Item name="max_interval_sec" label="最大间隔(秒)"><InputNumber min={0} /></Form.Item>
          <Form.Item name="daily_limit" label="每日上限"><InputNumber min={1} /></Form.Item>
          <Form.Item name="ah0" label="时段起"><InputNumber min={0} max={24} /></Form.Item>
          <Form.Item name="ah1" label="时段止"><InputNumber min={0} max={24} /></Form.Item>
          <Form.Item name="wait_ozon_approval" label="等审核" valuePropName="checked"><Switch /></Form.Item>
          <Button type="primary" htmlType="submit">保存节奏</Button>
        </Form>
      </Card>
      <Card title={`队列监控 · 下一条: ${mon.next_scheduled_at ?? "-"}`}>
        <Row gutter={16}>
          {STATUSES.map((st) => (
            <Col key={st} span={4}><Statistic title={LABEL[st]} value={mon.counts?.[st] ?? 0} /></Col>
          ))}
        </Row>
      </Card>
    </Space>
  );
}
```

- [ ] **Step 3: 加路由与菜单**

`App.tsx` 受保护路由内加 `import PublishMonitor` + `<Route path="/monitor" element={<PublishMonitor />} />`。
`Layout.tsx` 菜单加 `{ key: "monitor", label: "上架监控" }`。

- [ ] **Step 4: 写测试 `pages/PublishMonitor.test.tsx`**

```tsx
import { render, screen } from "@testing-library/react";
import { vi } from "vitest";
vi.mock("../api/pace", () => ({ getPace: vi.fn(() => Promise.resolve({})), savePace: vi.fn() }));
vi.mock("../api/publish", () => ({ schedule: vi.fn(), tick: vi.fn(), getMonitor: vi.fn(() => Promise.resolve({ counts: {}, next_scheduled_at: null })) }));
// jsdom 无 WebSocket → 提供最小桩
(globalThis as any).WebSocket = class { close() {} set onmessage(_f: any) {} set onerror(_f: any) {} };
import PublishMonitor from "./PublishMonitor";

test("渲染上架监控页", () => {
  render(<PublishMonitor />);
  expect(screen.getByText("上架监控 PublishMonitor")).toBeInTheDocument();
  expect(screen.getByText("开始排期")).toBeInTheDocument();
});
```

- [ ] **Step 5: 运行前端测试 + build**

Run: `cd ozon-listing-auto/web && npx vitest run && npm run build`
Expected: 所有前端测试通过(Login/Tasks/Products/ReviewBoard/ListingReview/PricingSettings/PublishMonitor)；`npm run build` 成功。

- [ ] **Step 6: 提交**

```bash
git add ozon-listing-auto/web/src/api/pace.ts ozon-listing-auto/web/src/api/publish.ts ozon-listing-auto/web/src/pages/PublishMonitor.tsx ozon-listing-auto/web/src/pages/PublishMonitor.test.tsx ozon-listing-auto/web/src/App.tsx ozon-listing-auto/web/src/pages/Layout.tsx
git commit -m "feat(m5): 前端 PublishMonitor(节奏配置+队列监控+实时WS)"
```

---

### Task 9: README/docs M5 + 全量回归

**Files:**
- Modify: `ozon-listing-auto/README.md`
- Create: `ozon-listing-auto/docs/M5-节奏调度说明.md`

**Interfaces:**
- Produces: README M5 段 + M5 使用说明。

- [ ] **Step 1: 更新 `README.md` M5 段**

加 M5 功能：上架节奏调度(plan_schedule 排 scheduled_at + tick 逐一上架 + 随机间隔/active_hours/daily_limit/等审核)、跨进程实时进度(Broadcaster memory/redis 后端, `PROGRESS_BACKEND=redis`)、节奏配置 /pace、排期/tick/监控 API、PublishMonitor 前端(实时WS)。更新里程碑状态(M1-M5 done)。注明真实 Ozon 审核状态端点 live 校正。

- [ ] **Step 2: 写 `docs/M5-节奏调度说明.md`**

流程：配节奏(/pace 或 PublishMonitor)→采集→…→采用→定价→确认→/publish/schedule(排期, 得 scheduled_at)→周期 tick 或手动 /publish/tick 逐一上架(等审核门)→PublishMonitor 看队列/已上架/审核中/失败+下一条ETA+实时。生产开 `PROGRESS_BACKEND=redis` 让 worker 进度跨进程推 WS; `OZON_SELLER_PROVIDER=real` + 真实店铺凭据走真实挂靠(审核状态端点 live 校正)。

- [ ] **Step 3: 全量回归**

Run: `cd ozon-listing-auto/server && .venv/bin/python -m pytest -q && cd ../web && npx vitest run && npm run build`
Expected: 后端全绿(非 live, 0 warnings)；前端全绿 + build 成功。

- [ ] **Step 4: 提交**

```bash
git add ozon-listing-auto/README.md ozon-listing-auto/docs/M5-节奏调度说明.md
git commit -m "docs: README + M5 节奏调度说明"
```

---

## 验收对照（spec §8）

| 验收项 | 覆盖任务 |
|---|---|
| 迁移 0005 publish_pace | Task 1 |
| 配节奏→…→确认→schedule(排 scheduled_at) | Task 4,6,7 |
| tick 逐一上架(随机间隔/active_hours/daily_limit/等审核) | Task 3,4,5 |
| Redis pub/sub 后端可切(memory 测试/redis 生产跨进程) | Task 2 |
| PublishMonitor 前端(队列/已上架/审核中/失败+ETA+实时WS+节奏配置) | Task 8 |
| MockOzonSeller.get_product_status 全链路 + 真实 live 跳过 | Task 3,5 |
| 非 live 0 warnings + README/docs + 前端 build | Task 9 |

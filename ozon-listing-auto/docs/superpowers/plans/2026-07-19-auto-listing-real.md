# 自动上品（真实 Ozon Seller）实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让真实自动上品端到端可用——跟卖（A 阶段）先真发，自建（B 阶段）补齐 Ozon v3 必填字段后真发；默认安全（默认 mock + 默认 dry-run）。

**Architecture:** 异步发布链路（`workers/publisher.py`）已配置驱动；本计划 A 阶段把两个同步接口也接线为配置驱动，并给 `RealOzonSeller` 加 dry-run（构造真实请求但不 POST）；B 阶段新增 Ozon 卖家端类目/类型/属性 provider、扩 `listing_drafts` 字段、上架审核补充表单、`create_product` 带全字段。

**Tech Stack:** Python 3.11 / FastAPI / SQLAlchemy 2.0 async / Alembic / httpx；React 18 + TS + Ant Design 5 + Vitest。

## Global Constraints

- 后端测试 **0 warnings**；真实网络用 `@pytest.mark.live`（默认 `-m 'not live'` 跳过）；请求结构测试用 `httpx.MockTransport`。
- 密文（api_key）Fernet 加密；配置读取沿用 `settings_store.get_category(s, "system")`。
- **默认安全**：`ozon_seller_provider` 默认 `mock`；`ozon_publish_dry_run` 默认 `"true"`。
- Ozon 端点固定：跟卖 `POST /v1/product/import-by-sku`；自建 `POST /v3/product/import`；状态 `POST /v1/product/import/info`；类目树 `POST /v1/description-category/tree`；属性 `POST /v1/description-category/attribute`；属性值 `POST /v1/description-category/attribute/values`。Base `https://api-seller.ozon.ru`，头 `Client-Id` + `Api-Key`。
- 前端沿用 `import { api } from "../api/client"`；配置页仅 admin；每步改完保证 `npm run build` + 相关 Vitest 通过。
- `PublishResult(ok, ozon_product_id, status, raw={}, error=None)`，status ∈ `published|pending_review|failed`。

---

# A 阶段：接线 + 开关 + dry-run（跟卖真发）

### Task 1: RealOzonSeller 支持 dry-run

**Files:**
- Modify: `server/app/services/ozon_seller/real.py`
- Test: `server/tests/test_ozon_seller_real.py`（已存在则追加）

**Interfaces:**
- Produces: `RealOzonSeller(timeout=30.0, transport=None, dry_run=False)`；dry_run=True 时 `create_follow_offer`/`create_product` 返回 `PublishResult(ok=True, ozon_product_id="DRYRUN", status="pending_review", raw={"dry_run": <请求体>})` 且不发起网络；`get_product_status` 返回 `"approved"`。

- [ ] **Step 1: 写失败测试**

```python
# server/tests/test_ozon_seller_real.py
import httpx, pytest
from app.services.ozon_seller.real import RealOzonSeller

def _boom_transport():
    def handler(request):  # 任何真实请求都视为错误
        raise AssertionError(f"dry-run 不应发起网络: {request.url}")
    return httpx.MockTransport(handler)

@pytest.mark.asyncio
async def test_follow_dry_run_builds_body_without_post():
    s = RealOzonSeller(transport=_boom_transport(), dry_run=True)
    r = await s.create_follow_offer(client_id="c", api_key="k", target_sku="123",
                                    barcode="b", price=2300.0, stock=5, offer_id="OF1")
    assert r.ok and r.status == "pending_review" and r.ozon_product_id == "DRYRUN"
    body = r.raw["dry_run"]
    assert body["items"][0]["sku"] == 123
    assert body["items"][0]["price"] == "2300"
    assert body["items"][0]["offer_id"] == "OF1"

@pytest.mark.asyncio
async def test_status_dry_run_is_approved():
    s = RealOzonSeller(transport=_boom_transport(), dry_run=True)
    assert await s.get_product_status(client_id="c", api_key="k", ozon_product_id="DRYRUN") == "approved"
```

- [ ] **Step 2: 运行确认失败**

Run: `cd server && python -m pytest tests/test_ozon_seller_real.py -k dry_run -q`
Expected: FAIL（`RealOzonSeller` 无 `dry_run` 参数 / 未短路）

- [ ] **Step 3: 实现**

在 `RealOzonSeller.__init__` 增 `dry_run` 字段；两个写方法在构造 `body`/`item` 后、`try` 网络前插入 dry-run 短路；`get_product_status` 顶部短路。

```python
# __init__（在现有基础上增参）
def __init__(self, timeout: float = 30.0, transport=None, dry_run: bool = False):
    self._timeout = timeout
    self._transport = transport
    self._dry_run = dry_run

# create_follow_offer：构造 body 后、async with 前
if self._dry_run:
    return PublishResult(ok=True, ozon_product_id="DRYRUN", status="pending_review", raw={"dry_run": body})

# create_product：构造 item/请求体后、async with 前
if self._dry_run:
    return PublishResult(ok=True, ozon_product_id="DRYRUN", status="pending_review",
                         raw={"dry_run": {"items": [item]}})

# get_product_status：方法第一行
if self._dry_run:
    return "approved"
```

- [ ] **Step 4: 运行确认通过**

Run: `cd server && python -m pytest tests/test_ozon_seller_real.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add server/app/services/ozon_seller/real.py server/tests/test_ozon_seller_real.py
git commit -m "feat(seller): RealOzonSeller 支持 dry-run(构造真实请求不提交)"
```

---

### Task 2: resolve_seller 配置解析 helper

**Files:**
- Create: `server/app/services/ozon_seller/resolve.py`
- Test: `server/tests/test_resolve_seller.py`

**Interfaces:**
- Consumes: `get_ozon_seller(name)`（factory）、`RealOzonSeller(dry_run=...)`、`get_category(session,"system")`、`settings.ozon_seller_provider`。
- Produces: `async def resolve_seller(session) -> OzonSellerProvider` —— provider=mock→MockOzonSeller；provider=real→RealOzonSeller(dry_run=<system.ozon_publish_dry_run != "false">)。dry_run 默认 True。

- [ ] **Step 1: 写失败测试**

```python
# server/tests/test_resolve_seller.py
import pytest
from app.services.ozon_seller.resolve import resolve_seller
from app.services.ozon_seller.mock import MockOzonSeller
from app.services.ozon_seller.real import RealOzonSeller
from app.services import settings_store

@pytest.mark.asyncio
async def test_resolve_mock_default(db_session):
    assert isinstance(await resolve_seller(db_session), MockOzonSeller)

@pytest.mark.asyncio
async def test_resolve_real_dry_run_default_true(db_session):
    await settings_store.set_value(db_session, "system", "ozon_seller_provider", "real", is_secret=False)
    seller = await resolve_seller(db_session)
    assert isinstance(seller, RealOzonSeller) and seller._dry_run is True

@pytest.mark.asyncio
async def test_resolve_real_dry_run_off(db_session):
    await settings_store.set_value(db_session, "system", "ozon_seller_provider", "real", is_secret=False)
    await settings_store.set_value(db_session, "system", "ozon_publish_dry_run", "false", is_secret=False)
    seller = await resolve_seller(db_session)
    assert isinstance(seller, RealOzonSeller) and seller._dry_run is False
```

> 若无 `db_session` fixture，用现有测试的 session fixture 名（见 `tests/conftest.py`）。

- [ ] **Step 2: 运行确认失败**

Run: `cd server && python -m pytest tests/test_resolve_seller.py -q`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现**

```python
# server/app/services/ozon_seller/resolve.py
"""按 system 配置解析 OzonSellerProvider：provider(mock|real) + real 时 dry-run 开关。"""
from app.core.config import settings
from app.services.settings_store import get_category
from app.services.ozon_seller.factory import get_ozon_seller
from app.services.ozon_seller.base import OzonSellerProvider


async def resolve_seller(session) -> OzonSellerProvider:
    conf = await get_category(session, "system")
    name = conf.get("ozon_seller_provider") or settings.ozon_seller_provider
    if name == "real":
        from app.services.ozon_seller.real import RealOzonSeller
        dry_run = conf.get("ozon_publish_dry_run", "true") != "false"
        return RealOzonSeller(dry_run=dry_run)
    return get_ozon_seller(name)
```

- [ ] **Step 4: 运行确认通过**

Run: `cd server && python -m pytest tests/test_resolve_seller.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add server/app/services/ozon_seller/resolve.py server/tests/test_resolve_seller.py
git commit -m "feat(seller): resolve_seller 按 system 配置解析 provider+dry-run"
```

---

### Task 3: 同步接口与 arq 统一用 resolve_seller

**Files:**
- Modify: `server/app/api/listing.py`（第 77 行附近）
- Modify: `server/app/api/publish.py`（第 35 行附近）
- Modify: `server/app/workers/publisher.py`（`run_publish`、`run_publish_tick` 内联读取改调 resolve_seller，DRY）
- Test: `server/tests/test_publish_wiring.py`

**Interfaces:**
- Consumes: `resolve_seller(session)`（Task 2）。
- 行为：`ozon_seller_provider=mock` 时两个同步接口行为不变；`=real`+dry-run 时同步 `/listing/publish?sync=true` 对 follow 草稿返回的 `ozon_result.raw.dry_run` 含真实请求体。

- [ ] **Step 1: 写失败测试**

```python
# server/tests/test_publish_wiring.py —— provider=real+dry-run 时同步 publish 不真发且构造真实请求体
import pytest
from httpx import AsyncClient
from app.services import settings_store

@pytest.mark.asyncio
async def test_sync_publish_real_dry_run(client: AsyncClient, admin_headers, seeded_follow_draft):
    # seeded_follow_draft: 建一个 mode=follow、含 shop_id/target_ozon_sku/price 的到期草稿, 返回 task_id
    await settings_store_set(("ozon_seller_provider", "real"), ("ozon_publish_dry_run", "true"))
    r = await client.post(f"/api/listing/publish?task_id={seeded_follow_draft}&sync=true", headers=admin_headers)
    assert r.status_code == 200
    # 拉草稿看结果
    drafts = (await client.get(f"/api/listing/drafts?task_id={seeded_follow_draft}", headers=admin_headers)).json()
    assert any((d.get("ozon_result") or {}).get("dry_run") for d in drafts)
```

> 实现者：按 `tests/conftest.py` 现有 fixture 命名调整（client/admin_headers/建草稿的方式）；若已有建草稿的 helper 复用之。核心断言=real+dry-run 下有 `dry_run` 请求体、无真实网络。

- [ ] **Step 2: 运行确认失败**

Run: `cd server && python -m pytest tests/test_publish_wiring.py -q`
Expected: FAIL（当前写死 mock，无 dry_run 结果）

- [ ] **Step 3: 实现**

`api/listing.py`：
```python
from app.services.ozon_seller.resolve import resolve_seller
# 删除 from app.services.ozon_seller.factory import get_ozon_seller（若仅此处用）
# 第 77 行：
        r = await run_publish_core(dbmod.async_session, task_id, seller=await resolve_seller(s))
```
`api/publish.py`：
```python
from app.services.ozon_seller.resolve import resolve_seller
# 第 35 行：
        return await tick_publish(dbmod.async_session, task_id, seller=await resolve_seller(s), now=datetime.now(timezone.utc))
```
`workers/publisher.py` `run_publish`（去掉内联三行读取，改用 resolve_seller）：
```python
async def run_publish(ctx, task_id: int) -> dict:
    from app.core.db import async_session
    from app.services.ozon_seller.resolve import resolve_seller
    async with async_session() as s:
        seller = await resolve_seller(s)
    return await run_publish_core(async_session, task_id, seller=seller)
```
`run_publish_tick` 同理：把内联的 `get_category(...).get("ozon_seller_provider")...get_ozon_seller(name)` 替换为 `await resolve_seller(s)`（在已有 `async with async_session() as s:` 内取一次 seller，传给 tick 循环）。

- [ ] **Step 4: 运行确认通过 + 回归**

Run: `cd server && python -m pytest tests/test_publish_wiring.py tests/test_ozon_seller_real.py tests/test_resolve_seller.py -q && python -m pytest -q`
Expected: PASS，全套 0 warnings

- [ ] **Step 5: 提交**

```bash
git add server/app/api/listing.py server/app/api/publish.py server/app/workers/publisher.py server/tests/test_publish_wiring.py
git commit -m "feat(publish): 同步接口与 arq 统一经 resolve_seller 配置驱动上品"
```

---

### Task 4: 系统设置页——上品模式 + dry-run 开关

**Files:**
- Modify: `web/src/pages/settings/SystemSettings.tsx`
- Test: `web/src/pages/settings/SystemSettings.test.tsx`（无则新建）

**Interfaces:**
- 读写 `system` 配置：`ozon_seller_provider`（Select：模拟 mock / 真实 real）、`ozon_publish_dry_run`（Switch，存 `"true"`/`"false"`）、保留 `category_tree_provider`。

- [ ] **Step 1: 写失败测试**

```tsx
// SystemSettings.test.tsx —— 渲染出"上品模式"选择与"试运行"开关
import { render, screen } from "@testing-library/react";
import { vi } from "vitest";
vi.mock("../../api/client", () => ({ api: { get: vi.fn().mockResolvedValue({ data: {
  ozon_seller_provider: "mock", ozon_publish_dry_run: "true", category_tree_provider: "mock" } }), put: vi.fn() } }));
import SystemSettings from "./SystemSettings";
test("显示上品模式与试运行开关", async () => {
  render(<SystemSettings />);
  expect(await screen.findByText("上品模式")).toBeInTheDocument();
  expect(await screen.findByText(/试运行/)).toBeInTheDocument();
});
```

- [ ] **Step 2: 运行确认失败**

Run: `cd web && npx vitest run src/pages/settings/SystemSettings -q`
Expected: FAIL

- [ ] **Step 3: 实现**

SystemSettings 表单加：
```tsx
<Form.Item name="ozon_seller_provider" label="上品模式" tooltip="真实模式会调用 Ozon Seller API 真正上品">
  <Select options={[{ value: "mock", label: "模拟（不真发）" }, { value: "real", label: "真实（调用 Ozon）" }]} />
</Form.Item>
<Form.Item name="ozon_publish_dry_run" label="试运行(dry-run)" valuePropName="checked"
  tooltip="真实模式下先只构造请求、不真正提交；确认无误后再关闭真发">
  <Switch />
</Form.Item>
```
读取时把 `"true"/"false"` 转成布尔喂给 Switch，保存时转回字符串：
```tsx
// load: form.setFieldsValue({ ...data, ozon_publish_dry_run: data.ozon_publish_dry_run !== "false" })
// submit: api.put("/settings/system", { ...v, ozon_publish_dry_run: v.ozon_publish_dry_run ? "true" : "false" })
```

- [ ] **Step 4: 运行确认通过 + build**

Run: `cd web && npx vitest run src/pages/settings/SystemSettings -q && npm run build`
Expected: PASS + build 成功

- [ ] **Step 5: 提交**

```bash
git add web/src/pages/settings/SystemSettings.tsx web/src/pages/settings/SystemSettings.test.tsx
git commit -m "feat(web): 系统设置加上品模式(模拟/真实)+试运行开关"
```

---

# B 阶段：自建补齐（自建真发）

### Task 5: listing_drafts 扩字段 + 迁移

**Files:**
- Modify: `server/app/models/listing_draft.py`
- Create: `server/alembic/versions/<rev>_draft_create_fields.py`
- Test: `server/tests/test_draft_create_fields.py`

**Interfaces:**
- Produces: `ListingDraft` 新增可空列 `type_id:int|None`、`depth/width/height/weight:int|None`、`dimension_unit:str("mm")`、`weight_unit:str("g")`。

- [ ] **Step 1: 写失败测试**

```python
# server/tests/test_draft_create_fields.py
import pytest
from app.models import ListingDraft

@pytest.mark.asyncio
async def test_draft_has_create_fields(db_session):
    d = ListingDraft(task_id=1, candidate_id=1, mode="create", type_id=971,
                     depth=100, width=80, height=50, weight=250)
    db_session.add(d); await db_session.flush()
    got = await db_session.get(ListingDraft, d.id)
    assert got.type_id == 971 and got.depth == 100 and got.dimension_unit == "mm" and got.weight_unit == "g"
```

- [ ] **Step 2: 运行确认失败**

Run: `cd server && python -m pytest tests/test_draft_create_fields.py -q`
Expected: FAIL（无 type_id 列）

- [ ] **Step 3: 实现**

`listing_draft.py` 在 `attributes` 后加列：
```python
    type_id: Mapped[int | None] = mapped_column(Integer, nullable=True)          # 自建：Ozon 类型 id
    depth: Mapped[int | None] = mapped_column(Integer, nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    weight: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dimension_unit: Mapped[str] = mapped_column(String(8), default="mm")
    weight_unit: Mapped[str] = mapped_column(String(8), default="g")
```
Alembic 迁移（`cd server && alembic revision -m "draft create fields"` 后填 upgrade/downgrade）：
```python
def upgrade():
    op.add_column("listing_drafts", sa.Column("type_id", sa.Integer(), nullable=True))
    op.add_column("listing_drafts", sa.Column("depth", sa.Integer(), nullable=True))
    op.add_column("listing_drafts", sa.Column("width", sa.Integer(), nullable=True))
    op.add_column("listing_drafts", sa.Column("height", sa.Integer(), nullable=True))
    op.add_column("listing_drafts", sa.Column("weight", sa.Integer(), nullable=True))
    op.add_column("listing_drafts", sa.Column("dimension_unit", sa.String(length=8), server_default="mm", nullable=False))
    op.add_column("listing_drafts", sa.Column("weight_unit", sa.String(length=8), server_default="g", nullable=False))

def downgrade():
    for c in ("type_id","depth","width","height","weight","dimension_unit","weight_unit"):
        op.drop_column("listing_drafts", c)
```

- [ ] **Step 4: 运行确认通过**

Run: `cd server && alembic upgrade head && python -m pytest tests/test_draft_create_fields.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add server/app/models/listing_draft.py server/alembic/versions/
git commit -m "feat(draft): 扩自建字段 type_id/尺寸/重量/单位 + 迁移"
```

---

### Task 6: Ozon 卖家端类目/类型/属性 provider

**Files:**
- Create: `server/app/services/ozon_seller/catalog.py`
- Test: `server/tests/test_ozon_catalog.py`

**Interfaces:**
- Produces: `class OzonCatalog:` `__init__(timeout=30.0, transport=None, sample=False)`；方法
  - `async get_types(client_id, api_key) -> list[dict]`（`POST /v1/description-category/tree`）
  - `async get_attributes(client_id, api_key, *, category_id, type_id) -> list[dict]`（`POST /v1/description-category/attribute`）
  - `async get_attribute_values(client_id, api_key, *, category_id, type_id, attribute_id) -> list[dict]`（`POST /v1/description-category/attribute/values`）
  - `sample=True`（或无凭证）返回内置样例，供前端开发/mock。

- [ ] **Step 1: 写失败测试**（MockTransport 断言 URL/body 结构）

```python
# server/tests/test_ozon_catalog.py
import json, httpx, pytest
from app.services.ozon_seller.catalog import OzonCatalog

def _transport(expect_path, reply):
    def handler(req):
        assert req.url.path == expect_path
        assert req.headers["Client-Id"] == "c" and req.headers["Api-Key"] == "k"
        return httpx.Response(200, json=reply)
    return httpx.MockTransport(handler)

@pytest.mark.asyncio
async def test_get_attributes_calls_correct_endpoint():
    reply = {"result": [{"id": 85, "name": "Бренд", "is_required": True, "dictionary_id": 28}]}
    cat = OzonCatalog(transport=_transport("/v1/description-category/attribute", reply))
    attrs = await cat.get_attributes("c", "k", category_id=17028922, type_id=93080)
    assert attrs[0]["id"] == 85 and attrs[0]["is_required"] is True

@pytest.mark.asyncio
async def test_sample_mode_no_network():
    cat = OzonCatalog(sample=True)
    assert isinstance(await cat.get_types("", ""), list)
    assert isinstance(await cat.get_attributes("", "", category_id=1, type_id=1), list)
```

- [ ] **Step 2: 运行确认失败**

Run: `cd server && python -m pytest tests/test_ozon_catalog.py -q`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现**

```python
# server/app/services/ozon_seller/catalog.py
"""Ozon 卖家端类目/类型/属性(description-category 系列)，供自建上品取 type_id/必填属性/字典值。
注意：这与买家端 composer 类目树是两套。sample=True 或无凭证时返回内置样例。"""
import httpx

_BASE = "https://api-seller.ozon.ru"
_TREE = "/v1/description-category/tree"
_ATTR = "/v1/description-category/attribute"
_ATTR_VALUES = "/v1/description-category/attribute/values"

_SAMPLE_TYPES = [{"category_id": 17028922, "category_name": "示例类目",
                  "types": [{"type_id": 93080, "type_name": "示例类型"}]}]
_SAMPLE_ATTRS = [{"id": 85, "name": "品牌", "is_required": True, "dictionary_id": 28},
                 {"id": 9048, "name": "商品名称", "is_required": True, "dictionary_id": 0}]
_SAMPLE_VALUES = [{"id": 1000, "value": "示例值A"}, {"id": 1001, "value": "示例值B"}]


class OzonCatalog:
    def __init__(self, timeout: float = 30.0, transport=None, sample: bool = False):
        self._timeout = timeout
        self._transport = transport
        self._sample = sample

    def _client(self):
        return httpx.AsyncClient(base_url=_BASE, timeout=self._timeout, transport=self._transport)

    @staticmethod
    def _headers(client_id, api_key):
        return {"Client-Id": str(client_id), "Api-Key": str(api_key), "Content-Type": "application/json"}

    async def _post(self, path, client_id, api_key, body):
        async with self._client() as c:
            r = await c.post(path, headers=self._headers(client_id, api_key), json=body)
            r.raise_for_status()
            return r.json()

    async def get_types(self, client_id, api_key):
        if self._sample or not client_id:
            return _SAMPLE_TYPES
        return (await self._post(_TREE, client_id, api_key, {})).get("result", [])

    async def get_attributes(self, client_id, api_key, *, category_id, type_id):
        if self._sample or not client_id:
            return _SAMPLE_ATTRS
        body = {"description_category_id": category_id, "type_id": type_id}
        return (await self._post(_ATTR, client_id, api_key, body)).get("result", [])

    async def get_attribute_values(self, client_id, api_key, *, category_id, type_id, attribute_id):
        if self._sample or not client_id:
            return _SAMPLE_VALUES
        body = {"description_category_id": category_id, "type_id": type_id,
                "attribute_id": attribute_id, "limit": 100}
        return (await self._post(_ATTR_VALUES, client_id, api_key, body)).get("result", [])
```

- [ ] **Step 4: 运行确认通过**

Run: `cd server && python -m pytest tests/test_ozon_catalog.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add server/app/services/ozon_seller/catalog.py server/tests/test_ozon_catalog.py
git commit -m "feat(seller): Ozon 卖家端类目/类型/属性 provider(含样例模式)"
```

---

### Task 7: 类目/属性 API 端点

**Files:**
- Create: `server/app/api/ozon_catalog.py`
- Modify: `server/app/api/__init__.py`（注册 router）
- Test: `server/tests/test_ozon_catalog_api.py`

**Interfaces:**
- Consumes: `OzonCatalog`（Task 6）、店铺凭证（取第一个 active ozon shop 或按 `shop_id` 参数）。provider=mock 或无店铺时用 `sample=True`。
- Produces（admin/operator）：`GET /ozon-catalog/types`、`GET /ozon-catalog/attributes?category_id=&type_id=`、`GET /ozon-catalog/attribute-values?category_id=&type_id=&attribute_id=`。

- [ ] **Step 1: 写失败测试**

```python
# server/tests/test_ozon_catalog_api.py —— 无真实店铺时走样例, 返回非空 list
import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_types_sample_without_shop(client: AsyncClient, admin_headers):
    r = await client.get("/api/ozon-catalog/types", headers=admin_headers)
    assert r.status_code == 200 and isinstance(r.json(), list) and r.json()
```

- [ ] **Step 2: 运行确认失败**

Run: `cd server && python -m pytest tests/test_ozon_catalog_api.py -q`
Expected: FAIL（404）

- [ ] **Step 3: 实现**

```python
# server/app/api/ozon_catalog.py
"""Ozon 卖家端类目/类型/属性查询(admin/operator)：供上架审核自建补充表单用。
有真实 ozon 店铺+provider=real 时走真实 API, 否则样例模式。"""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.db import get_session
from app.core.crypto import decrypt
from app.api.deps import require_role
from app.models import Shop, User
from app.services.settings_store import get_category
from app.services.ozon_seller.catalog import OzonCatalog

router = APIRouter(prefix="/ozon-catalog", tags=["ozon-catalog"])

async def _catalog_and_creds(s: AsyncSession):
    conf = await get_category(s, "system")
    real = (conf.get("ozon_seller_provider") or "mock") == "real"
    shop = (await s.execute(select(Shop).where(Shop.platform == "ozon", Shop.is_active == True))).scalars().first()
    if real and shop:
        return OzonCatalog(), shop.client_id, decrypt(shop.api_key_encrypted)
    return OzonCatalog(sample=True), "", ""

@router.get("/types")
async def types(s: AsyncSession = Depends(get_session), _: User = Depends(require_role("operator"))):
    cat, cid, key = await _catalog_and_creds(s)
    return await cat.get_types(cid, key)

@router.get("/attributes")
async def attributes(category_id: int, type_id: int, s: AsyncSession = Depends(get_session), _: User = Depends(require_role("operator"))):
    cat, cid, key = await _catalog_and_creds(s)
    return await cat.get_attributes(cid, key, category_id=category_id, type_id=type_id)

@router.get("/attribute-values")
async def attribute_values(category_id: int, type_id: int, attribute_id: int, s: AsyncSession = Depends(get_session), _: User = Depends(require_role("operator"))):
    cat, cid, key = await _catalog_and_creds(s)
    return await cat.get_attribute_values(cid, key, category_id=category_id, type_id=type_id, attribute_id=attribute_id)
```
在 `app/api/__init__.py` 注册：`from app.api import ozon_catalog` + `api.include_router(ozon_catalog.router)`（沿用现有注册风格）。

- [ ] **Step 4: 运行确认通过**

Run: `cd server && python -m pytest tests/test_ozon_catalog_api.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add server/app/api/ozon_catalog.py server/app/api/__init__.py server/tests/test_ozon_catalog_api.py
git commit -m "feat(api): Ozon 类目/类型/属性查询端点(样例兜底)"
```

---

### Task 8: create_product 带全字段 + 属性字典值

**Files:**
- Modify: `server/app/services/ozon_seller/base.py`（Protocol 签名）
- Modify: `server/app/services/ozon_seller/real.py`（`create_product` + `_to_ozon_attributes`）
- Modify: `server/app/services/ozon_seller/mock.py`（`create_product` 增参，保持可调用）
- Modify: `server/app/workers/publisher.py`（`_call_seller` 透传新字段）
- Test: `server/tests/test_ozon_seller_real.py`（追加）

**Interfaces:**
- Produces: `create_product(..., type_id, depth, width, height, weight, dimension_unit, weight_unit)` 新增关键字参数；`_to_ozon_attributes` 支持值为 `{"dictionary_value_id": int}` 或纯标量。

- [ ] **Step 1: 写失败测试**

```python
# 追加到 test_ozon_seller_real.py
@pytest.mark.asyncio
async def test_create_product_dry_run_includes_full_fields():
    s = RealOzonSeller(transport=_boom_transport(), dry_run=True)
    r = await s.create_product(client_id="c", api_key="k", offer_id="OF9", title="T", description="D",
        category_id=17028922, type_id=93080, attributes={85: {"dictionary_value_id": 1000}, 9048: "手动名称"},
        images=["u1"], price=1999.0, stock=3, barcode="B", depth=100, width=80, height=50,
        weight=250, dimension_unit="mm", weight_unit="g")
    item = r.raw["dry_run"]["items"][0]
    assert item["description_category_id"] == 17028922 and item["type_id"] == 93080
    assert item["depth"] == 100 and item["weight"] == 250 and item["dimension_unit"] == "mm"
    ids = {a["id"]: a for a in item["attributes"]}
    assert ids[85]["values"][0]["dictionary_value_id"] == 1000
    assert ids[9048]["values"][0]["value"] == "手动名称"
```

- [ ] **Step 2: 运行确认失败**

Run: `cd server && python -m pytest tests/test_ozon_seller_real.py -k full_fields -q`
Expected: FAIL

- [ ] **Step 3: 实现**

`_to_ozon_attributes`（支持字典值 id）：
```python
def _to_ozon_attributes(attrs: dict) -> list:
    out = []
    for k, v in (attrs or {}).items():
        if isinstance(v, dict) and "dictionary_value_id" in v:
            values = [{"dictionary_value_id": int(v["dictionary_value_id"])}]
        else:
            values = [{"value": str(v.get("value") if isinstance(v, dict) else v)}]
        out.append({"complex_id": 0, "id": int(k), "values": values})
    return out
```
`create_product` 签名与 item：
```python
async def create_product(self, *, client_id, api_key, offer_id, title, description,
                         category_id, attributes, images, price, stock, barcode,
                         type_id=None, depth=None, width=None, height=None,
                         weight=None, dimension_unit="mm", weight_unit="g") -> PublishResult:
    item = {"offer_id": str(offer_id), "name": title or "", "description_category_id": category_id,
            "type_id": type_id, "price": _fmt_price(price), "currency_code": "RUB",
            "barcode": barcode or "", "images": images or [],
            "depth": depth, "width": width, "height": height, "dimension_unit": dimension_unit,
            "weight": weight, "weight_unit": weight_unit,
            "attributes": _to_ozon_attributes(attributes)}
    if self._dry_run:
        return PublishResult(ok=True, ozon_product_id="DRYRUN", status="pending_review",
                             raw={"dry_run": {"items": [item]}})
    # ...原网络提交逻辑不变
```
`base.py` Protocol 的 `create_product` 增同名关键字参数（默认值）。
`mock.py` `create_product` 增 `**kwargs` 或同名默认参数以兼容新调用。
`publisher.py` `_call_seller` create 分支透传：
```python
    if d.mode == "create":
        return await seller.create_product(
            client_id=client_id, api_key=api_key, offer_id=offer_id, title=d.title or "",
            description=d.description or "", category_id=d.category_id, attributes=d.attributes or {},
            images=d.images or [], price=price, stock=d.stock_qty, barcode=d.barcode,
            type_id=d.type_id, depth=d.depth, width=d.width, height=d.height,
            weight=d.weight, dimension_unit=d.dimension_unit, weight_unit=d.weight_unit)
```

- [ ] **Step 4: 运行确认通过 + 回归**

Run: `cd server && python -m pytest tests/test_ozon_seller_real.py -q && python -m pytest -q`
Expected: PASS，0 warnings

- [ ] **Step 5: 提交**

```bash
git add server/app/services/ozon_seller/base.py server/app/services/ozon_seller/real.py server/app/services/ozon_seller/mock.py server/app/workers/publisher.py server/tests/test_ozon_seller_real.py
git commit -m "feat(seller): create_product 带 type_id/尺寸/重量/属性字典值"
```

---

### Task 9: 自建必填校验 + 补充信息回写端点

**Files:**
- Modify: `server/app/workers/publisher.py`（`confirm_draft` 校验扩展）
- Modify: `server/app/api/listing.py`（新增 `POST /listing/{draft_id}/confirm-create-fields`）
- Test: `server/tests/test_confirm_create_fields.py`

**Interfaces:**
- Consumes: 草稿新字段（Task 5）。
- Produces: `POST /listing/{draft_id}/confirm-create-fields` body `{type_id, depth, width, height, weight, dimension_unit?, weight_unit?, attributes?}` → 写回草稿；`confirm_draft` 对 `mode=="create"` 增校验 `type_id` + 尺寸(depth/width/height/weight) 齐全，缺则返回错误不推进。

- [ ] **Step 1: 写失败测试**

```python
# server/tests/test_confirm_create_fields.py
import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_confirm_create_fields_writes_and_gates(client: AsyncClient, admin_headers, seeded_create_draft):
    # seeded_create_draft: mode=create、有 category_id/images 但缺 type_id/尺寸, 返回 draft_id
    body = {"type_id": 93080, "depth": 100, "width": 80, "height": 50, "weight": 250,
            "attributes": {"85": {"dictionary_value_id": 1000}}}
    r = await client.post(f"/api/listing/{seeded_create_draft}/confirm-create-fields", json=body, headers=admin_headers)
    assert r.status_code == 200
    # confirm_draft 现在应通过(不再因缺字段被拒)
    c = await client.post(f"/api/listing/{seeded_create_draft}/confirm", headers=admin_headers)
    assert c.status_code == 200
```

- [ ] **Step 2: 运行确认失败**

Run: `cd server && python -m pytest tests/test_confirm_create_fields.py -q`
Expected: FAIL（端点不存在）

- [ ] **Step 3: 实现**

`confirm_draft`（现有对 create 校验 category_id/images，扩展）：
```python
    if d.mode == "create":
        if d.category_id is None or not d.images:
            return {"ok": False, "error": "自建缺类目或图片"}
        if d.type_id is None or None in (d.depth, d.width, d.height, d.weight):
            return {"ok": False, "error": "自建缺类型或尺寸/重量, 请先补充"}
```
`api/listing.py` 新端点：
```python
from pydantic import BaseModel
class CreateFieldsIn(BaseModel):
    type_id: int; depth: int; width: int; height: int; weight: int
    dimension_unit: str = "mm"; weight_unit: str = "g"; attributes: dict | None = None

@router.post("/{draft_id}/confirm-create-fields")
async def confirm_create_fields(draft_id: int, body: CreateFieldsIn, s: AsyncSession = Depends(get_session), _: User = Depends(require_role("operator"))):
    d = (await s.execute(select(ListingDraft).where(ListingDraft.id == draft_id))).scalar_one_or_none()
    if not d:
        raise HTTPException(404, "草稿不存在")
    d.type_id = body.type_id; d.depth = body.depth; d.width = body.width; d.height = body.height
    d.weight = body.weight; d.dimension_unit = body.dimension_unit; d.weight_unit = body.weight_unit
    if body.attributes is not None:
        merged = dict(d.attributes or {}); merged.update({str(k): v for k, v in body.attributes.items()})
        d.attributes = merged
    await s.commit()
    return {"ok": True}
```

- [ ] **Step 4: 运行确认通过**

Run: `cd server && python -m pytest tests/test_confirm_create_fields.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add server/app/workers/publisher.py server/app/api/listing.py server/tests/test_confirm_create_fields.py
git commit -m "feat(listing): 自建必填校验 + 补充信息回写端点"
```

---

### Task 10: 上架审核页——自建补充信息表单

**Files:**
- Modify: `web/src/pages/ListingReview.tsx`
- Create: `web/src/api/ozonCatalog.ts`
- Test: `web/src/pages/ListingReview.test.tsx`（追加）

**Interfaces:**
- Consumes: `GET /ozon-catalog/{types,attributes,attribute-values}`、`POST /listing/{id}/confirm-create-fields`。
- 行为：草稿 `mode==="create"` 行展开「补充信息」按钮/抽屉：选类型、填尺寸(长/宽/高)+重量、按必填属性选值 → 保存调 confirm-create-fields。

- [ ] **Step 1: 写失败测试**

```tsx
// 追加：ListingReview 对 create 草稿显示"补充信息"入口
import { render, screen } from "@testing-library/react";
import { vi } from "vitest";
vi.mock("../api/client", () => ({ api: { get: vi.fn().mockResolvedValue({ data: [
  { id: 1, mode: "create", title: "自建品", category_id: 100, status: "draft" }] }), post: vi.fn() } }));
import ListingReview from "./ListingReview";
test("自建草稿显示补充信息入口", async () => {
  render(<ListingReview />);
  expect(await screen.findByText(/补充信息/)).toBeInTheDocument();
});
```

- [ ] **Step 2: 运行确认失败**

Run: `cd web && npx vitest run src/pages/ListingReview -q`
Expected: FAIL

- [ ] **Step 3: 实现**

新增 `web/src/api/ozonCatalog.ts`：
```ts
import { api } from "./client";
export const getTypes = () => api.get("/ozon-catalog/types").then(r => r.data);
export const getAttributes = (category_id: number, type_id: number) =>
  api.get("/ozon-catalog/attributes", { params: { category_id, type_id } }).then(r => r.data);
export const getAttributeValues = (category_id: number, type_id: number, attribute_id: number) =>
  api.get("/ozon-catalog/attribute-values", { params: { category_id, type_id, attribute_id } }).then(r => r.data);
export const confirmCreateFields = (draftId: number, body: any) =>
  api.post(`/listing/${draftId}/confirm-create-fields`, body).then(r => r.data);
```
`ListingReview.tsx`：草稿列表对 `mode==="create"` 的行加「补充信息」按钮 → 打开 Drawer/Modal：
- 类型 Select（`getTypes`，按草稿 category_id 过滤对应 types）。
- 尺寸：长/宽/高 InputNumber + 重量 InputNumber（单位默认 mm/g，可下拉）。
- 必填属性：选类型后 `getAttributes(category_id, type_id)`，`is_required` 项渲染；`dictionary_id>0` 用 Select（`getAttributeValues` → `{dictionary_value_id:id}`），否则 Input（`{value}`）。
- 保存 → `confirmCreateFields(draftId, {type_id, depth, width, height, weight, attributes})` → 成功 toast + 刷新。

- [ ] **Step 4: 运行确认通过 + build**

Run: `cd web && npx vitest run src/pages/ListingReview -q && npm run build`
Expected: PASS + build 成功

- [ ] **Step 5: 提交**

```bash
git add web/src/pages/ListingReview.tsx web/src/api/ozonCatalog.ts web/src/pages/ListingReview.test.tsx
git commit -m "feat(web): 上架审核自建补充信息表单(类型/尺寸/必填属性)"
```

---

## 收尾（全部任务后）
- 更新 `docs/功能测试清单-真实集成准备.md`：把自动上品状态从"❌ 暂不能"更正为"跟卖✅(dry-run/真实按开关)、自建✅(需在上架审核补充类型/尺寸/属性)"，并补上品操作步骤（切真实模式、先 dry-run、店铺配凭证、自建补充信息）。
- 更新 `README.md` 相关小节（若有上品/配置说明）。
- 全套后端 `pytest -q` 0 warnings + 前端 `npm run build` + `vitest run` 通过。
- 重建 docker（web+api+worker）验证：`WEB_PORT=18080 DB_PORT=15432 REDIS_PORT=16379 API_PORT=18000 docker compose up -d --build`。

## 自查
- 覆盖 spec：A(接线 T1-3、开关/ dry-run T1/T2/T4)、B(字段 T5、catalog T6-7、create 全字段 T8、校验/回写 T9、前端表单 T10) —— 全覆盖。
- 类型一致：`resolve_seller(session)`、`OzonCatalog` 方法名、`create_product` 新参名、草稿字段名在各 Task 间一致。
- 无占位符：各步含实际代码/命令。
- 安全：默认 mock + 默认 dry-run + `_boom_transport` 断言 dry-run 不发网络。

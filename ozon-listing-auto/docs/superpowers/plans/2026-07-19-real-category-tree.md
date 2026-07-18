# 子项 B RealCategoryTree Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`).

**Goal:** 类目树从 mock 固定小树切到真实 Ozon 全量（composer `categoryChildV3`）；`/settings/system` 加 `category_tree_provider` 切换；抽共享 `composer_fetch`；实抓真实响应对齐解析。

**Architecture:** 抽 `composer_fetch`(composer 与 RealCategoryTree 共用)；`RealCategoryTree.list_children` 调 categoryChildV3 复用 cookie/proxy(get_crawler_conf)；`build_category_tree` 配置驱动；接线 /categories·suggest·build 读配置。前端 TreeSelect 无需改。

**Tech Stack:** FastAPI / httpx(MockTransport) / React+AntD / pytest / Vitest。

## Global Constraints

- Python 3.11；`.venv/bin/python -m pytest`（从 `server/`）。不用系统 python3。
- **pytest 0 warnings**；非 live 全 mock（httpx.MockTransport + monkeypatch sleep，无真实网络/sleep）；真实抓取 `@pytest.mark.live` 默认跳过。
- cookie/proxy 复用 crawler 配置（Fernet）；`/settings/system` 新字段非 secret。
- 角色门：/settings/system → admin；/categories → operator。
- **Task 3 依赖真实 categoryChildV3 样本**（控制者浏览器实抓提供夹具）；缺则 BLOCKED。

---

### Task 1: 抽共享 composer_fetch（composer 委托 + 回归）

**Files:**
- Create: `app/services/ozon_market/composer_http.py`
- Modify: `app/services/ozon_market/composer.py`（委托 composer_fetch，re-export CrawlerBlockedError）
- Modify: `tests/test_composer_hardening.py`（monkeypatch 目标改 composer_http）
- Test: `tests/test_composer_http.py`

**Interfaces:**
- Produces: `composer_fetch(endpoint, params, *, cookie=None, proxy=None, timeout=20.0, min_delay=0.3, max_delay=1.0, max_retries=4, transport=None) -> dict`；`CrawlerBlockedError`（在 composer_http，composer re-export）；`_UA_POOL`、`_BLOCK_CODES`。

- [ ] **Step 1: 写失败测试** `tests/test_composer_http.py`
```python
import pytest, httpx
from app.services.ozon_market.composer_http import composer_fetch, CrawlerBlockedError


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    async def _f(*a, **k): return None
    monkeypatch.setattr("app.services.ozon_market.composer_http.asyncio.sleep", _f)


@pytest.mark.asyncio
async def test_composer_fetch_injects_cookie_and_returns_json():
    seen = {}
    def h(req): seen["cookie"] = req.headers.get("Cookie"); return httpx.Response(200, json={"ok": 1})
    out = await composer_fetch("https://x/api", {"categoryId": 5}, cookie="a=1", transport=httpx.MockTransport(h))
    assert out == {"ok": 1} and seen["cookie"] == "a=1"


@pytest.mark.asyncio
async def test_composer_fetch_blocks_raise():
    def h(req): return httpx.Response(403)
    with pytest.raises(CrawlerBlockedError):
        await composer_fetch("https://x/api", {}, max_retries=2, transport=httpx.MockTransport(h))
```

- [ ] **Step 2: 运行确认失败** `.venv/bin/python -m pytest tests/test_composer_http.py -q` → FAIL（模块不存在）

- [ ] **Step 3: 建 `app/services/ozon_market/composer_http.py`**
```python
"""composer-api 共享请求层：cookie 头注入、随机 UA、间隔抖动、307/403/429 反爬退避。
OzonComposerProvider 与 RealCategoryTree 共用，避免重复请求逻辑。"""
import asyncio
import random
import httpx

_UA_POOL = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
]
_BLOCK_CODES = {429, 403, 307, 301, 302}


class CrawlerBlockedError(RuntimeError):
    """疑似反爬拦截或 cookie 失效，需人工更新 cookie/代理。"""


async def composer_fetch(endpoint: str, params: dict, *, cookie=None, proxy: str | None = None,
                         timeout: float = 20.0, min_delay: float = 0.3, max_delay: float = 1.0,
                         max_retries: int = 4, transport=None) -> dict:
    await asyncio.sleep(random.uniform(min_delay, max_delay))
    headers = {"User-Agent": random.choice(_UA_POOL), "Accept": "application/json"}
    if isinstance(cookie, str) and cookie:
        headers["Cookie"] = cookie
    backoff = 1.0
    for _ in range(max(1, int(max_retries))):
        kw = {"timeout": timeout, "follow_redirects": False}
        if transport is not None:
            kw["transport"] = transport
        elif proxy:
            kw["proxy"] = proxy
        if isinstance(cookie, dict):
            kw["cookies"] = cookie
        async with httpx.AsyncClient(**kw) as c:
            r = await c.get(endpoint, params=params, headers=headers)
        if r.status_code in _BLOCK_CODES:
            await asyncio.sleep(backoff)
            backoff *= 2
            continue
        r.raise_for_status()
        return r.json()
    raise CrawlerBlockedError(
        f"疑似反爬/cookie 失效，请在爬虫配置更新 cookie 或代理（{endpoint} {params}）")
```

- [ ] **Step 4: 改 `app/services/ozon_market/composer.py`** —— 委托 composer_fetch，re-export CrawlerBlockedError。
读现有文件；把 `_UA_POOL`/`_BLOCK_CODES`/`CrawlerBlockedError` 定义删掉，改为 `from app.services.ozon_market.composer_http import composer_fetch, CrawlerBlockedError`（re-export：模块级保留名字 `CrawlerBlockedError` 供 `from ...composer import CrawlerBlockedError` 继续可用）。`_ENDPOINT` 保留。把 `_fetch` 改为：
```python
    async def _fetch(self, page_url: str) -> dict:
        return await composer_fetch(
            _ENDPOINT, {"url": page_url}, cookie=self._cookie, proxy=self._proxy,
            timeout=self._timeout, min_delay=self._min_delay, max_delay=self._max_delay,
            max_retries=self._max_retries, transport=self._transport)
```
删除不再用的 `_headers`/`_client`/`asyncio`/`random` import（若 composer 不再直接用）。`__init__`、search/category/seller 方法签名不变。

- [ ] **Step 5: 改 `tests/test_composer_hardening.py`** —— monkeypatch 目标改为 composer_http（sleep 现在那里）。
把 `monkeypatch.setattr("app.services.ozon_market.composer.asyncio.sleep", ...)` 改为 `"app.services.ozon_market.composer_http.asyncio.sleep"`。其余不变（`OzonComposerProvider(transport=...)` 仍经 `_fetch`→composer_fetch 用 transport）。

- [ ] **Step 6: 运行测试通过 + 回归**
`.venv/bin/python -m pytest tests/test_composer_http.py tests/test_composer_hardening.py -q && .venv/bin/python -m pytest tests -q` → 全绿 0 warnings（现有 composer 硬化测试须仍绿）。

- [ ] **Step 7: 提交**
```bash
git add app/services/ozon_market/composer_http.py app/services/ozon_market/composer.py tests/test_composer_http.py tests/test_composer_hardening.py
git commit -m "refactor(cattree): 抽共享 composer_fetch(composer 委托), 供 RealCategoryTree 复用"
```

---

### Task 2: /settings/system category_tree_provider + build_category_tree + RealCategoryTree 骨架 + 接线

**Files:**
- Modify: `app/schemas/system.py`, `app/api/system.py`（加 category_tree_provider）
- Create: `app/services/ozon_market/category_tree_real.py`
- Modify: `app/services/category_tree.py`（build_category_tree）
- Modify: `app/api/category.py`（/categories 加 session 读配置；suggest 读配置）
- Modify: `app/api/listing.py`（build 传配置 tree）
- Test: `tests/test_category_tree_config.py`

**Interfaces:**
- Produces: `/settings/system` 增 `category_tree_provider`；`RealCategoryTree(cookie,proxy,timeout,max_retries,transport)` with `list_children(*, parent_id)`（解析 Task 3 对齐）+ `all_leaves()->[]`；`async def build_category_tree(session, name)`。

- [ ] **Step 1: 写失败测试** `tests/test_category_tree_config.py`
```python
import pytest, httpx
from app.core.security import hash_password
from app.models import User


async def _admin(client, db_session):
    db_session.add(User(username="a", password_hash=hash_password("p"), role="admin"))
    await db_session.commit()
    tok = (await client.post("/auth/login", data={"username": "a", "password": "p"})).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


@pytest.mark.asyncio
async def test_system_category_tree_provider_roundtrip(client, db_session):
    h = await _admin(client, db_session)
    await client.put("/settings/system", headers=h, json={"ozon_seller_provider": "mock", "category_tree_provider": "real"})
    g = (await client.get("/settings/system", headers=h)).json()
    assert g["category_tree_provider"] == "real" and g["ozon_seller_provider"] == "mock"


@pytest.mark.asyncio
async def test_build_category_tree_selects(db_session):
    from app.services.category_tree import build_category_tree, MockCategoryTree
    from app.services.ozon_market.category_tree_real import RealCategoryTree
    assert isinstance(await build_category_tree(db_session, "mock"), MockCategoryTree)
    assert isinstance(await build_category_tree(db_session, "real"), RealCategoryTree)


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    async def _f(*a, **k): return None
    monkeypatch.setattr("app.services.ozon_market.composer_http.asyncio.sleep", _f)


@pytest.mark.asyncio
async def test_real_tree_blocks_raise():
    from app.services.ozon_market.category_tree_real import RealCategoryTree
    from app.services.ozon_market.composer_http import CrawlerBlockedError
    t = RealCategoryTree(max_retries=2, transport=httpx.MockTransport(lambda r: httpx.Response(403)))
    with pytest.raises(CrawlerBlockedError):
        await t.list_children(parent_id=None)


@pytest.mark.asyncio
async def test_categories_endpoint_default_mock(client, db_session):
    h = await _admin(client, db_session)
    r = await client.get("/categories", headers=h)   # 默认 mock, 返回固定小树根
    assert r.status_code == 200 and isinstance(r.json(), list) and r.json()
```

- [ ] **Step 2: 运行确认失败** → FAIL（category_tree_provider/build_category_tree/RealCategoryTree 不存在）

- [ ] **Step 3: 改 `app/schemas/system.py`**
```python
class SystemIn(BaseModel):
    ozon_seller_provider: str = "mock"
    category_tree_provider: str = "mock"   # mock | real

class SystemOut(BaseModel):
    ozon_seller_provider: str = "mock"
    category_tree_provider: str = "mock"
```

- [ ] **Step 4: 改 `app/api/system.py`** —— read/write 补 category_tree_provider：
read 返回 `category_tree_provider=m.get("category_tree_provider", "mock")`；write 加 `await store.set_value(s, _CAT, "category_tree_provider", body.category_tree_provider, is_secret=False, updated_by=u.id)`，返回时带上。

- [ ] **Step 5: 建 `app/services/ozon_market/category_tree_real.py`**
```python
"""RealCategoryTree：composer categoryChildV3 → 真实 Ozon 类目树。复用 composer_fetch(cookie/proxy/退避)。
解析层独立；categoryChildV3 真实结构由 Task 3 用实抓样本对齐(此处为初版容错解析)。"""
from app.services.ozon_market.composer_http import composer_fetch

_CATEGORY_CHILD = "https://api.ozon.ru/composer-api.bx/_action/v2/categoryChildV3"


class RealCategoryTree:
    name = "real"

    def __init__(self, cookie=None, proxy: str | None = None, timeout: float = 20.0,
                 max_retries: int = 4, transport=None):
        self._cookie = cookie
        self._proxy = proxy
        self._timeout = timeout
        self._max_retries = max_retries
        self._transport = transport

    async def list_children(self, *, parent_id: int | None) -> list[dict]:
        params = {"categoryId": parent_id} if parent_id is not None else {}
        data = await composer_fetch(_CATEGORY_CHILD, params, cookie=self._cookie, proxy=self._proxy,
                                    timeout=self._timeout, max_retries=self._max_retries, transport=self._transport)
        return _parse_category_children(data)   # Task 3 对齐真实结构

    def all_leaves(self) -> list[dict]:
        return []   # 真实树巨大；suggest_category 对非 mock 树用 list_children(parent_id=None)


def _parse_category_children(payload: dict) -> list[dict]:
    """初版容错解析（Task 3 用实抓样本对齐真实字段路径）。找不到返回 []，不崩。"""
    items = payload.get("categories") or payload.get("items") or []
    out = []
    for it in items if isinstance(items, list) else []:
        cid = it.get("id") or it.get("categoryId")
        if cid is None:
            continue
        out.append({"id": int(cid), "name": it.get("title") or it.get("name"),
                    "path": it.get("path") or it.get("title") or it.get("name"),
                    "leaf": bool(it.get("isLeaf") or it.get("leaf"))})
    return out
```

- [ ] **Step 6: 改 `app/services/category_tree.py`** —— 加 build_category_tree：
```python
async def build_category_tree(session, name: str):
    """配置驱动：real → get_crawler_conf 取 cookie/proxy 构造 RealCategoryTree；mock → MockCategoryTree。"""
    if name == "real":
        from app.services.ozon_market.category_tree_real import RealCategoryTree
        from app.services.crawler_conf import get_crawler_conf
        c = await get_crawler_conf(session)
        return RealCategoryTree(cookie=c.get("cookie") or None, proxy=c.get("proxy") or None,
                                timeout=c["timeout"], max_retries=c["max_retries"])
    return MockCategoryTree()
```
（`get_category_tree` 同步版保留。）

- [ ] **Step 7: 接线 `app/api/category.py`** ——
- `categories` 端点：加 `s: AsyncSession = Depends(get_session)`；读配置 provider（`from app.services.settings_store import get_category`：`name = (await get_category(s,"system")).get("category_tree_provider","mock")`）；`return await (await build_category_tree(s, name)).list_children(parent_id=parent_id)`。import build_category_tree。
- `suggest` 端点：`tree=get_category_tree("mock")` → `tree=await build_category_tree(s, name)`（同上读配置）。
- import：`from app.services.category_tree import build_category_tree`（保留或去掉 get_category_tree 若无用）。

- [ ] **Step 8: 接线 `app/api/listing.py`（build）** —— `build_create_drafts(..., tree=await build_category_tree(s, name))`（读 system.category_tree_provider）。import build_category_tree + get_category。

- [ ] **Step 9: 运行测试通过 + 回归**
`.venv/bin/python -m pytest tests/test_category_tree_config.py -q && .venv/bin/python -m pytest tests -q` → 全绿 0 warnings。

- [ ] **Step 10: 提交**
```bash
git add app/schemas/system.py app/api/system.py app/services/ozon_market/category_tree_real.py app/services/category_tree.py app/api/category.py app/api/listing.py tests/test_category_tree_config.py
git commit -m "feat(cattree): /settings/system category_tree_provider + build_category_tree + RealCategoryTree 骨架 + 接线"
```

---

### Task 3: 实抓真实 categoryChildV3 对齐解析

> **前置依赖：** 需真实 categoryChildV3 响应样本。控制者派发时用浏览器实抓提供夹具 `tests/fixtures/category_child.json`（+ 随附期望值）。**缺夹具则 BLOCKED——停止索取，不盲写。**

**Files:**
- Create: `server/tests/fixtures/category_child.json`（控制者提供）
- Modify: `app/services/ozon_market/category_tree_real.py`（`_parse_category_children` 对齐真实结构）
- Test: `tests/test_category_tree_real.py`

- [ ] **Step 1: 落夹具** 控制者提供的真实 categoryChildV3 响应。

- [ ] **Step 2: 写失败测试** `tests/test_category_tree_real.py`（期望值随夹具由控制者给定；示例）
```python
import json, pathlib, httpx, pytest
from app.services.ozon_market.category_tree_real import RealCategoryTree

_FIX = pathlib.Path(__file__).parent / "fixtures" / "category_child.json"


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    async def _f(*a, **k): return None
    monkeypatch.setattr("app.services.ozon_market.composer_http.asyncio.sleep", _f)


@pytest.mark.asyncio
async def test_real_tree_parses_children():
    payload = json.loads(_FIX.read_text())
    t = RealCategoryTree(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=payload)))
    nodes = await t.list_children(parent_id=None)
    assert len(nodes) > 0
    n = nodes[0]
    assert n["id"] and n["name"] and "leaf" in n     # 关键字段（具体断言随夹具给定）
```

- [ ] **Step 3: 运行确认失败**（初版解析对真实结构抽不出/抽错）

- [ ] **Step 4: 按夹具对齐 `_parse_category_children`** —— 定位真实响应里类目子节点数组（按实抓结构），抽 id/name/path/leaf。解析层独立、容错（缺字段返 None/[] 不崩）。

- [ ] **Step 5: 运行测试通过 + 回归** `.venv/bin/python -m pytest tests/test_category_tree_real.py -q && .venv/bin/python -m pytest tests -q` → 全绿 0 warnings。

- [ ] **Step 6: 提交**
```bash
git add app/services/ozon_market/category_tree_real.py tests/test_category_tree_real.py server/tests/fixtures/category_child.json
git commit -m "feat(cattree): parser 对齐真实 categoryChildV3(实抓样本驱动)"
```

---

### Task 4: 前端 system 加类目树切换 + @live + 文档 + 回归

**Files:**
- Modify: `web/src/pages/settings/SystemSettings.tsx`（加 category_tree_provider 切换）
- Modify: `web/src/pages/settings/SystemSettings.test.tsx`（若存在）
- Create: `server/tests/test_live_category_tree.py`（@live）
- Modify: `README.md`、`docs/去mock化-真实集成总规划.md`（标 B 完成）
- Test: 全量回归

- [ ] **Step 1: 读现有** `web/src/pages/settings/SystemSettings.tsx`（M7/crawler 子项建的 ozon_seller_provider 切换）与其 api `web/src/api/system.ts`、测试。

- [ ] **Step 2: 改 SystemSettings.tsx** —— 加一个 `category_tree_provider` Select（mock/real），随现有 ozon_seller_provider 一同 putSystem；提示"real 需在爬虫配置填 cookie/proxy"。api/system.ts 的 put/get 传/收字段自动带上（body 透传）。

- [ ] **Step 3: 建 `server/tests/test_live_category_tree.py`**（@live 默认跳过）
```python
"""真实 categoryChildV3 抓取冒烟(@live 默认跳过)。跑法：
  OZON_COOKIE=... .venv/bin/python -m pytest tests/test_live_category_tree.py -m live -v"""
import os, pytest
from app.services.ozon_market.category_tree_real import RealCategoryTree


@pytest.mark.live
@pytest.mark.asyncio
async def test_live_category_children():
    cookie = os.environ.get("OZON_COOKIE")
    if not cookie:
        pytest.skip("需设置 OZON_COOKIE")
    t = RealCategoryTree(cookie=cookie, proxy=os.environ.get("OZON_PROXY") or None)
    nodes = await t.list_children(parent_id=None)
    assert isinstance(nodes, list) and len(nodes) > 0
```

- [ ] **Step 4: 更新 `README.md` + 总规划** —— README 加「真实类目树」说明（/settings/system 切 category_tree_provider real + 爬虫 cookie；前端 TreeSelect 自动真实全量；@live 跑法）；总规划标 B 已完成。

- [ ] **Step 5: 全量回归**
```bash
cd server && .venv/bin/python -m pytest tests -q
cd ../web && source ~/.nvm/nvm.sh && nvm use 20 >/dev/null && npx vitest run && npm run build
```
Expected: 后端全绿 0 warnings（live +1 deselected）；前端通过 + build。

- [ ] **Step 6: 提交**
```bash
git add web/src/pages/settings/SystemSettings.tsx server/tests/test_live_category_tree.py README.md docs/去mock化-真实集成总规划.md
git commit -m "feat(cattree): 前端 system 类目树切换 + @live + README/总规划标 B 完成"
```

---

## Self-Review

- **Spec 覆盖**：§2.1 composer_fetch→Task 1；§2.2 RealCategoryTree→Task 2(骨架)+Task 3(解析对齐)；§2.3 配置切换→Task 2；§2.4 接线→Task 2；§3 测试贯穿；@live→Task 4；前端→Task 4。全覆盖。
- **占位符扫描**：无 TBD；后端含完整代码；Task 3 解析对齐明标依赖真实样本、缺则 BLOCKED；前端 Task 4 以结构给出并要求先读现有 SystemSettings。
- **名称一致**：`composer_fetch`(Task 1 定义、composer/RealCategoryTree 用)；`CrawlerBlockedError`(composer_http, composer re-export)；`RealCategoryTree(cookie,proxy,timeout,max_retries,transport)` + `list_children`；`build_category_tree(session,name)`(Task 2 定义、category api/listing 用)；`category_tree_provider`(schema/api/前端/接线一致)。
- **落地注意**：抽 composer_fetch 后 sleep 在 composer_http → 现有 composer 硬化测试 monkeypatch 目标须改（Task 1 Step 5 已写）；CrawlerBlockedError 须仍可从 composer import（re-export，Task 1 Step 4）；`/categories` 端点原无 session，需加 `Depends(get_session)`（Task 2 Step 7）；Task 3 强依赖真实样本，派发前确认夹具就位。

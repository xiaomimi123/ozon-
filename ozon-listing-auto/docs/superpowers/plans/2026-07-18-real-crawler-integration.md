# 真实爬虫接入（composer-api）+ 爬虫/Seller 配置页 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让系统能用真实 Ozon 前台数据采集：爬虫 cookie/代理配置进后台页、collector 配置驱动构造 composer provider、反爬硬化（307/cookie 失效可操作提示）、parser 对齐真实响应、Ozon Seller real/mock 切换搬进配置页。

**Architecture:** 复用现有配置中心（Fernet 加密 settings）与 provider 抽象。爬虫配置存 `settings/crawler`，系统配置存 `settings/system`。collector 读配置构造 `OzonComposerProvider(cookie, proxy)`。parser 按真实样本夹具重写。sync=mock 规律不变；真实抓取走 `@pytest.mark.live`。

**Tech Stack:** FastAPI / SQLAlchemy / httpx(MockTransport 供测试) / ARQ / React+Ant Design / Vitest / pytest。

## Global Constraints

- Python 3.11；测试 `.venv/bin/python -m pytest`（从 `ozon-listing-auto/server/`）。不用系统 python3(3.9)。
- **pytest 0 warnings**；非 live 测试全 mock（无真实网络、无真实 sleep：monkeypatch/注入）。真实抓取一律 `@pytest.mark.live`（默认跳过）。
- 密钥（cookie/proxy）Fernet 加密（复用 `settings_store`），GET 脱敏，**留空不覆盖**已存值（同 M6 imagegen）。
- 角色门：爬虫/系统配置 → `require_role("admin")`。
- **sync=true 的 API 恒 mock**；真实 provider 只在 sync=false 的 worker 路径按配置选。
- 沿用现有中文 docstring 风格与命名。

---

### Task 1: 配置后端 —— 爬虫配置(/settings/crawler) + 系统配置(/settings/system) + Seller 切换生效

**Files:**
- Create: `app/schemas/crawler.py`, `app/schemas/system.py`
- Create: `app/api/crawler.py`, `app/api/system.py`
- Create: `app/services/crawler_conf.py`（`get_crawler_conf` + `DEFAULT_CRAWLER`）
- Modify: `app/main.py`（注册两路由）
- Modify: `app/workers/publisher.py`（`run_publish`/`run_publish_tick` 读 system 配置选 seller）
- Test: `tests/test_crawler_system_config.py`

**Interfaces:**
- Produces: `GET/PUT /settings/crawler`（cookie/proxy 脱敏、留空不覆盖）、`GET/PUT /settings/system`（ozon_seller_provider）；`get_crawler_conf(session)->dict`（cookie/proxy/timeout/min_delay/max_delay/max_retries，数值已解析）；`DEFAULT_CRAWLER`。

- [ ] **Step 1: 写失败测试** `tests/test_crawler_system_config.py`

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
async def test_crawler_settings_mask_and_keep_blank(client, db_session):
    h = await _admin(client, db_session)
    await client.put("/settings/crawler", headers=h, json={
        "cookie": "abc=1; def=2", "proxy": "http://u:pw@h:8080", "timeout": 15, "max_retries": 3})
    g = (await client.get("/settings/crawler", headers=h)).json()
    assert g["cookie"] == "***" and g["proxy"] == "***"           # 脱敏
    assert str(g["timeout"]) in ("15", "15.0")
    # 留空不覆盖 cookie/proxy
    await client.put("/settings/crawler", headers=h, json={"cookie": "", "proxy": "", "timeout": 25})
    from app.services.crawler_conf import get_crawler_conf
    conf = await get_crawler_conf(db_session)
    assert conf["cookie"] == "abc=1; def=2" and conf["proxy"] == "http://u:pw@h:8080"
    assert conf["timeout"] == 25.0


@pytest.mark.asyncio
async def test_crawler_conf_defaults(db_session):
    from app.services.crawler_conf import get_crawler_conf, DEFAULT_CRAWLER
    conf = await get_crawler_conf(db_session)
    assert conf["max_retries"] == DEFAULT_CRAWLER["max_retries"] and conf["cookie"] in ("", None)


@pytest.mark.asyncio
async def test_system_seller_provider_toggle(client, db_session):
    h = await _admin(client, db_session)
    await client.put("/settings/system", headers=h, json={"ozon_seller_provider": "real"})
    g = (await client.get("/settings/system", headers=h)).json()
    assert g["ozon_seller_provider"] == "real"
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/python -m pytest tests/test_crawler_system_config.py -q`
Expected: FAIL（路由/模块不存在）

- [ ] **Step 3: 建 `app/services/crawler_conf.py`**

```python
"""爬虫配置读取：合并 settings/crawler(Fernet 存)与默认值，数值解析。供 provider 构造与后续复用。"""
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.settings_store import get_category

DEFAULT_CRAWLER = {"cookie": "", "proxy": "", "timeout": 20.0,
                   "min_delay": 0.3, "max_delay": 1.0, "max_retries": 4}


async def get_crawler_conf(session: AsyncSession) -> dict:
    raw = await get_category(session, "crawler")   # {key: 解密值(str)}
    conf = dict(DEFAULT_CRAWLER)
    if raw.get("cookie"):
        conf["cookie"] = raw["cookie"]
    if raw.get("proxy"):
        conf["proxy"] = raw["proxy"]
    for k, cast in (("timeout", float), ("min_delay", float), ("max_delay", float), ("max_retries", int)):
        if raw.get(k) not in (None, ""):
            try:
                conf[k] = cast(float(raw[k])) if cast is int else cast(raw[k])
            except (ValueError, TypeError):
                pass
    return conf
```

- [ ] **Step 4: 建 `app/schemas/crawler.py`**

```python
from pydantic import BaseModel

class CrawlerIn(BaseModel):
    cookie: str = ""
    proxy: str = ""
    timeout: float = 20.0
    min_delay: float = 0.3
    max_delay: float = 1.0
    max_retries: int = 4

class CrawlerOut(BaseModel):
    cookie: str | None = None      # 脱敏
    proxy: str | None = None       # 脱敏
    timeout: float = 20.0
    min_delay: float = 0.3
    max_delay: float = 1.0
    max_retries: int = 4
```

- [ ] **Step 5: 建 `app/schemas/system.py`**

```python
from pydantic import BaseModel

class SystemIn(BaseModel):
    ozon_seller_provider: str = "mock"   # mock | real

class SystemOut(BaseModel):
    ozon_seller_provider: str = "mock"
```

- [ ] **Step 6: 建 `app/api/crawler.py`**（cookie/proxy 留空不覆盖 + 脱敏，仿 imagegen）

```python
"""爬虫配置 API(admin)：cookie/proxy Fernet 加密脱敏、留空不覆盖；timeout/间隔/重试明文。"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.db import get_session
from app.api.deps import require_role
from app.models import User
from app.schemas.crawler import CrawlerIn, CrawlerOut
from app.services import settings_store as store

router = APIRouter(prefix="/settings/crawler", tags=["settings"])
_CAT = "crawler"


@router.get("", response_model=CrawlerOut)
async def read(s: AsyncSession = Depends(get_session), _: User = Depends(require_role("admin"))):
    m = await store.get_category_masked(s, _CAT)
    return CrawlerOut(cookie=m.get("cookie"), proxy=m.get("proxy"),
                      timeout=float(m.get("timeout") or 20.0), min_delay=float(m.get("min_delay") or 0.3),
                      max_delay=float(m.get("max_delay") or 1.0), max_retries=int(float(m.get("max_retries") or 4)))


@router.put("", response_model=CrawlerOut)
async def write(body: CrawlerIn, s: AsyncSession = Depends(get_session), u: User = Depends(require_role("admin"))):
    if body.cookie:
        await store.set_value(s, _CAT, "cookie", body.cookie, is_secret=True, updated_by=u.id)
    if body.proxy:
        await store.set_value(s, _CAT, "proxy", body.proxy, is_secret=True, updated_by=u.id)
    await store.set_value(s, _CAT, "timeout", str(body.timeout), is_secret=False, updated_by=u.id)
    await store.set_value(s, _CAT, "min_delay", str(body.min_delay), is_secret=False, updated_by=u.id)
    await store.set_value(s, _CAT, "max_delay", str(body.max_delay), is_secret=False, updated_by=u.id)
    await store.set_value(s, _CAT, "max_retries", str(body.max_retries), is_secret=False, updated_by=u.id)
    await s.commit()
    return CrawlerOut(cookie="***" if body.cookie else None, proxy="***" if body.proxy else None,
                      timeout=body.timeout, min_delay=body.min_delay, max_delay=body.max_delay,
                      max_retries=body.max_retries)
```

- [ ] **Step 7: 建 `app/api/system.py`**

```python
"""系统配置 API(admin)：全局 Ozon Seller provider(mock|real)切换。"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.db import get_session
from app.api.deps import require_role
from app.models import User
from app.schemas.system import SystemIn, SystemOut
from app.services import settings_store as store

router = APIRouter(prefix="/settings/system", tags=["settings"])
_CAT = "system"


@router.get("", response_model=SystemOut)
async def read(s: AsyncSession = Depends(get_session), _: User = Depends(require_role("admin"))):
    m = await store.get_category(s, _CAT)
    return SystemOut(ozon_seller_provider=m.get("ozon_seller_provider", "mock"))


@router.put("", response_model=SystemOut)
async def write(body: SystemIn, s: AsyncSession = Depends(get_session), u: User = Depends(require_role("admin"))):
    await store.set_value(s, _CAT, "ozon_seller_provider", body.ozon_seller_provider, is_secret=False, updated_by=u.id)
    await s.commit()
    return SystemOut(ozon_seller_provider=body.ozon_seller_provider)
```

- [ ] **Step 8: 改 `app/main.py`** —— 注册两路由。**关键：须先于通用 `/settings/{category}`（settings_router）注册**（否则被 catch-all 吞，同 M6 imagegen）。在 import 区加：
```python
from app.api.crawler import router as crawler_router
from app.api.system import router as system_router
```
在 include_router 区，把这两行放到 `app.include_router(settings_router)` **之前**（与 imagegen_router 同处理）：
```python
app.include_router(crawler_router)
app.include_router(system_router)
```

- [ ] **Step 9: 改 `app/workers/publisher.py`** —— seller 选择读 system 配置。

`run_publish`：
```python
async def run_publish(ctx, task_id: int) -> dict:
    from app.core.db import async_session
    from app.core.config import settings
    from app.services.settings_store import get_category
    async with async_session() as s:
        name = (await get_category(s, "system")).get("ozon_seller_provider") or settings.ozon_seller_provider
    return await run_publish_core(async_session, task_id, seller=get_ozon_seller(name))
```
`run_publish_tick`：把 `seller = get_ozon_seller(settings.ozon_seller_provider)` 改为先读 system 配置：
```python
    from app.services.settings_store import get_category
    async with async_session() as s:
        name = (await get_category(s, "system")).get("ozon_seller_provider") or settings.ozon_seller_provider
    seller = get_ozon_seller(name)
```
（保留 `from app.core.config import settings` 作回退默认；sync=true 的 `/listing/publish`、`/publish/tick` 路径仍恒 mock，不改。）

- [ ] **Step 10: 运行测试通过 + 回归**

Run: `.venv/bin/python -m pytest tests/test_crawler_system_config.py -q && .venv/bin/python -m pytest tests -q`
Expected: 全绿 0 warnings。

- [ ] **Step 11: 提交**

```bash
git add app/schemas/crawler.py app/schemas/system.py app/api/crawler.py app/api/system.py app/services/crawler_conf.py app/main.py app/workers/publisher.py tests/test_crawler_system_config.py
git commit -m "feat(crawler): 爬虫配置(/settings/crawler cookie/proxy)+系统配置(/settings/system seller 切换)+run_publish 读配置"
```

---

### Task 2: OzonComposerProvider 硬化 + build_ozon_provider + collector 接入

**Files:**
- Modify: `app/services/ozon_market/composer.py`（cookie 头注入、307/3xx 反爬、CrawlerBlockedError、配置参数、可注入 transport/sleep）
- Modify: `app/services/ozon_market/factory.py`（`build_ozon_provider`）
- Modify: `app/workers/collector.py`（用 `build_ozon_provider`；捕获 CrawlerBlockedError 置 failed）
- Test: `tests/test_composer_hardening.py`

**Interfaces:**
- Consumes: `get_crawler_conf`（Task 1）。
- Produces: `CrawlerBlockedError`；`OzonComposerProvider(cookie=None, proxy=None, timeout=20, min_delay=0.3, max_delay=1.0, max_retries=4, transport=None)`；`async def build_ozon_provider(session, name)`。

- [ ] **Step 1: 写失败测试** `tests/test_composer_hardening.py`（用 `httpx.MockTransport` 免真实网络；monkeypatch sleep 免真实等待）

```python
import pytest
import httpx
from app.services.ozon_market.composer import OzonComposerProvider, CrawlerBlockedError


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    async def _fast(*a, **k):
        return None
    monkeypatch.setattr("app.services.ozon_market.composer.asyncio.sleep", _fast)


@pytest.mark.asyncio
async def test_cookie_header_injected_and_success():
    seen = {}
    def handler(request: httpx.Request) -> httpx.Response:
        seen["cookie"] = request.headers.get("Cookie")
        return httpx.Response(200, json={"widgetStates": {}})
    prov = OzonComposerProvider(cookie="abc=1; def=2", transport=httpx.MockTransport(handler))
    await prov.search_by_keyword("phone", 1)
    assert seen["cookie"] == "abc=1; def=2"


@pytest.mark.asyncio
async def test_307_retried_then_success():
    calls = {"n": 0}
    def handler(request):
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(307, headers={"Location": "/challenge"})
        return httpx.Response(200, json={"widgetStates": {}})
    prov = OzonComposerProvider(max_retries=5, transport=httpx.MockTransport(handler))
    out = await prov.search_by_keyword("phone", 1)
    assert calls["n"] == 3 and out == []


@pytest.mark.asyncio
async def test_persistent_block_raises_actionable_error():
    def handler(request):
        return httpx.Response(403)
    prov = OzonComposerProvider(max_retries=3, transport=httpx.MockTransport(handler))
    with pytest.raises(CrawlerBlockedError):
        await prov.search_by_keyword("phone", 1)
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/python -m pytest tests/test_composer_hardening.py -q`
Expected: FAIL（CrawlerBlockedError/transport 参数不存在）

- [ ] **Step 3: 改 `app/services/ozon_market/composer.py`**（整体替换为）

```python
"""Composer-api 真实请求层：cookie 头注入、随机 UA、间隔抖动、307/403/429 反爬退避，解析交由 parser。"""
import asyncio
import random
import httpx
from app.services.ozon_market.base import OzonProductDTO
from app.services.ozon_market.parser import parse_search_widgets

_UA_POOL = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
]
_ENDPOINT = "https://api.ozon.ru/composer-api.bx/page/json/v2"
_BLOCK_CODES = {429, 403, 307, 301, 302}   # 反爬信号：限流/禁止/重定向到挑战页


class CrawlerBlockedError(RuntimeError):
    """疑似反爬拦截或 cookie 失效，需人工更新 cookie/代理。"""


class OzonComposerProvider:
    name = "composer"

    def __init__(self, cookie=None, proxy: str | None = None, timeout: float = 20.0,
                 min_delay: float = 0.3, max_delay: float = 1.0, max_retries: int = 4, transport=None):
        self._cookie = cookie            # str(原始 Cookie 头) 或 dict 或 None
        self._proxy = proxy
        self._timeout = timeout
        self._min_delay = min_delay
        self._max_delay = max_delay
        self._max_retries = max(1, int(max_retries))
        self._transport = transport      # 测试注入 httpx.MockTransport

    def _headers(self) -> dict:
        h = {"User-Agent": random.choice(_UA_POOL), "Accept": "application/json"}
        if isinstance(self._cookie, str) and self._cookie:
            h["Cookie"] = self._cookie
        return h

    def _client(self) -> httpx.AsyncClient:
        kw = {"timeout": self._timeout, "follow_redirects": False}
        if self._transport is not None:
            kw["transport"] = self._transport
        else:
            if self._proxy:
                kw["proxy"] = self._proxy
        if isinstance(self._cookie, dict):
            kw["cookies"] = self._cookie
        return httpx.AsyncClient(**kw)

    async def _fetch(self, page_url: str) -> dict:
        await asyncio.sleep(random.uniform(self._min_delay, self._max_delay))
        params = {"url": page_url}
        backoff = 1.0
        for _ in range(self._max_retries):
            async with self._client() as c:
                r = await c.get(_ENDPOINT, params=params, headers=self._headers())
            if r.status_code in _BLOCK_CODES:
                await asyncio.sleep(backoff)
                backoff *= 2
                continue
            r.raise_for_status()
            return r.json()
        raise CrawlerBlockedError(
            f"疑似反爬/cookie 失效，请在爬虫配置更新 cookie 或代理（url={page_url}）")

    async def search_by_keyword(self, kw: str, page: int) -> list[OzonProductDTO]:
        return parse_search_widgets(await self._fetch(f"/search/?text={kw}&page={page}"))

    async def list_by_category(self, category_url: str, page: int) -> list[OzonProductDTO]:
        sep = "&" if "?" in category_url else "?"
        return parse_search_widgets(await self._fetch(f"{category_url}{sep}page={page}"))

    async def list_by_seller(self, seller_id: str, page: int) -> list[OzonProductDTO]:
        return parse_search_widgets(await self._fetch(f"/seller/{seller_id}/?page={page}"))
```

- [ ] **Step 4: 改 `app/services/ozon_market/factory.py`** —— 加配置驱动构造。文件末尾加：

```python
async def build_ozon_provider(session, name: str):
    """配置驱动构造：composer 读 settings/crawler(cookie/proxy/超时/间隔/重试)；mock/apify 同 get_provider。"""
    if name == "composer":
        from app.services.ozon_market.composer import OzonComposerProvider
        from app.services.crawler_conf import get_crawler_conf
        c = await get_crawler_conf(session)
        return OzonComposerProvider(
            cookie=c.get("cookie") or None, proxy=c.get("proxy") or None,
            timeout=c["timeout"], min_delay=c["min_delay"], max_delay=c["max_delay"],
            max_retries=c["max_retries"])
    return get_provider(name)
```
（`get_provider` 保留不变。）

- [ ] **Step 5: 改 `app/workers/collector.py`** —— 用 build_ozon_provider + 捕获 CrawlerBlockedError。

顶部 import：`from app.services.ozon_market.factory import build_ozon_provider`（保留原 get_provider import 或移除若不再用）。
把 `provider = get_provider(task.provider)` 改为 `provider = await build_ozon_provider(s, task.provider)`。
在采集循环 `try:` 的 except 中（拉页处），捕获 CrawlerBlockedError 单独处理：任务置 failed 并记可操作提示。找到拉页的 try/except（`if entry_type == "seller": ...` 那段），确保外层有：
```python
        except CrawlerBlockedError as exc:
            async with session_factory() as s:
                task = (await s.execute(select(CollectTask).where(CollectTask.id == task_id))).scalar_one()
                task.status = "failed"
                task.stats = {**(task.stats or {}), "error": str(exc)}
                await s.commit()
            log.error("crawler_blocked", error=str(exc))
            return {"inserted": total_inserted, "skipped": total_skipped, "pages": pages_done, "error": str(exc)}
```
（import `from app.services.ozon_market.composer import CrawlerBlockedError`。若现有采集循环无 try 包裹拉页，按最小改动加上；不改动其余续跑/去重逻辑。读现有 collector.py 拉页段落后精确插入。）

- [ ] **Step 6: 运行测试通过 + 回归**

Run: `.venv/bin/python -m pytest tests/test_composer_hardening.py -q && .venv/bin/python -m pytest tests -q`
Expected: 全绿 0 warnings。（现有 collector mock 采集测试须仍通过。）

- [ ] **Step 7: 提交**

```bash
git add app/services/ozon_market/composer.py app/services/ozon_market/factory.py app/workers/collector.py tests/test_composer_hardening.py
git commit -m "feat(crawler): composer cookie 头注入+307/403/429 反爬退避+CrawlerBlockedError+配置驱动构造+collector 接入"
```

---

### Task 3: 前端 —— 爬虫配置页 + 系统设置（Seller 切换）

**Files:**
- Create: `web/src/api/crawler.ts`, `web/src/api/system.ts`
- Create: `web/src/pages/settings/CrawlerSettings.tsx`, `web/src/pages/settings/SystemSettings.tsx`
- Modify: 路由 `web/src/App.tsx` + 菜单 `web/src/pages/Layout.tsx`
- Test: `web/src/pages/settings/CrawlerSettings.test.tsx`

**Interfaces:** 后端 `/settings/crawler`、`/settings/system`（Task 1）。

- [ ] **Step 1: 读现有** `web/src/api/client.ts`（`import { api } from "./client"` 范式）、`web/src/pages/settings/ImagegenSettings.tsx`（配置页范式）、其 `.test.tsx`（Vitest+mock 范式）、`App.tsx`/`Layout.tsx`（路由/菜单）。

- [ ] **Step 2: 建 api 客户端**（mirror 现有 `api/*.ts`）

`web/src/api/crawler.ts`:
```typescript
import { api } from "./client";
export const getCrawler = () => api.get("/settings/crawler").then(r => r.data);
export const putCrawler = (body: any) => api.put("/settings/crawler", body).then(r => r.data);
```
`web/src/api/system.ts`:
```typescript
import { api } from "./client";
export const getSystem = () => api.get("/settings/system").then(r => r.data);
export const putSystem = (body: any) => api.put("/settings/system", body).then(r => r.data);
```

- [ ] **Step 3: 建 `CrawlerSettings.tsx`**（仿 ImagegenSettings）：Form —— cookie（`Input.TextArea`，提示"从浏览器 devtools 复制 Cookie 头；留空则不修改"）、proxy（`Input.Password`）、timeout/min_delay/max_delay（`InputNumber`）、max_retries（`InputNumber`）→ `putCrawler`；加载时 cookie/proxy 显示占位（脱敏 `***` 不回填明文）。

- [ ] **Step 4: 建 `SystemSettings.tsx`**：Form —— `ozon_seller_provider` `Select`（mock/real）→ `putSystem`；提示"real 需在店铺管理配置真实 Ozon 凭据"。

- [ ] **Step 5: 路由 + 菜单** —— `App.tsx` 加 `/settings/crawler`、`/settings/system`；`Layout.tsx` 菜单加对应入口（归到"系统设置"分组）。

- [ ] **Step 6: 写渲染测试** `CrawlerSettings.test.tsx`（mirror ImagegenSettings.test.tsx）：mock `../../api/crawler`，渲染断言关键控件（cookie/proxy/保存），触发保存断言 `putCrawler` 调用。

- [ ] **Step 7: 前端测试 + 构建**

Run（从 `web/`）: `source ~/.nvm/nvm.sh && nvm use 20 >/dev/null && npx vitest run && npm run build`
Expected: 全部通过 + build 成功。

- [ ] **Step 8: 提交**

```bash
git add web/src/api/crawler.ts web/src/api/system.ts web/src/pages/settings/CrawlerSettings.tsx web/src/pages/settings/SystemSettings.tsx web/src/pages/settings/CrawlerSettings.test.tsx web/src/App.tsx web/src/pages/Layout.tsx
git commit -m "feat(crawler): 前端爬虫配置页(cookie/proxy)+系统设置(Seller 切换)"
```

---

### Task 4: parser 对齐真实响应（真实样本夹具）

> **前置依赖：** 本任务需要真实 composer-api 响应样本。控制者会在派发本任务时提供夹具文件 `tests/fixtures/composer_search.json`（+ 可选类目/卖家）。**若夹具缺失，本任务 BLOCKED——停止并向控制者索取样本，不要盲目改 parser。**

**Files:**
- Create: `server/tests/fixtures/composer_search.json`（真实样本，控制者提供）
- Modify: `app/services/ozon_market/parser.py`（按样本对齐字段抽取）
- Test: `tests/test_parser_real.py`

**Interfaces:** Produces `parse_search_widgets(payload) -> list[OzonProductDTO]`，字段映射对齐真实 widget。

- [ ] **Step 1: 落夹具** —— 把控制者提供的真实响应存为 `server/tests/fixtures/composer_search.json`。

- [ ] **Step 2: 写失败测试** `tests/test_parser_real.py`（断言基于真实样本的预期——具体条数/字段由控制者随夹具给出的"期望"确定；示例结构）

```python
import json
import pathlib
from app.services.ozon_market.parser import parse_search_widgets

_FIX = pathlib.Path(__file__).parent / "fixtures" / "composer_search.json"


def test_parse_real_search_extracts_products():
    payload = json.loads(_FIX.read_text())
    products = parse_search_widgets(payload)
    assert len(products) > 0                                  # 真实样本应抽出商品
    p = products[0]
    assert p.sku and p.title and p.price is not None          # 关键字段非空
    assert p.product_url                                      # 商品链接
    # 图集/月销/评分等按样本实际可得字段补充断言（控制者随夹具给定）
```

- [ ] **Step 3: 运行确认失败**

Run: `.venv/bin/python -m pytest tests/test_parser_real.py -q`
Expected: FAIL（旧 parser 按 `searchResults`/`items` 盲写，抽不出真实结构）

- [ ] **Step 4: 按样本重写 `parse_search_widgets`** —— 定位真实商品 widget（按 key 前缀容错，如 `searchResultsV2*`/`tileGrid*`/`skuGrid*`），从真实 item 结构抽取 sku/title/price(含 cardPrice)/月销/评分/评论/图集/product_url/parent_sku 映射到 `OzonProductDTO`。**具体字段路径以夹具真实结构为准**（解析层独立，端点/结构变更只改此文件）。保留对旧结构与多版本的容错（找不到字段返回 None 而非崩溃）。

- [ ] **Step 5: 运行测试通过 + 回归**

Run: `.venv/bin/python -m pytest tests/test_parser_real.py -q && .venv/bin/python -m pytest tests -q`
Expected: 全绿 0 warnings。（现有 mock 采集/解析测试须仍通过——若旧 parser 单测断言旧结构，按真实结构更新之。）

- [ ] **Step 6: 提交**

```bash
git add app/services/ozon_market/parser.py tests/test_parser_real.py server/tests/fixtures/composer_search.json
git commit -m "feat(crawler): parser 对齐真实 composer-api 响应(样本夹具驱动)"
```

---

### Task 5: 文档 + @live 真实抓取测试 + 全量回归

**Files:**
- Modify: `README.md`（真实爬虫配置说明 + Seller 切换）
- Create: `docs/真实爬虫接入说明.md`
- Create: `server/tests/test_live_crawler.py`（`@pytest.mark.live` 默认跳过）
- Test: 全量回归

- [ ] **Step 1: 读现有** `README.md`（配置/环境变量段）。

- [ ] **Step 2: 建 `server/tests/test_live_crawler.py`**（真实抓取，默认跳过，用户带 cookie 跑）

```python
"""真实 composer-api 抓取冒烟（@live 默认跳过）。跑法：
先在后台 /settings/crawler 配好 cookie/proxy，或设 OZON_COOKIE/OZON_PROXY 环境变量后：
  .venv/bin/python -m pytest tests/test_live_crawler.py -m live -v"""
import os
import pytest
from app.services.ozon_market.composer import OzonComposerProvider


@pytest.mark.live
@pytest.mark.asyncio
async def test_live_search_returns_products():
    cookie = os.environ.get("OZON_COOKIE")
    proxy = os.environ.get("OZON_PROXY") or None
    if not cookie:
        pytest.skip("需设置 OZON_COOKIE 环境变量")
    prov = OzonComposerProvider(cookie=cookie, proxy=proxy)
    products = await prov.search_by_keyword("телефон", 1)
    assert len(products) > 0
    assert products[0].sku and products[0].title
```

- [ ] **Step 3: 更新 `README.md`** —— 加「真实采集」小节：后台 `/settings/crawler` 填 cookie(浏览器复制)/proxy；建 composer 任务即走真实抓取；反爬失效在任务列表看到可操作提示；`/settings/system` 切 Seller real/mock；`@live` 测试跑法。保持精简。

- [ ] **Step 4: 建 `docs/真实爬虫接入说明.md`** —— 目的/用法/关键设计：cookie 获取步骤（devtools 复制）、代理配置、三入口(关键词/类目/卖家)、反爬硬化(307/403/429 退避 + cookie 失效提示)、parser 解析层独立(结构变更只改 parser)、Seller real/mock 切换、live 测试跑法、已知 live 后置(cookie 池轮换、RealCategoryTree、端点校正)。

- [ ] **Step 5: 全量回归**

Run:
```bash
cd server && .venv/bin/python -m pytest tests -q
cd ../web && source ~/.nvm/nvm.sh && nvm use 20 >/dev/null && npx vitest run && npm run build
```
Expected: 后端全绿 0 warnings；前端测试通过 + build 成功。

- [ ] **Step 6: 提交**

```bash
git add README.md docs/真实爬虫接入说明.md server/tests/test_live_crawler.py
git commit -m "docs(crawler): README + 真实爬虫接入说明 + @live 抓取冒烟测试"
```

---

## Self-Review（写计划后自检）

- **Spec 覆盖**：§2.1 爬虫配置→Task 1；§2.2 系统配置+seller 切换→Task 1；§3.1 build_ozon_provider+collector→Task 2；§3.2 硬化→Task 2；§4 parser→Task 4；§5.1 前端→Task 3；§5.2 测试贯穿；§5.3 验收→全量；live→Task 5。全覆盖。
- **占位符扫描**：无 TBD 式空步骤；后端/配置步骤含完整代码；parser Task 4 明确标注**依赖真实样本夹具、缺失即 BLOCKED**（不盲写）；前端 Task 3 以结构+关键调用给出并要求先读 imagegen 范式。
- **类型/名称一致**：`get_crawler_conf`/`DEFAULT_CRAWLER`（Task 1 定义、Task 2 factory 用）；`CrawlerBlockedError`（Task 2 定义、collector 用）；`OzonComposerProvider(cookie,proxy,timeout,min_delay,max_delay,max_retries,transport)`（Task 2 签名、测试用一致）；`build_ozon_provider(session,name)`（Task 2 定义、collector 用）；`/settings/crawler`·`/settings/system`（Task 1 建、Task 3 前端调、Task 5 文档一致）；seller 读 `settings/system.ozon_seller_provider`（Task 1）。
- **已知落地注意**：`/settings/crawler`·`/settings/system` 须先于通用 `/settings/{category}` 注册（Task 1 Step 8 已注明，同 M6 imagegen）；测试用 `httpx.MockTransport`（无新依赖）+ monkeypatch `composer.asyncio.sleep`（免真实等待，Task 2 已写）；settings 值均以 str 存需解析（Task 1 get_crawler_conf 已处理）；**Task 4 强依赖真实样本，派发前须确认夹具就位**。

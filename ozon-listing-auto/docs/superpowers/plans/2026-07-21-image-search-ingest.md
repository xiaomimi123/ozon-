# 图搜采集核心 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 浏览器截获 1688 拍立淘图搜响应 → POST 后端 → 复用 `parse_offers + dedup_and_upsert` 写入该 Ozon 商品的 `supply_candidates`，接进现有五维评分/上架。

**Architecture:** 后端加一个薄端点 `POST /import/image-search`（token 鉴权 + 校验商品属任务 + 复用现有解析/去重入库）；编排脚本用 Playwright 驱动 AdsPower 拍立淘上传主图并截获响应回传。绕开图搜签名逆向。

**Tech Stack:** Python 3.11 / FastAPI / SQLAlchemy async；Playwright + AdsPower Local API（脚本）。

## Global Constraints

- **最大化复用**：解析 `parse_offers`(parser_ali)、入库去重 `dedup_and_upsert`(candidate_ingest)、embedder `get_embedder`(embedding.factory)、`get_source_conf`(sources.conf)——都不重造。
- 后端 0 warnings；端点用 fixture 做 TDD。编排脚本无自动化测试（依赖 AdsPower/live），交付 README 供用户验证。
- ingest 用 `X-Import-Token` 头（复用 `sources.import_token`，fail-closed），非 JWT（脚本无登录态）。
- 校验 `ozon_product_id` 存在且属于 `task_id`（否则 404）。幂等（dedup_and_upsert 唯一约束兜底）。
- **脚本不含任何验证码绕过/反检测规避代码**（红线）；Claude 不 live 跑抓取。

---

### Task 1: 后端 POST /import/image-search（复用解析+去重入库）

**Files:**
- Modify: `server/app/api/importer.py`（加端点 + import）
- Test: `server/tests/test_image_search_ingest.py`

**Interfaces:**
- Consumes: `parse_offers`、`dedup_and_upsert`、`get_embedder`、`get_source_conf`、`OzonProduct`/`SupplyCandidate`/`ImportCapture`。
- Produces: `POST /import/image-search` body `{task_id:int, ozon_product_id:int, payload:dict}` → `{inserted, skipped, clusters, captured}`。

- [ ] **Step 1: 写失败测试**

```python
# server/tests/test_image_search_ingest.py
import pytest
from sqlalchemy import select, func
from app.core.security import hash_password
from app.models import User, CollectTask, OzonProduct, SupplyCandidate, ImportCapture
from app.services import settings_store

_PAYLOAD = {"data": {"offerList": [
    {"offerId": 111, "subject": "连衣裙", "priceInfo": {"price": "18.5"}, "imageUrl": "http://i/1.jpg",
     "detailUrl": "http://d/111", "company": {"name": "甲厂"}},
    {"offerId": 222, "subject": "碎花裙", "priceInfo": {"price": "9.9"}, "imageUrl": "http://i/2.jpg",
     "detailUrl": "http://d/222", "company": {"name": "乙厂"}},
]}}

async def _setup(db_session):
    db_session.add(User(username="adm", password_hash=hash_password("p"), role="admin"))
    await settings_store.set_value(db_session, "sources", "import_token", "TK", is_secret=True)
    t = CollectTask(name="t", entry_type="keyword", entry_value="x", provider="mock", source_platforms=["ali1688"])
    db_session.add(t); await db_session.flush()
    p = OzonProduct(task_id=t.id, sku="S1", title="phone")
    db_session.add(p); await db_session.commit()
    return t.id, p.id

@pytest.mark.asyncio
async def test_image_search_ingest_and_idempotent(client, db_session):
    tid, pid = await _setup(db_session)
    body = {"task_id": tid, "ozon_product_id": pid, "payload": _PAYLOAD}
    r = await client.post("/import/image-search", json=body, headers={"X-Import-Token": "TK"})
    assert r.status_code == 200 and r.json()["inserted"] == 2 and r.json()["captured"] == 2
    n = (await db_session.execute(select(func.count()).select_from(SupplyCandidate).where(
        SupplyCandidate.ozon_product_id == pid, SupplyCandidate.task_id == tid))).scalar_one()
    assert n == 2
    await client.post("/import/image-search", json=body, headers={"X-Import-Token": "TK"})  # 再来一次
    n2 = (await db_session.execute(select(func.count()).select_from(SupplyCandidate).where(
        SupplyCandidate.ozon_product_id == pid))).scalar_one()
    assert n2 == 2  # 幂等去重
    caps = (await db_session.execute(select(func.count()).select_from(ImportCapture))).scalar_one()
    assert caps == 2  # 每次存 capture

@pytest.mark.asyncio
async def test_bad_token(client, db_session):
    tid, pid = await _setup(db_session)
    r = await client.post("/import/image-search", json={"task_id": tid, "ozon_product_id": pid, "payload": _PAYLOAD},
                          headers={"X-Import-Token": "WRONG"})
    assert r.status_code == 401

@pytest.mark.asyncio
async def test_product_not_in_task(client, db_session):
    tid, pid = await _setup(db_session)
    r = await client.post("/import/image-search", json={"task_id": tid, "ozon_product_id": 999999, "payload": _PAYLOAD},
                          headers={"X-Import-Token": "TK"})
    assert r.status_code == 404
```

- [ ] **Step 2: 运行确认失败**

Run: `cd server && .venv/bin/python -m pytest tests/test_image_search_ingest.py -q`
Expected: FAIL（404 无路由）

- [ ] **Step 3: 实现（扩 importer.py）**

顶部 import 追加：
```python
from pydantic import BaseModel
from app.core.config import settings
from app.models import OzonProduct   # 加入现有 from app.models import 行或单列
from app.services.sources.parser_ali import parse_offers
from app.services.candidate_ingest import dedup_and_upsert
from app.services.embedding.factory import get_embedder
```
加端点：
```python
class ImageSearchIn(BaseModel):
    task_id: int
    ozon_product_id: int
    payload: dict

@router.post("/image-search")
async def ingest_image_search(body: ImageSearchIn, x_import_token: str | None = Header(default=None),
                              s: AsyncSession = Depends(get_session)):
    conf = await get_source_conf(s)
    token = conf.get("import_token") or ""
    if not token or x_import_token != token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "无效导入令牌")
    prod = (await s.execute(select(OzonProduct).where(
        OzonProduct.id == body.ozon_product_id, OzonProduct.task_id == body.task_id))).scalar_one_or_none()
    if not prod:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "商品不存在或不属于该任务")
    dtos = parse_offers(body.payload, conf.get("ali1688_offer_list_path", "data.offerList"))
    s.add(ImportCapture(platform="ali1688", keyword=f"图搜:product={body.ozon_product_id}",
                        raw=body.payload, item_count=len(dtos)))
    embedder = get_embedder(settings.embedder)
    result = await dedup_and_upsert(s, body.task_id, body.ozon_product_id, dtos, embedder)
    await s.commit()
    return {**result, "captured": len(dtos)}
```

- [ ] **Step 4: 运行确认通过 + 回归**

Run: `cd server && .venv/bin/python -m pytest tests/test_image_search_ingest.py -q && .venv/bin/python -m pytest -q`
Expected: PASS，0 warnings

- [ ] **Step 5: 提交**

```bash
git add server/app/api/importer.py server/tests/test_image_search_ingest.py
git commit -m "feat(import): POST /import/image-search 图搜响应入 supply_candidates(复用parse_offers+dedup_and_upsert)"
```

---

### Task 2: 拍立淘图搜编排脚本

**Files:**
- Create: `scripts/collect_1688_image_search.py`、`scripts/README-image-search.md`

**Interfaces:**
- 用 AdsPower Local API + Playwright；**无自动化测试**（外部依赖），review 审代码正确性；用户 live 验证。

- [ ] **Step 1: 脚本**

```python
# scripts/collect_1688_image_search.py
"""AdsPower + Playwright 拍立淘图搜采集：下载 Ozon 主图 → 环境内打开 1688 拍立淘上传页 → 上传图 →
截获图搜接口响应 → POST /import/image-search {task_id, ozon_product_id, payload}。
socks5/扩展无关/1688 登录态在 AdsPower 环境内预配置。不含任何验证码绕过/反检测规避。
用法: python scripts/collect_1688_image_search.py --user-id <env> --backend http://host/api --token <import_token> \
      --task-id 1 --product-id 5 --image-url <Ozon主图URL> [--search-url <拍立淘上传页>] [--match offer/search]
"""
import argparse, json, tempfile, time, urllib.request

def _get(url):
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.loads(r.read().decode())

def _post(url, body, token):
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method="POST",
                                 headers={"Content-Type": "application/json", "X-Import-Token": token})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://local.adspower.net:50325")
    ap.add_argument("--user-id", required=True)
    ap.add_argument("--backend", required=True)   # 如 http://localhost:18080/api
    ap.add_argument("--token", required=True)      # import_token
    ap.add_argument("--task-id", type=int, required=True)
    ap.add_argument("--product-id", type=int, required=True)
    ap.add_argument("--image-url", required=True)  # Ozon 主图 URL
    ap.add_argument("--search-url", default="https://s.1688.com/youyuan/index.htm")  # 拍立淘上传页, 按实际调
    ap.add_argument("--file-input", default="input[type=file]")  # 文件 input 选择器, 按实际调
    ap.add_argument("--match", default="imageSearch,offer/search,pcImageSearch")  # 图搜接口 URL 命中子串
    ap.add_argument("--dwell", type=float, default=8.0)
    a = ap.parse_args()

    # 下载 Ozon 主图到临时文件
    img = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
    with urllib.request.urlopen(a.image_url, timeout=30) as r:
        img.write(r.read())
    img.close()

    start = _get(f"{a.api}/api/v1/browser/start?user_id={a.user_id}")
    ws = start["data"]["ws"]["puppeteer"]
    subs = [x for x in a.match.split(",") if x]
    captured = {}
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(ws)
        ctx = browser.contexts[0]
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        def on_response(resp):
            if any(sub in resp.url for sub in subs) and not captured:
                try:
                    captured["payload"] = resp.json()
                except Exception:
                    pass
        page.on("response", on_response)

        page.goto(a.search_url, wait_until="domcontentloaded")
        try:
            page.set_input_files(a.file_input, img.name)  # 上传主图触发拍立淘; 遇滑块请人工处理
        except Exception as e:
            print("上传图片失败(检查 --file-input 选择器与页面):", e)
        time.sleep(a.dwell)
        browser.close()
    _get(f"{a.api}/api/v1/browser/stop?user_id={a.user_id}")

    if "payload" in captured:
        body = {"task_id": a.task_id, "ozon_product_id": a.product_id, "payload": captured["payload"]}
        print("回传后端:", _post(f"{a.backend.rstrip('/')}/import/image-search", body, a.token))
    else:
        print("未截获图搜响应(检查 --match 子串 / 是否触发拍立淘 / 是否遇滑块)")

if __name__ == "__main__":
    main()
```

- [ ] **Step 2: README**

`scripts/README-image-search.md`：写明——AdsPower 建环境→挂 socks5(国内住宅)→登录 1688→`pip install playwright && playwright install chromium`→跑脚本示例；**`--search-url`(拍立淘上传页)、`--file-input`(文件 input 选择器)、`--match`(图搜接口子串) 均随 1688 页面变，需按实际抓包/审元素调**；遇滑块人工处理（本子项目不自动过验证码）；首次成功后原始响应存后端 ImportCapture，若解析 0 条按 `ali1688_offer_list_path` 校准；合规见 `docs/1688-拼多多采集-选型与成本对比.md` §8。**此脚本 live 由用户验证。**

- [ ] **Step 3: 提交**

```bash
git add scripts/collect_1688_image_search.py scripts/README-image-search.md
git commit -m "feat(scripts): 拍立淘图搜编排脚本(AdsPower+Playwright 上传图/截流/回传)"
```

---

## 收尾（全部任务后）
- 后端 `pytest -q` 0 warnings。
- 重建 docker api：`WEB_PORT=18080 DB_PORT=15432 REDIS_PORT=16379 API_PORT=18000 docker compose up -d --build api`。
- 交给用户 live 验证：AdsPower 拍立淘上传主图 → 截获响应回传 → 该 Ozon 商品 supply_candidates 入库 → 现有评分/审核台可见。首个 raw 回传后按需校准 `ali1688_offer_list_path`。

## 自查
- 覆盖 spec：端点(T1，复用 parse_offers+dedup_and_upsert)、脚本(T2，live)。
- 复用不造轮子；token fail-closed；product 属 task 校验；幂等。
- 离线可测(端点) vs live(脚本) 边界清晰；无占位符。

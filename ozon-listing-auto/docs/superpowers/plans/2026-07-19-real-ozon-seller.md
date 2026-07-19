# 子项 E RealOzonSeller 端点校正 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`).

**Goal:** RealOzonSeller 三方法对齐真实 Ozon Seller API：跟卖 `/v1/product/import-by-sku`、自建 `/v3/product/import`、状态 `/v1/product/import/info`；属性格式转换；状态映射；@live 沙箱脚手架。

**Architecture:** 重写 `real.py`（`Client-Id`+`Api-Key` 头，httpx，transport 可注入测试）。非 live 用 MockTransport 验请求/响应形状；真实调用 `@pytest.mark.live` 默认跳过。走 `OZON_SELLER_PROVIDER=real` 或 `/settings/system`（M7）切换（现状已就绪，本项不改切换）。

**Tech Stack:** httpx(MockTransport) / pytest。

## Global Constraints

- Python 3.11；`.venv/bin/python -m pytest`（从 `server/`）。不用系统 python3。
- **pytest 0 warnings**；非 live 全 mock（MockTransport，无真实网络）；真实调用 `@pytest.mark.live` 默认跳过。
- `RealOzonSeller` 必须惰性/内部 import httpx（现状：方法内 import）；transport 参数供测试注入。
- 不改 base Protocol 签名（create_follow_offer/create_product/get_product_status 参数不变）；不改 publisher/factory 切换逻辑。

---

### Task 1: real.py 三方法重写对齐真实端点 + 属性转换 + MockTransport 测试

**Files:**
- Modify: `app/services/ozon_seller/real.py`（整体重写）
- Test: `tests/test_ozon_seller_real.py`

**Interfaces:** `RealOzonSeller(timeout=30.0, transport=None)`；三方法签名不变（对齐 base Protocol）；`_to_ozon_attributes(attrs) -> list`。

- [ ] **Step 1: 写失败测试** `tests/test_ozon_seller_real.py`
```python
import json
import pytest
import httpx
from app.services.ozon_seller.real import RealOzonSeller, _to_ozon_attributes


def _prov(handler):
    return RealOzonSeller(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_follow_offer_uses_import_by_sku():
    seen = {}
    def h(req):
        seen["path"] = req.url.path
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, json={"result": {"task_id": 123, "unmatched_sku_list": []}})
    res = await _prov(h).create_follow_offer(client_id="c", api_key="k", target_sku="298789742",
                                             barcode="460", price=2300.0, stock=5, offer_id="A1")
    assert seen["path"] == "/v1/product/import-by-sku"
    assert seen["body"]["items"][0]["sku"] == 298789742 and seen["body"]["items"][0]["offer_id"] == "A1"
    assert res.ok and res.ozon_product_id == "123" and res.status == "pending_review"


@pytest.mark.asyncio
async def test_follow_offer_unmatched_fails():
    def h(req):
        return httpx.Response(200, json={"result": {"task_id": 0, "unmatched_sku_list": [298789742]}})
    res = await _prov(h).create_follow_offer(client_id="c", api_key="k", target_sku="298789742",
                                             barcode=None, price=1.0, stock=1, offer_id="A1")
    assert not res.ok and res.status == "failed"


@pytest.mark.asyncio
async def test_create_product_uses_v3_import():
    seen = {}
    def h(req):
        seen["path"] = req.url.path
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, json={"result": {"task_id": 456}})
    res = await _prov(h).create_product(client_id="c", api_key="k", offer_id="A1", title="童鞋",
                                        description="d", category_id=17028922, attributes={"85": "Samsung"},
                                        images=["http://x/a.jpg"], price=1000.0, stock=3, barcode="460")
    assert seen["path"] == "/v3/product/import"
    it = seen["body"]["items"][0]
    assert it["name"] == "童鞋" and it["description_category_id"] == 17028922
    assert it["attributes"] == [{"complex_id": 0, "id": 85, "values": [{"value": "Samsung"}]}]
    assert res.ok and res.ozon_product_id == "456"


@pytest.mark.asyncio
@pytest.mark.parametrize("st,expect", [("imported", "approved"), ("failed", "rejected"), ("pending", "pending")])
async def test_get_status_maps(st, expect):
    def h(req):
        assert req.url.path == "/v1/product/import/info"
        return httpx.Response(200, json={"result": {"items": [{"status": st, "product_id": 9}]}})
    out = await _prov(h).get_product_status(client_id="c", api_key="k", ozon_product_id="456")
    assert out == expect


@pytest.mark.asyncio
async def test_get_status_exception_is_pending():
    def h(req):
        return httpx.Response(500)
    out = await _prov(h).get_product_status(client_id="c", api_key="k", ozon_product_id="456")
    assert out == "pending"


def test_to_ozon_attributes():
    assert _to_ozon_attributes({"85": "Samsung", "9048": "红"}) == [
        {"complex_id": 0, "id": 85, "values": [{"value": "Samsung"}]},
        {"complex_id": 0, "id": 9048, "values": [{"value": "红"}]}]
    assert _to_ozon_attributes({}) == [] and _to_ozon_attributes(None) == []
```

- [ ] **Step 2: 运行确认失败** `.venv/bin/python -m pytest tests/test_ozon_seller_real.py -q` → FAIL（旧 real.py 端点/形状不符）

- [ ] **Step 3: 重写 `app/services/ozon_seller/real.py`**（整体替换）
```python
"""RealOzonSeller：对齐真实 Ozon Seller API(api-seller.ozon.ru, Client-Id+Api-Key 头)。
跟卖 /v1/product/import-by-sku、自建 /v3/product/import、状态 /v1/product/import/info。
真实调用 @live 校验(沙箱)；非 live 用 MockTransport 测请求/响应形状。"""
from app.services.ozon_seller.base import PublishResult

_HOST = "https://api-seller.ozon.ru"
_IMPORT_BY_SKU = f"{_HOST}/v1/product/import-by-sku"   # 跟卖：按目标 SKU 克隆卡片建 offer
_IMPORT_V3 = f"{_HOST}/v3/product/import"               # 自建：创建新商品
_IMPORT_INFO = f"{_HOST}/v1/product/import/info"        # 异步导入任务状态


def _to_ozon_attributes(attrs: dict) -> list:
    """草稿 {attr_id: value} → Ozon [{complex_id,id,values:[{value}]}]；非数字 key 跳过。"""
    return [{"complex_id": 0, "id": int(k), "values": [{"value": str(v)}]}
            for k, v in (attrs or {}).items() if str(k).isdigit()]


class RealOzonSeller:
    name = "real"

    def __init__(self, timeout: float = 30.0, transport=None):
        self._timeout = timeout
        self._transport = transport

    def _client(self):
        import httpx
        kw = {"timeout": self._timeout}
        if self._transport is not None:
            kw["transport"] = self._transport
        return httpx.AsyncClient(**kw)

    @staticmethod
    def _headers(client_id, api_key):
        return {"Client-Id": str(client_id), "Api-Key": str(api_key), "Content-Type": "application/json"}

    async def create_follow_offer(self, *, client_id, api_key, target_sku, barcode, price, stock, offer_id) -> PublishResult:
        body = {"items": [{"sku": int(target_sku), "offer_id": str(offer_id),
                           "price": str(price), "currency_code": "RUB"}]}
        try:
            async with self._client() as c:
                r = await c.post(_IMPORT_BY_SKU, headers=self._headers(client_id, api_key), json=body)
                r.raise_for_status()
                data = r.json()
            result = data.get("result", {})
            if result.get("unmatched_sku_list"):
                return PublishResult(ok=False, ozon_product_id=None, status="failed",
                                     raw=data, error=f"SKU 未匹配/禁止复制: {result['unmatched_sku_list']}")
            return PublishResult(ok=True, ozon_product_id=str(result.get("task_id")),
                                 status="pending_review", raw=data)
        except Exception as exc:  # noqa: BLE001
            return PublishResult(ok=False, ozon_product_id=None, status="failed", error=str(exc) or exc.__class__.__name__)

    async def create_product(self, *, client_id, api_key, offer_id, title, description,
                             category_id, attributes, images, price, stock, barcode) -> PublishResult:
        # 注意：v3/product/import 真实自建还需 type_id + 尺寸/重量 + 属性字典值 id，草稿暂无 →
        # 缺字段留空, 真实 import 审核会拒, 需后续扩草稿字段/人工补(见文档)。
        item = {"offer_id": str(offer_id), "name": title or "", "description_category_id": category_id,
                "price": str(price), "currency_code": "RUB", "barcode": barcode or "",
                "images": images or [], "attributes": _to_ozon_attributes(attributes)}
        try:
            async with self._client() as c:
                r = await c.post(_IMPORT_V3, headers=self._headers(client_id, api_key), json={"items": [item]})
                r.raise_for_status()
                data = r.json()
            return PublishResult(ok=True, ozon_product_id=str(data.get("result", {}).get("task_id")),
                                 status="pending_review", raw=data,
                                 error=None)
        except Exception as exc:  # noqa: BLE001
            return PublishResult(ok=False, ozon_product_id=None, status="failed", error=str(exc) or exc.__class__.__name__)

    async def get_product_status(self, *, client_id, api_key, ozon_product_id) -> str:
        # ozon_product_id 实为 create 返回的 import task_id；轮询 import/info 映射状态。
        try:
            task_id = int(ozon_product_id)
        except (TypeError, ValueError):
            return "pending"
        try:
            async with self._client() as c:
                r = await c.post(_IMPORT_INFO, headers=self._headers(client_id, api_key), json={"task_id": task_id})
                r.raise_for_status()
                items = r.json().get("result", {}).get("items", [])
            st = (items[0].get("status") if items else "") or ""
            if st == "imported":
                return "approved"
            if st == "failed":
                return "rejected"
            return "pending"
        except Exception:  # noqa: BLE001  查询失败按未出结果处理, 不误判
            return "pending"
```

- [ ] **Step 4: 运行测试通过 + 回归** `.venv/bin/python -m pytest tests/test_ozon_seller_real.py -q && .venv/bin/python -m pytest tests -q` → 全绿 0 warnings。（现有 mock seller 测试不受影响——只改 real.py。）

- [ ] **Step 5: 提交**
```bash
git add app/services/ozon_seller/real.py tests/test_ozon_seller_real.py
git commit -m "feat(ozon-seller): RealOzonSeller 对齐真实端点(跟卖 import-by-sku/自建 v3 import/状态 import-info)+属性转换"
```

---

### Task 2: @live 沙箱冒烟 + 文档 + 回归

**Files:**
- Create: `server/tests/test_live_ozon_seller.py`（@live）
- Modify: `README.md`、`docs/M4-定价上架说明.md`（或新建 docs/真实 Ozon 上架说明）、`docs/去mock化-真实集成总规划.md`（标 E 完成）
- Test: 全量回归

- [ ] **Step 1: 建 `server/tests/test_live_ozon_seller.py`**（@live 默认跳过）
```python
"""真实/沙箱 Ozon Seller 冒烟(@live 默认跳过)。用法(优先沙箱店):
  OZON_CLIENT_ID=.. OZON_API_KEY=.. OZON_TARGET_SKU=.. \\
    .venv/bin/python -m pytest tests/test_live_ozon_seller.py -m live -v"""
import os, pytest
from app.services.ozon_seller.real import RealOzonSeller


@pytest.mark.live
@pytest.mark.asyncio
async def test_live_follow_offer_and_status():
    cid, key, sku = os.environ.get("OZON_CLIENT_ID"), os.environ.get("OZON_API_KEY"), os.environ.get("OZON_TARGET_SKU")
    if not (cid and key and sku):
        pytest.skip("需设置 OZON_CLIENT_ID/OZON_API_KEY/OZON_TARGET_SKU")
    prov = RealOzonSeller()
    res = await prov.create_follow_offer(client_id=cid, api_key=key, target_sku=sku, barcode=None,
                                         price=1000.0, stock=1, offer_id="live-smoke-1")
    assert res.raw is not None    # 有响应(ok 视 SKU 是否可跟卖)
    if res.ok:
        st = await prov.get_product_status(client_id=cid, api_key=key, ozon_product_id=res.ozon_product_id)
        assert st in ("approved", "pending", "rejected")
```

- [ ] **Step 2: 更新 `README.md`** —— 「真实 Ozon 上架」小节：`/settings/system` 或 `OZON_SELLER_PROVIDER=real` 切真实 + 店铺管理页填 Client-Id/Api-Key；跟卖走 import-by-sku（需真实目标 SKU）；自建 v3/product/import（**缺 type_id/尺寸/属性字典 id，真实自建 import 审核会拒，需后续扩草稿字段**）；库存需单独 /v2/products/stocks（后续）；`@live` 沙箱跑法。
- [ ] **Step 3: 更新 `docs/M4-定价上架说明.md`** —— §5「切真实」处更新为真实端点已对齐（import-by-sku/v3 import/import-info）+ 缺字段说明；或在 docs 下新建《真实 Ozon 上架说明.md》承载。保持与代码一致。
- [ ] **Step 4: 更新 `docs/去mock化-真实集成总规划.md`** —— 子项 E 标「已完成（端点对齐 + @live）」（section 标题 + 矩阵行）。

- [ ] **Step 5: 全量回归**
```bash
cd server && .venv/bin/python -m pytest tests -q
cd ../web && source ~/.nvm/nvm.sh && nvm use 20 >/dev/null && npx vitest run && npm run build
```
Expected: 后端全绿 0 warnings（live +1 deselected）；前端通过 + build（本项无前端改动，确认不破坏）。

- [ ] **Step 6: 提交**
```bash
git add server/tests/test_live_ozon_seller.py README.md docs/
git commit -m "docs(ozon-seller): @live 沙箱冒烟 + README/M4/总规划标 E 完成(含自建数据缺口标注)"
```

---

## Self-Review

- **Spec 覆盖**：§2.1 跟卖 import-by-sku→Task 1；§2.2 自建 v3 import→Task 1；§2.3 状态 import-info→Task 1；§2.4 属性转换→Task 1；§3 测试贯穿；@live+文档→Task 2；数据缺口标注→Task 2 文档。全覆盖。
- **占位符扫描**：无 TBD；后端含完整代码；文档 Task 2 以要点给出（对齐真实端点 + 缺字段诚实标注）。
- **名称/契约一致**：三方法签名与 `base.py` Protocol 完全一致（未改参数）；`_to_ozon_attributes`；transport 注入测试；ozon_product_id 语义=import task_id（get_product_status 据此轮询）。
- **落地注意**：只改 real.py + 加测试，不动 mock/factory/publisher（切换逻辑现状就绪）；MockTransport handler 按路径分派；`@live` 默认跳过；诚实标注自建缺 type_id/尺寸（真实 import 会拒）——不假装可用。

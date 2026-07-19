# 设计文档：子项 E — RealOzonSeller 端点校正（跟卖/自建/状态）

> 去 mock 化子项 E（见《去mock化-真实集成总规划.md》）。日期：2026-07-19。
> 依据：现有 `real.py` 占位、`OzonSellerProvider` 抽象、**联网查证的 Ozon Seller 官方 API**（api-seller.ozon.ru）。用户确认端点校正。

## 1. 目标与范围

**目标** = RealOzonSeller 三方法对齐真实 Ozon Seller API（`Client-Id`+`Api-Key` 头）。

**真实端点（官方文档查证）：**
- **create_follow_offer（跟卖）** → `POST /v1/product/import-by-sku`：按目标 SKU 克隆已有卡片建新 offer。body `{items:[{sku, offer_id, price, currency_code, ...}]}`；异步 `{result:{task_id, unmatched_sku_list}}`。**现占位误用 `/v2/product/import`（已废弃），须改。**
- **create_product（自建）** → `POST /v3/product/import`（v2 废弃）：body item 含 offer_id/name/description_category_id/**type_id**/price(str)/currency_code/vat/barcode/images/attributes/**尺寸重量**；异步 `{result:{task_id}}`。
- **get_product_status（审核轮询）** → `POST /v1/product/import/info` `{task_id}`：`result.items[0].status` ∈ `imported`|`pending`|`failed`（三值明确）+ product_id。

**范围：**
1. 三方法重写对齐真实端点/请求体/异步 task_id。
2. 属性格式转换 `{attr_id: value}` → Ozon `[{complex_id:0, id, values:[{value}]}]`。
3. 状态映射 imported→approved、failed→rejected、其余/异常→pending（不误判）。
4. `@pytest.mark.live`（沙箱）+ 非 live MockTransport 验请求/响应形状 + 文档。

**已知数据缺口（诚实标注）**：v3/product/import 真实自建必填 `type_id` + 尺寸/重量 + 属性字典值 id，现 `listing_drafts` 不带 → 本轮把请求构造对齐、缺字段留空并文档标注（真实自建 import 会因缺 type_id/尺寸被拒，需后续扩草稿字段/用户补）；跟卖 import-by-sku 字段全，可较完整。库存需单独 `/v2/products/stocks`（本轮价在 body，库存留后续/文档标注）。

**依赖你**：真实/沙箱 Client-Id/Api-Key（店铺管理页填）+ 跟卖真实目标 SKU；@live 你跑，按报错迭代。

## 2. 模块与接口（`real.py` 重写）

`RealOzonSeller(timeout=30.0, transport=None)`；`_client()`（timeout + 可注入 transport）；`_headers(client_id, api_key)`（Client-Id/Api-Key/Content-Type）。

### 2.1 create_follow_offer（跟卖）
- `POST https://api-seller.ozon.ru/v1/product/import-by-sku`，body `{"items":[{"sku": int(target_sku), "offer_id": offer_id, "price": str(price), "currency_code": "RUB"}]}`。
- 响应 `result.task_id` + `result.unmatched_sku_list`：unmatched 非空 → `ok=False, status="failed", error="SKU 未匹配/禁止复制"`；否则 `ok=True, ozon_product_id=str(task_id), status="pending_review", raw=data`。异常/非 2xx → failed。

### 2.2 create_product（自建）
- `POST /v3/product/import`，body item `{offer_id, name:title, description_category_id:category_id, price:str(price), currency_code:"RUB", barcode, images:images or [], attributes:_to_ozon_attributes(attributes)}`（type_id/尺寸/重量缺 → 不填）。
- 响应 `result.task_id` → `ok=True, ozon_product_id=str(task_id), status="pending_review", meta 标注缺字段`。异常 → failed。

### 2.3 get_product_status（审核轮询）
- `ozon_product_id` 实为 task_id；`POST /v1/product/import/info` `{"task_id": int(ozon_product_id)}`（不可转 int → 直接返回 "pending"）。
- `result.items[0].status`：`imported`→`approved`、`failed`→`rejected`、其余/无 → `pending`。异常/非 2xx → `pending`。

### 2.4 属性转换
```python
def _to_ozon_attributes(attrs: dict) -> list:
    return [{"complex_id": 0, "id": int(k), "values": [{"value": str(v)}]}
            for k, v in (attrs or {}).items() if str(k).isdigit()]
```

## 3. 测试 + 验收 + 风险

### 3.1 测试（非 live 全 mock，httpx.MockTransport，0 warnings）
- create_follow_offer：断言 POST 路径 `/v1/product/import-by-sku`、body `items[0].sku == int(target_sku)`；`{result:{task_id:123,unmatched_sku_list:[]}}` → ok/pending_review/"123"；unmatched 非空 → ok=False。
- create_product：路径 `/v3/product/import`、body 含 name/description_category_id/转换后 attributes；`{result:{task_id:456}}` → ok=True。
- get_product_status：`/v1/product/import/info`；imported→approved、failed→rejected、pending→pending、异常→pending。
- `_to_ozon_attributes` 转换单测。
- `@pytest.mark.live`（默认跳过）：真实/沙箱 create_follow_offer + get_product_status（env OZON_CLIENT_ID/OZON_API_KEY/OZON_TARGET_SKU）。

### 3.2 验收标准
1. 三方法对齐真实端点 + 请求体（import-by-sku / v3/product/import / import/info）。
2. 状态映射 imported→approved、failed→rejected、其余→pending。
3. 属性 dict→Ozon 格式转换。
4. 非 live 0 warnings + README/docs（含自建数据缺口 type_id/尺寸 + 库存单独设）+ `@live` 齐备。

### 3.3 风险与降级
| 风险 | 应对 |
|---|---|
| 自建缺 type_id/尺寸/属性字典 id | 请求对齐、缺字段留空 + 文档标注；真实 import 会拒, 需后续扩草稿字段 |
| 跟卖目标禁止复制/SKU 不匹配 | unmatched_sku_list → ok=False 明确 |
| import/info 其他状态值 | 仅 imported/failed 明确映射, 其余→pending 兜底 |
| 沙箱与文档差异 | @live 沙箱迭代；端点常量化便于快速改 |
| 库存需单独 /v2/products/stocks | 本轮价在 body；库存单独 call 留后续/文档标注 |

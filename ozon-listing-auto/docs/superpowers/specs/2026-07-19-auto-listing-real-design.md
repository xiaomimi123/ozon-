# 设计文档：自动上品（真实 Ozon Seller）接线 + 自建补齐

> 日期：2026-07-19。子项目①（三项之一：自动上品 → 货源账号池 → 配置页小白化）。
> 用户决策：跟卖+自建都做；A 接线先行、B 自建补齐跟进；dry-run 作安全；默认模拟。

## 1. 背景与现状（已核对代码）

- **异步发布链路已是配置驱动**：`app/workers/publisher.py` 的 `run_publish`、`run_publish_tick`（arq 任务/定时）已读 `system.ozon_seller_provider`（mock|real），用 `get_ozon_seller(name)`，从 `draft.shop_id` 读店铺 `client_id` + 解密 `api_key`，按 `draft.mode`（follow/create）分派 `create_follow_offer` / `create_product`，并用 `get_product_status` 轮询 `import/info`。
- **仅两个同步便捷接口写死 mock**：`app/api/listing.py:77`（`POST /listing/publish`）与 `app/api/publish.py:35`（`POST /publish/tick`）调用 `get_ozon_seller("mock")`。前端"上架/推进"走这两个，故当前只 mock 成功。
- **`RealOzonSeller`（`app/services/ozon_seller/real.py`）已实现**：跟卖 `POST /v1/product/import-by-sku`、自建 `POST /v3/product/import`、状态 `POST /v1/product/import/info`；`Client-Id`+`Api-Key` 头；`_fmt_price`；`_to_ozon_attributes`。
- **自建缺字段（`create_product` 内注释已标注）**：v3 真实 import 还需 `type_id`（description-category 下的类型）、尺寸（长/宽/高 + 单位）、重量（+ 单位）、属性字典值 `dictionary_value_id`；`listing_drafts` 当前无这些字段，真实提交会被 Ozon 拒。
- **草稿现有字段**（`app/models/listing_draft.py`）：mode、target_ozon_sku、barcode、title、description、category_id、attributes({attr_id:value})、images、price、currency、stock_qty、shop_id 等。
- **店铺**（`app/models/shop.py`）：client_id（明文）、api_key_encrypted（Fernet）、is_active、is_sandbox（默认 true）。
- **系统设置页**（`web/src/pages/settings/SystemSettings.tsx`）已有 `ozon_seller_provider`、`category_tree_provider` 两字段，写入 `system` category。

## 2. 目标与范围

**目标**：让真实自动上品可端到端工作——跟卖（A 阶段）先真发，自建（B 阶段）补齐必填字段后真发；全程默认安全（默认 mock + dry-run + 明确开关）。

**范围**
- A. 同步接口接线为配置驱动；上品模式开关（模拟/真实）；dry-run 安全模式；跟卖端到端真发。
- B. 接 Ozon 卖家端类目/类型/属性 API；扩草稿字段（type_id/尺寸/重量/属性字典值）；上架审核页补充信息表单；`create_product` 带全字段发送。

**不做（YAGNI）**：拼多多/1688（子项目②③）；Ozon 独立沙箱域名（Ozon 无公开沙箱，用 dry-run 替代）；批量类目属性的自动 AI 填充（B 阶段仅提供表单 + 已有类目建议）。

## 3. A 阶段：接线 + 开关 + dry-run 安全

### 3.1 同步接口接线
- 新增 helper `app/services/ozon_seller/resolve.py`：`async def resolve_seller(session) -> OzonSellerProvider`，读 `get_category(s,"system").get("ozon_seller_provider") or settings.ozon_seller_provider`，返回 `get_ozon_seller(name)`。**arq 的 `run_publish`/`run_publish_tick` 与两个同步接口统一改用此 helper**（消除重复的三行读取，DRY）。
- 改 `app/api/listing.py:77`、`app/api/publish.py:35`：`seller=await resolve_seller(s)`（替换 `get_ozon_seller("mock")`）。

### 3.2 上品模式开关（前端）
- SystemSettings 页把 `ozon_seller_provider` 从裸文本框改为 **Select**：`模拟(mock)` / `真实(real)`，默认 `模拟`，附一句说明「真实模式将调用 Ozon Seller API 真正上品」。（此项在子项目③统一小白化时会再润色，本阶段先可用。）

### 3.3 dry-run 安全模式
- 新增 `system` 配置项 `ozon_publish_dry_run`（`"true"`/`"false"`，默认 `"true"`）。
- `RealOzonSeller.__init__` 增参 `dry_run: bool = False`。为真时：`create_follow_offer`/`create_product` **构造出真实请求体后不 POST**，返回 `PublishResult(ok=True, ozon_product_id="DRYRUN", status="pending_review", raw={"dry_run": <请求体>}, error=None)`；`get_product_status` dry-run 时直接返回 `"approved"`（便于流程演练）。
- `resolve_seller` 读 `ozon_publish_dry_run`，real 时以 `dry_run` 构造 `RealOzonSeller(dry_run=...)`。
- SystemSettings 页加开关「试运行（dry-run）：只构造请求不真正提交」，默认开。
- 结果：real + dry-run → 走真实代码路径与真实请求体，但不产生真实上品；关掉 dry-run 才真发。

### 3.4 A 阶段验收
- provider=mock：行为与现在完全一致（回归）。
- provider=real + dry-run=true：`/listing/publish` 对一条 follow 草稿返回 `raw.dry_run` 含正确 Ozon 请求体（sku/offer_id/price/currency），未发生网络 POST。
- provider=real + dry-run=false（用真实或测试店铺）：跟卖草稿真实 `import-by-sku` 得 task_id → `pending_review`；`/publish/tick` 轮询 `import/info` 映射审核状态。

## 4. B 阶段：自建补齐

### 4.1 Ozon 卖家端类目/类型/属性 provider
- 新增 `app/services/ozon_seller/catalog.py`（真实，走 `api-seller.ozon.ru`，复用 Client-Id/Api-Key）：
  - `get_description_category_tree(client_id, api_key)` → `POST /v1/description-category/tree`（返回 category → type 层级，含 `type_id`）。
  - `get_category_attributes(client_id, api_key, category_id, type_id)` → `POST /v1/description-category/attribute`（必填/选填属性列表，是否 `dictionary`）。
  - `get_attribute_values(client_id, api_key, category_id, type_id, attribute_id)` → `POST /v1/description-category/attribute/values`（字典可选值 → `dictionary_value_id`）。
  - dry-run/mock 分支：无凭证或 mock 时返回内置样例，保证前端可开发/演示。
- 新增 API `app/api/ozon_catalog.py`（admin/operator）：`GET /ozon-catalog/types?category_id=`、`GET /ozon-catalog/attributes?category_id=&type_id=`、`GET /ozon-catalog/attribute-values?...` 透传上述服务（供上架审核页表单用）。

### 4.2 草稿字段扩展（Alembic 迁移）
`listing_drafts` 增列（均 nullable）：
- `type_id INTEGER`
- `weight INTEGER`（克）、`dimension_unit STRING(8)`（默认 `mm`）、`weight_unit STRING(8)`（默认 `g`）
- `depth INTEGER`、`width INTEGER`、`height INTEGER`（尺寸，单位 `dimension_unit`）
- `attributes` 复用现有 JSONB，但值结构升级为 `{attr_id: {"value": str} | {"dictionary_value_id": int}}`（兼容旧的纯 value）。

### 4.3 上架审核页「自建补充信息」表单
- `web/src/pages/ListingReview.tsx`：当 `draft.mode==="create"` 时，展开补充表单：
  - 类型 Select（按 category_id 拉 `/ozon-catalog/types`）。
  - 尺寸（长/宽/高）+ 重量，单位下拉。
  - 必填属性：按 `/ozon-catalog/attributes` 渲染；字典属性用 Select 拉 `/attribute-values`，自由属性用输入框。
  - 保存 → `POST /listing/{draft_id}/confirm-create-fields`（新端点，写回草稿新字段）。
- 缺必填字段时 `confirm_draft`/发布前校验拒绝并提示（现有 `confirm_draft` 已对 create 校验 category_id/images，扩展为同时校验 type_id + 尺寸 + 必填属性）。

### 4.4 create_product 带全字段
- `RealOzonSeller.create_product` 增参 `type_id, depth, width, height, weight, dimension_unit, weight_unit`；item 增：
  `description_category_id`、`type_id`、`depth/width/height`、`dimension_unit`、`weight`、`weight_unit`、`attributes`（含 dictionary_value_id）。
- `_call_seller`（`publisher.py`）把草稿新字段透传。

### 4.5 B 阶段验收
- create 草稿补齐 type_id/尺寸/重量/必填属性后，dry-run 请求体符合 v3 import 结构；真实店铺提交被 Ozon 接受（返回 task_id）。
- 缺任一必填 → 发布前明确报错，不发。

## 5. 测试计划

- **A**：`resolve_seller` 单测（mock/real/dry-run 分支）；`RealOzonSeller(dry_run=True)` 用 `httpx.MockTransport` 断言"未发起 POST"且返回体含请求体；两个同步接口集成测试（mock 回归 + real+dry-run）；真实 POST 用 `@pytest.mark.live` 默认跳过。
- **B**：catalog provider 请求结构测试（MockTransport 断言 URL/body）；草稿迁移与新字段读写；`create_product` 全字段请求体断言；`confirm_draft` 必填校验；`@live` 真发。
- 前端：SystemSettings 开关渲染/保存；ListingReview create 补充表单渲染 + 保存调 API（Vitest + mock）。
- 后端 0 warnings；前端 build。

## 6. 风险与降级

| 风险 | 应对 |
|---|---|
| 真实误发错货 | 默认 provider=mock + 默认 dry-run=true + 前端明确"真实"标识；三重保护 |
| 自建缺字段被 Ozon 拒 | B 阶段补齐；补齐前对 create 草稿发布前硬校验并提示缺哪项 |
| Ozon 无独立沙箱域名 | 用 dry-run（构造真实请求不提交）替代沙箱 |
| 凭证过期/风控 | 现有错误返回与状态映射；失败单条隔离不影响其他草稿 |
| 卖家类目 API 与买家 composer 树不同 | B 阶段单独接 description-category 系列，不复用 composer 树 |
| 属性值结构升级破坏旧草稿 | 新结构兼容旧纯 value（读取时归一化）|

## 7. 交付顺序
1. A 阶段（接线 + 开关 + dry-run + 跟卖真发）——先交付，最快见效。
2. B 阶段（catalog provider + 草稿字段 + 补充表单 + create 全字段）——跟进。

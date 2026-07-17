# 设计文档：M4 — 跟卖定价 + 跟卖上架分支 + 上架草稿确认

> Ozon 跟卖/铺货自动化系统 v3.0，第四个里程碑。建立在已合入 main 的 M1(采集/筛选)+M2(货源匹配)+M3(评分/审核)之上。
> 版本：v1 ｜ 日期：2026-07-17 ｜ 依据：`开发文档v3-*.md` §5.8/§5.9/§5.10、里程碑表 M4、M3 代码。

## 1. 目标与范围

**M4 交付** = 跟卖定价(自定义公式) + 生成跟卖草稿 + 草稿确认闸门 + 跟卖挂靠上架(follow 分支)。验收「跟卖草稿→测试店成功挂靠」。
管线：…→审核采用(M3) → **定价+生成草稿 → 人工确认 → 挂靠上架(M4)**。

**四个已确认决策：**
- **Mock-first**：mock `OzonSellerProvider` 跑通 定价→草稿→确认→挂靠 整条链路可测；真实 `RealOzonSeller`(同接口, live 默认跳过)后置，Ozon "跟卖"端点细节联调时定。
- **simpleeval** 作自定义公式安全求值引擎(变量白名单, 禁任意代码)。
- **完整前端**：ListingReview(草稿确认/挂靠) + 定价设置 + 店铺管理。
- **settings/pricing 集中配**：汇率/佣金率/履约费率/目标毛利率/最低价/公式存 `app_settings.pricing`。

**范围外(后续里程碑)**：上架节奏调度(随机间隔/时段/日限/等审核/PublishMonitor 完整版) = M5；自建改图+类目映射 = M6；公网部署 = M7。**M4 上架是"确认后直接挂靠",无节奏。**

## 2. 架构与新增文件

沿用 mock-first + 配置驱动 provider 模式，新增定价引擎 + Ozon 写入抽象(第一次写 Ozon) + 草稿/店铺。

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
web/src/pages/{ListingReview.tsx, Shops.tsx}
web/src/api/{listing.ts, shops.ts}
```

要点：
- **定价**(§5.8)：内置毛利率反推 + simpleeval 自定义公式 + 最低价保护；参数存 `app_settings.pricing`，对齐 Ozon 计算器口径。
- **跟卖挂靠**(§5.9 follow)：listing_builder 由已采用候选+定价生成草稿；publisher 调 `ozon_seller.create_follow_offer` 以条码/SKU 关联目标商品卡；mock-first。
- **店铺凭据**：`shops` 表存 Ozon Client-Id/Api-Key(Fernet 加密)。
- **M4 直接挂靠、无节奏**(节奏 M5)。

## 3. 数据库 Schema(migration 0004)

### 3.1 `shops` 新表
```
id, name, platform('ozon' 默认),
client_id(varchar, Ozon Client-Id 明文), api_key_encrypted(bytea, Fernet),
is_active(bool 默认 true, NOT NULL), is_sandbox(bool 默认 true, NOT NULL),
created_at, updated_at
```

### 3.2 `listing_drafts` 新表
```
id, task_id(fk collect_tasks), ozon_product_id(fk ozon_products, 跟卖目标卡),
candidate_id(fk supply_candidates, 已采用货源), shop_id(fk shops, null 可),
mode('follow'|'create' 默认 follow), target_ozon_sku(varchar), barcode(varchar null),
price(numeric null, RUB), currency(varchar 默认 'RUB'), stock_qty(int 默认 0, NOT NULL),
cost(numeric null, 到手成本), margin(numeric null, 毛利率), pricing_detail(jsonb),
scheduled_at(timestamptz null, M5), status('draft' 默认, NOT NULL),
ozon_result(jsonb null), error(text null), created_at, updated_at
```
- 唯一约束 `(task_id, candidate_id)`；索引 `(task_id, status)`、`(shop_id)`
- status ∈ draft | confirmed | publishing | published | failed | below_min

### 3.3 `ozon_products` 增列
```
ADD barcode varchar null   # 跟卖按条码关联; 缺失时挂靠用 target_ozon_sku 兜底
```

### 3.4 定价参数(不建表)
`app_settings.pricing`：`mode`(builtin|formula)、`formula`、`commission_rate`、`fulfillment_rate`、`fx`(CNY→RUB)、`target_margin`、`logistics`、`min_price`(RUB)、`strike_coeff`。缺省用 `DEFAULT_PRICING`。

## 4. 模块规格

### 4.1 定价引擎(`services/pricing.py`)
```python
DEFAULT_PRICING = {"mode":"builtin","commission_rate":0.15,"fulfillment_rate":0.10,
                   "fx":13.0,"target_margin":0.20,"logistics":5.0,"min_price":0.0,
                   "strike_coeff":1.3,"formula":""}

@dataclass
class PriceResult:
    price: float; cost: float; margin: float; strike: float | None; blocked: bool; detail: dict

def price_candidate(cost_cny: float, weight: float | None, params: dict) -> PriceResult
```
- **builtin**：`到手成本=cost+logistics`；`denom=1-target_margin-commission_rate-fulfillment_rate`(守卫 denom>0 否则 blocked)；`售价=到手成本/denom×fx`；`划线价=售价×strike_coeff`。
- **formula**：`SimpleEval(names={cost,logistics,commission_rate,fulfillment_rate,fx,weight,target_margin,min_price}).eval(formula)`→售价；异常安全兜底。
- **最低价保护**：售价<min_price → blocked=True。参数从 app_settings.pricing 读，缺省 DEFAULT_PRICING。

### 4.2 Ozon 写入抽象(`services/ozon_seller/`)
```python
@dataclass
class PublishResult:
    ok: bool; ozon_product_id: str | None; status: str; raw: dict; error: str | None = None

class OzonSellerProvider(Protocol):
    async def create_follow_offer(self, *, client_id, api_key, target_sku, barcode,
                                  price, stock, offer_id) -> PublishResult: ...
```
- `MockOzonSeller`：确定性 `ok=True, ozon_product_id="OZ-"+offer_id, status="published"`。
- `RealOzonSeller`：以条码/SKU 调 Ozon Seller API 创建 offer 关联目标商品卡(复用原图文)；请求层与解析层分离；live 默认跳过。
- `factory.get_ozon_seller(name)` 默认 mock。

### 4.3 草稿生成(`services/listing_builder.py`)
- `build_follow_drafts(session, task_id, *, params, shop_id=None) -> dict`：对 status∈{adopted,auto_adopted} 且无草稿的候选，`price_candidate(candidate.price, ozon.weight, params)`→建 listing_drafts(mode=follow, target_ozon_sku=ozon.sku, barcode=ozon.barcode, price/cost/margin/pricing_detail, stock 默认, shop_id, status=below_min if blocked else draft)。按 (task_id,candidate_id) 幂等。返回 `{built, blocked}`。

### 4.4 上架(`workers/publisher.py`, follow 分支)
- `apply_auto_confirm(session, task_id)`：读 task.review_config；`listing_review_required=false` 时 status='draft' 且(listing_score_min 空或候选总分≥min)的草稿→status='confirmed'。
- `run_publish_core(session_factory, task_id, *, seller, max_drafts=None, progress_cb=None) -> dict`：对 status='confirmed' 草稿取 shop_id 凭据(Fernet 解密), `seller.create_follow_offer(...)`→回写 ozon_result+status(published/failed)+error；M4 直接挂靠无节奏；失败重试一次；断点/失败同范式。返回 `{published, failed}`。
- `run_publish(ctx, task_id)`：ARQ 入口, 配置选中 seller(默认 mock)。
- `confirm_draft(session, draft_id)`：draft→confirmed(人工闸门)。

## 5. API
```
POST/GET/PUT/DELETE /shops                # 店铺凭据 CRUD(admin, api_key 加密/脱敏)
GET/PUT /settings/pricing                 # 定价参数(admin)
POST /listing/build?task_id=&shop_id=     # 生成跟卖草稿(operator+)
GET  /listing/drafts?task_id=&status=     # 草稿列表(进价/售价/毛利率/目标卡/状态)
POST /listing/{draft_id}/confirm          # 单条确认闸门(reviewer+)
POST /listing/auto-confirm?task_id=       # 按 review_config 自动确认(operator+)
POST /listing/publish?task_id=&sync=false # 挂靠上架(publisher+; sync=true 用 mock seller 落测试库)
GET  /listing/monitor?task_id=            # 草稿各状态计数(简版; 完整 PublishMonitor 留 M5)
```
角色：build→operator+；confirm→reviewer+；publish→publisher+(admin 超级通过)。

## 6. 前端
- **ListingReview**：选任务+选店铺→生成草稿→草稿表(目标卡 SKU/标题、平台、进价/售价/毛利率、tier、状态；低于最低价标红)→单条/批量确认→挂靠上架→回写 Ozon 商品ID。
- **定价设置页**：mode(内置/公式)+佣金率/履约费率/汇率/目标毛利率/物流/最低价/划线系数；公式模式显示编辑器→存 /settings/pricing。
- **店铺管理页**：店铺列表+新增(name/client_id/api_key/沙箱)+删除；api_key 脱敏。
- `api/listing.ts` `api/shops.ts`；加路由+菜单。

## 7. 测试策略(TDD, mock-first)
- 定价单测(核心)：内置公式已知输入→已知售价/毛利率；公式模式(simpleeval 白名单)；最低价拦截；denom≤0 守卫。
- ozon_seller 单测：MockOzonSeller 返回 ok+Ozon商品ID；RealOzonSeller live 默认跳过。
- listing_builder 单测：已采用候选→草稿(带定价)、幂等、below_min、跳过未采用。
- publisher 单测：apply_auto_confirm(listing_review_required=false→confirmed)；run_publish_core(confirmed→published+回写 ozon_result, mock seller)；店铺凭据解密。
- API 集成测：采集→…→采用→build→drafts→confirm→publish(mock) 全链路；shops CRUD(api_key 不泄漏)；settings/pricing。
- 前端：ListingReview/Shops 渲染(Vitest+mock api)。
- pytest 0 warnings；测试全走 mock。

## 8. M4 验收标准(「跟卖草稿→测试店成功挂靠」)
1. 迁移 0004：shops、listing_drafts、ozon_products.barcode。
2. 建店铺(凭据加密/脱敏)；配定价参数。
3. 采集→匹配→评分→采用→/listing/build→草稿有进价/售价/毛利率；最低价拦截。
4. 草稿确认(人工闸门+review_config 自动确认)；/listing/publish(mock)→草稿 published+回写 Ozon 商品ID。
5. 前端 ListingReview(草稿确认/挂靠)+定价设置+店铺管理。
6. MockOzonSeller 全链路；RealOzonSeller 配置切换、live 默认跳过。
7. 非 live 测试全绿 0 warnings + README/docs + 前端 build。

## 9. 风险与降级
| 风险 | 应对 |
|---|---|
| Ozon "跟卖"写入 API 细节/审核 | mock-first 保证链路先通；RealOzonSeller 请求层版本化封装；live 默认跳过, 沙箱店先试 |
| 自定义公式写错致错价 | simpleeval 白名单+禁代码；最低价保护；denom≤0 守卫；挂靠前人工确认闸门 |
| 汇率/费率过期致错价 | 参数集中 app_settings.pricing 可维护；对齐 Ozon 计算器核对 |
| 目标卡条码缺失 | 采集补 barcode；缺失用 target_ozon_sku 兜底；真实挂靠联调时校正 |
| 店铺密钥泄漏 | Fernet 加密；响应脱敏；仅 admin 可管 |
| 挂靠中断 | 草稿 status 幂等；失败重试+回写 error |

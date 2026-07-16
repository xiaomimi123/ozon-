# 设计文档：项目骨架 + M1（采集 → 筛选 → 商品列表 → 任务选模式）

> 面向 Ozon 跟卖/铺货自动化系统 v3.0。本 spec 覆盖「整体骨架」与首个里程碑 **M1**。
> 后续里程碑（M2–M7）各自另立 spec → plan → 实现。
> 版本：v1 ｜ 日期：2026-07-17 ｜ 依据：`开发文档v3-Ozon跟卖铺货自动化系统.md`、`产品说明书v3`

## 1. 目标与范围

**本次交付 = 可运行的地基 + M1 垂直切片。**

M1 验收（文档里程碑表）：「采到商品、可筛、可选模式」。

**构建策略：Mock-first 垂直切片**——先用 `OzonMockProvider`（造好的假商品数据）把「采集→筛选→商品列表→任务选模式」整条链路端到端跑通、可测试、界面立刻可运行；再在**同一 `OzonMarketProvider` 接口**背后实现真实 `OzonComposerProvider`（composer-api 三入口），上层代码对 mock/真实无感。此策略贴合文档 §5.1「M1 三步走降风险」。

**范围内（M1）：** Docker 一键启动、JWT + 角色鉴权、加密配置中心机制、采集 Provider 抽象（mock + composer + apify 占位）、采集 worker（限速/断点续传/变体归集/去重）、六维筛选、任务中心（选跟卖/自建）、商品列表、WS 进度、README + docs。

**范围外（后续里程碑）：** 货源匹配 1688/拼多多（M2）、五维评分与审核台（M3）、跟卖定价与上架（M4）、上架节奏调度（M5）、自建改图与类目映射（M6）、公网部署 Nginx+HTTPS（M7）。

## 2. 整体架构与骨架

代码库结构（遵循开发文档 §3，M1 只落地会用到的部分，其余占位）：

```
ozon-listing-auto/
├── docker-compose.yml          # postgres(pgvector) + redis + api + worker + web(dev)
├── .env.example
├── README.md
├── server/
│   ├── pyproject.toml           # Python 3.11, FastAPI, SQLAlchemy(async), Alembic, ARQ, structlog, httpx
│   ├── alembic/                 # 数据库迁移
│   └── app/
│       ├── main.py              # FastAPI 入口：REST + WS + CORS
│       ├── core/
│       │   ├── config.py        # pydantic-settings
│       │   ├── db.py            # async SQLAlchemy engine/session
│       │   ├── redis.py         # ARQ / Redis 连接
│       │   ├── security.py      # JWT、密码哈希、角色依赖
│       │   ├── crypto.py        # Fernet 加密
│       │   └── logging.py       # structlog，全链路 task_id
│       ├── models/              # SQLAlchemy ORM
│       ├── schemas/             # Pydantic 请求/响应
│       ├── api/                 # auth / tasks / products / collect / settings / ws
│       ├── services/
│       │   ├── ozon_market/
│       │   │   ├── base.py      # OzonMarketProvider 接口 + OzonProductDTO
│       │   │   ├── mock.py      # OzonMockProvider
│       │   │   ├── composer.py  # OzonComposerProvider（真实 composer-api）
│       │   │   ├── apify.py     # OzonApifyProvider（占位）
│       │   │   ├── parser.py    # widget→DTO 解析层（与请求层分离）
│       │   │   └── factory.py   # get_provider(name)
│       │   ├── ozon_api.py      # 自有店官方 API（own_shop 读，占位可扩展）
│       │   └── filtering.py     # 筛选引擎
│       └── workers/
│           └── collector.py     # 采集 worker（ARQ）
└── web/                          # React + TS + Vite + Ant Design
    ├── package.json
    └── src/{api,pages,components,store}/
        └── pages/                # Login / Tasks / Filters / ProductList
```

技术要点：
- **后端全异步**：FastAPI + async SQLAlchemy + asyncpg；worker 用 ARQ（Redis）。
- **鉴权**：JWT + 角色 `admin/operator/reviewer/publisher`，依赖注入做角色校验。
- **配置/密钥**：普通配置走环境变量（pydantic-settings）；第三方密钥走 `app_settings` 表 + **Fernet 加密**，不硬编码。M1 建好加密存取机制，具体密钥后续里程碑填。
- **日志**：structlog 结构化，采集任务全程带 `task_id`。
- **一键启动**：`docker compose up`；开发时也可后端 `uvicorn` + 前端 `npm run dev` 分开跑（本机环境与线上一致）。
- **文档**：骨架建好后写 README（技术栈/快速开始/环境变量/目录结构）。

## 3. 数据库 Schema（重建后的 v3）

因无 v2 文档，基表从上下文完整重建，v3 增量直接合并进最终建表语句。**M1 迁移只创建 M1 读写的表**，其余表在各自里程碑迁移中创建。

### 3.1 M1 创建并使用的表

**`users`**
`id, username(uniq), password_hash, role('admin'|'operator'|'reviewer'|'publisher'), is_active, created_at`

**`collect_tasks`**
`id, name, listing_mode('follow'|'create' 默认follow), entry_type('keyword'|'category'|'seller'|'own_shop'), entry_value(text), provider('mock'|'composer'|'apify' 默认mock), source_platforms(jsonb 默认["ali1688","pinduoduo"]), review_config(jsonb), last_filter(jsonb 记住上次筛选), status('pending'|'running'|'paused'|'done'|'failed'), cursor(jsonb 断点续传游标), stats(jsonb 采集/去重计数), created_by(fk users), created_at, updated_at`

`review_config` 结构：`{source_review_required:bool, source_score_min:num|null, listing_review_required:bool, listing_score_min:num|null}`（M1 仅存储，消费在 M3/M4）。

**`ozon_products`**
`id, task_id(fk), sku, product_url, title, price, currency, sales_monthly, rating, reviews_count, weight, listed_at, follow_count, return_rate, main_image_url, images(jsonb), attributes(jsonb), parent_sku, phash, raw(jsonb), collected_at`
唯一约束 `(task_id, sku)`；索引 `(task_id, parent_sku)`、`phash`。

**`app_settings`**
`id, category, key, value_encrypted(bytea), is_secret(bool), updated_by, updated_at`，唯一 `(category, key)`。`category ∈ {ozon_shop, llm, imagegen, source, pricing, publish_pace, review_config, ...}`。

### 3.2 迁移里同时做（铺路，不建空表）
`CREATE EXTENSION IF NOT EXISTS vector`（pgvector，图匹配 M2 用）、`CREATE EXTENSION IF NOT EXISTS pg_trgm`（标题模糊筛）。

### 3.3 后续里程碑的表（蓝图，不在 M1 迁移中创建）
`supply_candidates`(+platform, M2) · `source_accounts`(原 ali_accounts+platform, M2) · `review_decisions`(M3) · `listing_drafts`(+mode/target_ozon_sku/barcode/scheduled_at/stock_qty, M4) · `publish_pace`(M5) · `category_map`(M6)。

## 4. M1 功能切片

### 4.1 采集 Provider 抽象

`services/ozon_market/base.py`：

```python
@dataclass
class OzonProductDTO:   # 解析层产物，字段对齐 ozon_products
    sku: str
    title: str
    price: float | None
    currency: str | None
    sales_monthly: int | None
    rating: float | None
    reviews_count: int | None
    weight: float | None
    listed_at: datetime | None
    follow_count: int | None
    return_rate: float | None
    main_image_url: str | None
    images: list[str]
    attributes: dict
    parent_sku: str | None
    product_url: str | None
    raw: dict

class OzonMarketProvider(Protocol):
    name: str
    async def search_by_keyword(self, kw: str, page: int) -> list[OzonProductDTO]: ...
    async def list_by_category(self, category_url: str, page: int) -> list[OzonProductDTO]: ...
    async def list_by_seller(self, seller_id: str, page: int) -> list[OzonProductDTO]: ...
```

实现：
- **`OzonMockProvider`**：从 `fixtures/` 读造好的商品 JSON，支持分页，样本含变体（同 parent_sku）与重复（同 sku / 相近 phash），让归集/去重/筛选逻辑都被真实触发。
- **`OzonComposerProvider`**：请求层 `httpx.AsyncClient` 打 `api.ozon.ru/composer-api.bx/page/json/v2`（三入口仅 URL 不同）；解析层 `parser.py`（widget→DTO，端点变了只改 parser）。防反爬：随机 UA、间隔随机抖动、代理池、429/403 指数退避、可选 cookie 会话。**请求层与解析层严格分离。**
- **`OzonApifyProvider`**：占位（`NotImplementedError` + TODO）。

`factory.get_provider(name)` 按 `collect_tasks.provider` 实例化。

### 4.2 采集 worker（`workers/collector.py`）

ARQ 任务 `run_collect(task_id)`：
1. 读 task → `get_provider(task.provider)`，按 `entry_type` 选调 keyword/category/seller。
2. 逐页拉取 → 解析 DTO 列表 → **变体归集**（按 parent_sku 归并）+ **去重**（`(task_id, sku)` 唯一 + phash 聚类）→ upsert `ozon_products`。
3. **断点续传**：每页后写 `cursor`；可 `paused`，续跑从 cursor 起（幂等）。
4. **限速**：请求间隔随机抖动（mock 下可设 0 加速测试）。
5. 进度经 **WS `/ws/progress`** 广播（task_id、已采集/去重计数、当前页、状态）+ 写 `stats`。
6. 失败：单页重试 + 指数退避；连续失败标 `failed` 并 structlog 留痕（带 task_id）。

### 4.3 筛选（`services/filtering.py`）

对 `ozon_products` 的查询时过滤，条件均可空（空即不限）：`月销量 / 退货率 / 评分 / 重量 / 上架时间 / 跟卖数量` 区间 + 标题关键词（pg_trgm）。构造动态 where。"可改重筛"= 换参数重查。

### 4.4 API 端点（M1）

```
POST /auth/login                      # 返回 JWT
GET  /auth/me
POST /tasks                           # name, listing_mode, entry_type, entry_value, provider, source_platforms, review_config
GET  /tasks   GET /tasks/{id}
POST /collect/start?task_id=          # 入队 run_collect（operator+）
POST /collect/pause?task_id=          # 断点暂停
GET  /products?task_id=&<筛选参数...> # 分页 + 筛选
GET/PUT /settings/{category}          # 加密配置读写（admin）
WS   /ws/progress                     # 采集进度推送
```

角色：建任务/启动采集需 `operator`+；设置需 `admin`。

### 4.5 Web 前端页面（React+TS+Vite+AntD）

- **Login**：账号登录，存 JWT，路由守卫。
- **任务中心 Tasks**：建任务表单（选跟卖/自建、entry_type + entry_value、选 provider、货源平台占位、review_config 开关+阈值）、任务列表、启动/暂停、实时进度（订阅 WS）。
- **筛选 Filters**：六维筛选表单（可空）+ 应用/重置。
- **商品列表 ProductList**：表格（图/标题/价/月销/评分/跟卖数/…），受筛选驱动，分页。

界面响应式（桌面/平板），AntD Layout。

## 5. 测试策略

后端（pytest + pytest-asyncio）：
- **解析层单测**：喂 composer-api 样本 JSON（`fixtures/`），断言 `parser.py` 抽字段正确（含缺字段/异常 widget 容错）——爬虫最脆弱处，重点覆盖。
- **变体归集 + 去重单测**：含变体/重复的 mock 数据，断言归并与去重。
- **筛选引擎单测**：边界——空条件、单边区间、多条件叠加、无匹配。
- **采集 worker 单测**：`OzonMockProvider` 跑 `run_collect`，断言写库计数、cursor 断点、暂停/续跑幂等。
- **鉴权单测**：登录发 JWT、角色校验、过期/非法 token。
- **API 集成测**：`httpx.ASGITransport` + 测试库，跑「建任务→启动采集(mock)→筛选查询」链路。

遵循 **TDD**：每单元先写失败测试再实现。

前端：关键交互（登录守卫、建任务提交、筛选刷新）加 Vitest + RTL 轻量测试。

真实爬虫：`OzonComposerProvider` 联调用少量真实请求冒烟，标 `@pytest.mark.live`，默认不跑，CI 只跑 mock。

## 6. M1 验收标准

1. `docker compose up` 一键起 pg + redis + api + worker + web，健康检查通过。
2. 浏览器登录（JWT + 角色）。
3. 建采集任务，可选跟卖/自建、entry_type、provider（mock/composer）。
4. 启动采集（mock）→ `ozon_products` 有数据，**变体归集 + 去重生效**，WS 实时进度，可暂停/续跑。
5. 商品列表展示结果，**六维筛选可用、可改重筛**。
6. `OzonComposerProvider` 真实打通 composer-api 单点冒烟（三步走第 1 步：解析出真实商品 JSON），接口与 mock 一致、上层无感。
7. 所有非 live 测试通过；README + `docs/` 更新。

## 7. 风险与降级

| 风险 | 应对 |
|---|---|
| composer-api 被 Cloudflare/风控拦 | mock-first 保证链路先通；composer 请求层随机 UA/代理池/退避/cookie 会话；必要时降级 Apify（占位接口已留） |
| 端点/页面结构变化 | 请求层与解析层分离，只改 parser；provider 版本化封装 |
| 无 v2 schema 源 | 完整重建并合并进 M1 迁移，作为 v3 权威 schema |
| 采集中断 | cursor 断点续传 + 幂等 upsert |

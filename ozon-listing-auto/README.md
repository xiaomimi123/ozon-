# Ozon 跟卖/铺货自动化系统（M1 + M2 + M3 + M4）

面向 Ozon 平台跟卖/铺货场景的自动化辅助系统。M1 完成骨架搭建：登录鉴权、采集任务管理（跟卖/自建两种模式、mock/composer/apify 三种数据源）、商品入库去重、六维条件筛选浏览、WebSocket 采集进度推送，以及 Docker Compose 一键启动。M2 在此基础上新增货源匹配：账号池、双源（1688/拼多多）候选采集、跨平台 CLIP 去重、匹配/候选管理 API。M3 在匹配候选之上新增五维评分与审核台：图像/标题/属性/价格/供应商五维打分 + tier 分级、LLM 抽象（mock/OpenAI 兼容，用于译标题与抽属性）、人工审核（采用/拒绝）或按阈值自动采用、评分/审核 API + 审核台前端。M4 在已采用候选之上新增跟卖定价与挂靠上架：定价引擎（内置毛利率反推 / simpleeval 自定义公式 + 最低价保护）、Ozon 写入抽象（MockOzonSeller/RealOzonSeller）、草稿生成与人工确认闸门（或按阈值自动确认）、挂靠上架回写 Ozon 商品 ID、店铺凭据管理（Fernet 加密）、上架 API + 前端 ListingReview/Shops 页面。

## 技术栈

- **后端**：FastAPI + SQLAlchemy（async）+ Alembic（数据库迁移）+ ARQ（Redis 后台任务队列）
- **数据库**：PostgreSQL 16（pgvector 扩展）+ Redis 7
- **前端**：React + Vite + TypeScript + Ant Design
- **容器化**：Docker Compose（postgres + redis + api + worker + web/nginx）

## 快速开始

### 方式一：Docker Compose 一键启动（推荐）

```bash
cd ozon-listing-auto
cp .env.example .env   # 按需修改 JWT_SECRET / FERNET_KEY / ADMIN_USER / ADMIN_PASSWORD
docker compose up -d --build
```

首次启动会自动：
1. `api` 容器执行 `alembic upgrade head` 建库；
2. FastAPI 启动钩子幂等地创建首个管理员账号（默认账号 **`admin` / `admin123`**，可通过 `ADMIN_USER` / `ADMIN_PASSWORD` 覆盖）。

服务地址：
- 前端：http://localhost:8080
- 后端 API：http://localhost:8000（健康检查 `GET /health`）
- Postgres：localhost:5432（用户/库均为 `ozon`）
- Redis：localhost:6379

停止服务：`docker compose down`（加 `-v` 一并删除数据库数据卷）。

> `.env.example` 中的 `FERNET_KEY` 一行给出的是一个可直接使用的开发默认值，生产环境务必用下方命令重新生成一个真实的 Fernet key 后再写入 `.env`，否则后端会因无法解析 Fernet key 而启动失败。

> 默认 `docker compose up` 走 `EMBEDDER=mock` + `INSTALL_ML=false`：worker 镜像不装 torch/cn_clip，体积小、构建快，货源匹配（M2）全链路可直接跑通（mock embedder）。需要真实 CLIP 跨平台去重时见下方「M2 货源匹配」章节及 [`docs/M2-货源匹配说明.md`](docs/M2-货源匹配说明.md)。

### 方式二：本机开发（不使用 Docker）

后端（需要本地 Postgres + Redis，或用 `docker compose up db redis` 只启动依赖）：

```bash
cd server
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --reload
```

前端：

```bash
cd web
npm install
npm run dev      # 本地开发，代理 /api、/ws 到 http://localhost:8000
npm run build    # 生产构建
```

## 环境变量

| 变量 | 说明 | 默认值 |
| --- | --- | --- |
| `DATABASE_URL` | 后端数据库连接串（compose 中已固定指向 `db` 服务） | `postgresql+asyncpg://ozon:ozon@localhost:5432/ozon` |
| `REDIS_URL` | Redis 连接串（compose 中已固定指向 `redis` 服务） | `redis://localhost:6379/0` |
| `JWT_SECRET` | JWT 签名密钥，生产环境务必修改 | `dev-secret-change-me` |
| `FERNET_KEY` | 对称加密密钥（用于加密存储配置中心的第三方凭据，如 cookie/代理/API key；以及 M4 店铺表 `shops.api_key_encrypted`） | 开发默认值，生产务必替换 |
| `ADMIN_USER` | 启动种子创建的首个管理员用户名 | `admin` |
| `ADMIN_PASSWORD` | 启动种子创建的首个管理员密码 | `admin123` |
| `EMBEDDER` | 货源匹配用的图像 embedder：`mock`（无需 torch）或 `clip`（真实 `ChineseClipEmbedder`） | `mock` |
| `INSTALL_ML` | worker 镜像构建参数，是否安装 `[ml]`（torch/cn_clip，体积达数 GB）；仅 `EMBEDDER=clip` 时需要设为 `true` | `false` |
| `LLM_PROVIDER` | 五维评分用的 LLM 服务：`mock`（确定性桩，无需 key）或 `openai`（OpenAI 兼容 Chat Completions） | `mock` |
| `LLM_BASE_URL` | `LLM_PROVIDER=openai` 时的接口地址 | `https://dashscope.aliyuncs.com/compatible-mode/v1`（通义千问 DashScope） |
| `LLM_API_KEY` | `LLM_PROVIDER=openai` 时的 API key | 空 |
| `LLM_MODEL` | `LLM_PROVIDER=openai` 时使用的模型名 | `qwen-plus` |

生成生产用 `FERNET_KEY`：

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## 目录结构

```
ozon-listing-auto/
├── docker-compose.yml   # postgres(pgvector) + redis + api + worker + web 一键启动
├── .env.example
├── server/               # FastAPI 后端
│   ├── app/
│   │   ├── api/          # 路由（auth/tasks/collect/products/settings/ws/accounts/match/candidates/
│   │   │                 #   score/review/shops/listing）
│   │   ├── core/         # 配置、数据库、鉴权、加密等基础设施
│   │   ├── models/       # SQLAlchemy ORM 模型（含 source_account/supply_candidate/review_decision/
│   │   │                 #   shop/listing_draft）
│   │   ├── services/     # 业务逻辑：六维筛选、入库去重、ozon_market 采集 provider、
│   │   │                 #   sources/（1688/拼多多货源 provider）、embedding/（mock/CLIP）、账号池、候选去重入库、
│   │   │                 #   scoring.py（五维评分引擎+tier）、review.py（审核队列/采用拒绝/自动采用/并发锁）、
│   │   │                 #   llm/（mock/OpenAI 兼容 LLM 抽象，译标题+抽属性）、
│   │   │                 #   pricing.py（内置反推+simpleeval 自定义公式定价引擎+最低价保护）、
│   │   │                 #   ozon_seller/（Ozon 写入抽象 mock/real）、listing_builder.py（候选+定价→跟卖草稿）
│   │   ├── workers/      # ARQ 后台任务（采集 collector、货源匹配 matcher、评分 scorer、上架 publisher，
│   │   │                 #   均支持断点续传/暂停）
│   │   └── seed.py       # 启动种子：幂等创建首个管理员
│   ├── alembic/          # 数据库迁移
│   └── tests/
├── docs/                 # 里程碑设计文档（如 M2-货源匹配说明.md、M3-评分审核说明.md、M4-定价上架说明.md）
└── web/                  # React + Vite 前端
    ├── src/
    │   ├── api/
    │   ├── pages/         # 登录、任务中心、商品列表、审核台（ReviewBoard）、上架审核（ListingReview）、
    │   │                  #   店铺管理（Shops）等页面
    │   └── store/
    └── nginx.conf         # 生产镜像内 nginx：SPA + /api、/ws 反代
```

## M1 已实现功能

- **鉴权/角色**：用户登录、JWT 鉴权、operator/admin 角色校验（建任务/启动采集需 operator 及以上，配置中心需 admin）
- **配置中心**：按 category 加密存储第三方凭据（cookie/代理等），读取时脱敏返回
- **采集任务**：新建任务（跟卖 `follow` / 自建 `create` 两种 `listing_mode`，`entry_type` 支持关键词/类目/店铺/自有店铺，`provider` 可选 `mock`/`composer`/`apify`）、启动（同步或经 ARQ 入队异步执行）、暂停
- **采集节奏**：跨页去重（sku/图片 phash）、变体归集、游标断点续传、暂停后可续跑、WebSocket 实时进度推送
- **商品列表**：按任务查看已入库商品，支持销量/评分/退货率/重量/上架时间/关注数六维可空条件筛选 + 关键词搜索，可反复调整条件重筛，分页返回
- **采集 provider**：
  - `mock`（默认）：内置 fixtures，无需外部依赖即可跑通完整采集→入库→筛选链路
  - `composer`：接 Ozon composer-api 的真实爬虫实现（随机 UA、请求间隔抖动、429/403 指数退避），实际可用性依赖 cookie/代理配置调优，反爬策略随时间变化
  - `apify`：占位实现，供后续接入 Apify 平台采集

## M2 已实现功能（货源匹配）

- **账号池**（`/accounts`，admin）：1688/拼多多货源账号 CRUD，cookie/会话等凭据用 `FERNET_KEY` 加密存储、响应脱敏（不回传凭据明文）；调用时按日限额 `daily_limit`、最小请求间隔 `min_interval_sec` 限速取号，触发风控自动冷却换号，不中断主流程
- **双源货源匹配**：
  - **1688**：`httpx` + cookie 会话真实图搜/关键词搜索 + 解析器（供货商信用等级/复购率等 `supplier_info`）
  - **拼多多**：一期先落地 JSON 解析层 `parse_pdd_items`（分→元换算、字段映射，已测试），真实图搜/关键词搜索需 `selenium` + 代理截获移动端 API，一期在 `PinduoduoProvider` 中为占位（抛 `NotImplementedError`），留待后续接入
  - 两者均可通过工厂切换 `mock` provider（内置 fixtures，无需任何外部依赖）用于本地/CI 全链路验证
- **跨平台 CLIP 去重**：按 `EMBEDDER` 环境变量切换 embedder——默认 `mock`（SHA256 确定性归一化向量，无需 torch）用于开发/CI；`clip`（真实 `ChineseClipEmbedder`，`cn_clip` ViT-B-16）用于生产，需要 worker 镜像以 `INSTALL_ML=true` 构建安装 `[ml]` 组（torch/cn_clip，体积达数 GB）。同一商品下多平台候选按图像向量贪心聚簇，近似重复折叠为 1 个代表候选、跨平台不同款各自保留，相似度阈值可配
- **匹配控制 API**（`/match`，operator 及以上）：`POST /match/start`（`sync=true` 同步跑完便于本地/mock 演示，`sync=false` 经 ARQ 入队异步执行）、`POST /match/pause`、`GET /match/monitor`（匹配状态 `match_status` + 统计 `match_stats`），支持断点续传（游标记录到已处理商品）
- **候选查询 API**（`/candidates`）：按任务/商品/平台过滤、`only_representative` 只看去重代表、分页返回，字段含 `platform`/`offer_id`/价格/起订量/供应商信息/`is_representative`/去重分组

## M3 已实现功能（五维评分与审核台）

- **五维评分引擎**（`app/services/scoring.py`）：候选商品按 **图像 45% / 标题 20% / 属性 15% / 价格 5% / 供应商 15%** 加权算出总分（权重可通过 `weights` 参数覆盖）：
  - 图像分：Ozon 主图向量与候选图向量的余弦相似度（复用 M2 的 `embedding`/`EMBEDDER` 配置，`mock`/`clip` 通用）
  - 标题分：Ozon 标题经 LLM 译中后与候选标题的相似度
  - 属性分：LLM 从候选标题抽取结构化属性 JSON，与 Ozon 属性做键值命中率
  - 价格分：命中价格区间给满分，否则按有价/无价给基础分
  - 供应商分：综合供应商复购率、信用等级（1688 `supplier_info`）等信号
  - 总分按可配阈值（默认 `tier_auto=85` / `tier_review=70`）分级为 `auto`（免审自动采用）/ `review`（需人工审核）/ `rejected`
- **LLM 抽象**（`app/services/llm/`，`LLMProvider` 协议：`chat`/`translate`/`extract_json`）：
  - `MockLLM`（默认）：确定性桩，`translate` 恒等透传、`extract_json` 返回空，无需 key/网络，用于开发/CI
  - `OpenAICompatLLM`：真实 OpenAI 兼容 Chat Completions 客户端（Bearer 鉴权、失败重试 3 次、容错解析模型返回的 JSON），默认对接**通义千问 DashScope**，也可指向任意 OpenAI 兼容服务；由 `LLM_PROVIDER=openai` + `LLM_BASE_URL`/`LLM_API_KEY`/`LLM_MODEL` 环境变量启用
- **审核台**（`app/services/review.py` + `/review` API + 前端 `ReviewBoard`）：
  - 审核队列 `GET /review/queue`：按任务聚合「一个 Ozon 商品 ↔ 其下多个候选（按总分降序）」，前端左侧展示 Ozon 商品图/标题/价格，右侧逐个展示候选的平台标签、五维分明细、总分与 tier
  - 决策 `POST /review/{candidate_id}`（`decision=adopt|reject`，写 `review_decisions` 留痕）：对同一商品下的多个候选逐一「采用」或「拒绝」，即可实现换选另一候选
  - 任务级 `review_config`（`source_review_required` 是否需要人工审核、`source_score_min` 自动采用分数线）：关闭审核开关后调用 `POST /review/auto-adopt` 按阈值批量自动采用达标候选（同样写 `review_decisions`，`decision=auto_adopt`，`reviewer_id=null` 留痕），前端关闭审核走二次确认弹窗
  - 多人审核并发锁：`review_lock()` 预留了按商品加锁的接口（当前实现为 no-op 上下文管理器），生产环境替换为 Redis 分布式锁即可避免多个审核员对同一商品重复决策
- **评分控制 API**（`/score`，operator 及以上）：`POST /score/start`（`sync=true` 同步跑完，便于本地/mock 演示；`sync=false` 经 ARQ 入队由 `worker` 异步执行 `app.workers.scorer.run_score`）、`POST /score/pause`、`GET /score/monitor`（`score_status` + `score_stats`），支持断点续传（`score_cursor` 记录到已处理的最后一个商品 id）

详细操作流程与真实 LLM 切换步骤见 [`docs/M3-评分审核说明.md`](docs/M3-评分审核说明.md)。

## M4 已实现功能（跟卖定价与挂靠上架）

- **定价引擎**（`app/services/pricing.py`）：对已采用候选按货源到手价（含 `logistics` 运费）计算 Ozon 售价，支持两种模式（任务/全局参数经 `PUT /settings/pricing` 配置，`GET /settings/pricing` 脱敏读取）：
  - `mode=builtin`（默认）：**内置毛利率反推**——`售价 = (到手价 + 运费) / (1 - 目标毛利率 - 平台佣金率 - 履约费率) × 汇率`，参数 `commission_rate`/`fulfillment_rate`/`fx`/`target_margin`/`logistics` 均可配置；分母 ≤ 0（毛利率+佣金+履约费率之和越界）时判定该价格不可用（拦截）。
  - `mode=formula`：**simpleeval 自定义公式**，可用变量 `cost`/`logistics`/`commission_rate`/`fulfillment_rate`/`fx`/`weight`/`target_margin`/`min_price` 做纯算术运算；出于安全考虑禁用函数调用与属性/方法访问（`se.functions = {}` + 剔除 `ast.Attribute` 节点），公式非法或求值异常时安全兜底为拦截，不会抛出到调用方。
  - **最低价保护**：算出的售价 ≤ 0 或低于配置的 `min_price` 时该候选被拦截（草稿状态 `below_min`，不参与后续确认/挂靠）。
  - 划线价 `strike` 按 `strike_coeff`（默认 1.3）系数从售价换算，仅供参考展示。
- **Ozon 写入抽象**（`app/services/ozon_seller/`，`OzonSellerProvider` 协议 `create_follow_offer()`）：
  - `MockOzonSeller`（默认，`get_ozon_seller("mock")`）：确定性返回挂靠成功，`ozon_product_id` 固定为 `OZ-{offer_id}`，供本地/CI 全链路验证，无需任何外部依赖。
  - `RealOzonSeller`（`get_ozon_seller("real")`）：以店铺 `Client-Id`/`Api-Key` 调 Ozon Seller API 创建跟卖 offer 的真实实现；**当前接口地址与请求体是占位实现（`_ENDPOINT` 指向 `product/import`），真实跟卖端点字段需在 live 联调时校正**，且目前后端代码（`POST /listing/publish` 同步路径与 `run_publish` 异步 worker）尚**硬编码使用 `mock`**，暂无环境变量/配置项可一键切到 `real`——要跑通真实挂靠需临时改动 `app/api/listing.py` / `app/workers/publisher.py` 里的 `get_ozon_seller("mock")` 为 `get_ozon_seller("real")`，详见 [`docs/M4-定价上架说明.md`](docs/M4-定价上架说明.md) 第 5 节。
- **草稿生成**（`app/services/listing_builder.py`，`POST /listing/build`）：把某任务下已采用（`adopted`/`auto_adopted`）的候选按定价参数逐个生成 `listing_drafts` 记录（幂等，同一候选不会重复生成），写入进价 `cost`、售价 `price`、毛利率 `margin`、定价明细 `pricing_detail`；被最低价拦截的候选草稿状态为 `below_min`，其余为 `draft`。
- **确认闸门与自动确认**（`app/workers/publisher.py`）：草稿默认需人工 `POST /listing/{id}/confirm` 确认（`draft → confirmed`）才能进入挂靠；若任务 `review_config.listing_review_required=false`，`POST /listing/auto-confirm` 会按可选阈值 `listing_score_min`（对比候选 `score_total`）批量把达标草稿从 `draft` 置为 `confirmed`。
- **挂靠上架**（`POST /listing/publish`）：对该任务下 `confirmed` 状态的草稿逐条调用 `OzonSellerProvider.create_follow_offer()`，成功则草稿状态置为 `published` 并回写 `ozon_result.ozon_product_id`；失败（含店铺凭据解密失败等异常）则置为 `failed` 并记录 `error`，单条失败不影响同批其余草稿。`sync=true` 请求内同步跑完（当前固定用 `mock` seller，便于本地/演示/测试）；`sync=false`（默认）经 ARQ 入队由 `worker` 异步执行 `app.workers.publisher.run_publish`（当前同样固定用 `mock` seller）。
- **店铺凭据管理**（`/shops`，admin，`app/models/shop.py`）：Ozon 店铺 `Client-Id`（明文）+ `Api-Key`（`FERNET_KEY` 加密存储）CRUD，响应统一脱敏（不回传 `api_key` 字段）；草稿关联 `shop_id` 后挂靠时按店铺解密取用凭据。
- **上架 API**（`/listing`，`app/api/listing.py`）：`POST /listing/build`（operator 及以上）、`GET /listing/drafts`（按任务/状态过滤）、`POST /listing/{id}/confirm`（reviewer/admin）、`POST /listing/auto-confirm`（operator 及以上）、`POST /listing/publish`（publisher/admin，`sync` 参数控制同步/入队）、`GET /listing/monitor`（按状态统计草稿数量）。
- **前端**：`ListingReview`（`/listing`）——按任务生成草稿、选店铺、草稿列表展示进价/售价/毛利率/状态/Ozon 回写结果，逐条确认或按开关批量自动确认、一键挂靠；`Shops`（`/shops`）——新增/列表/删除店铺，`Api-Key` 输入框脱敏、列表不回显凭据。

详细操作流程（建店铺→配定价→build→确认→publish→切真实）见 [`docs/M4-定价上架说明.md`](docs/M4-定价上架说明.md)。

## 测试

后端（83 个用例，默认跳过标记为 `live` 的真实网络冒烟测试，覆盖 M1 采集 + M2 货源匹配 + M3 评分审核 + M4 定价上架全链路）：

```bash
cd server && .venv/bin/python -m pytest -q
```

前端：

```bash
cd web && npx vitest run
```

## 采集 provider 说明

- `provider=mock` 走内置样例数据，是本地验证「建任务 → 启动采集 → 商品入库 → 筛选」全流程的默认选择，无需任何外部配置。
- `provider=composer` 会真实请求 `https://api.ozon.ru/composer-api.bx/page/json/v2`，需要在配置中心配置可用的 cookie / 代理才能稳定拿到数据；对应的 live 测试 (`server/tests/test_composer_live.py`) 默认跳过，需显式执行 `pytest -m live` 才会发起真实网络请求。

## M2 货源 provider 说明

详细流程与切换步骤见 [`docs/M2-货源匹配说明.md`](docs/M2-货源匹配说明.md)。要点：

- 货源 provider 默认 `mock`，供本地/CI 免外部依赖跑通「建账号 → 采集(M1) → 匹配 → 候选」全链路。
- 切真实 1688 需在账号池配置可用 cookie，对应 live 冒烟测试 (`server/tests/test_source_live.py`) 默认跳过，需 `pytest -m live` 显式触发。
- 拼多多一期仅完成 JSON 解析层（`parse_pdd_items`），图搜/关键词搜索仍是占位（`NotImplementedError`），真实抓取（`selenium` + 代理截获）留待后续接入，暂无法通过环境变量切换为真实可用状态。
- CLIP 去重默认 `mock` embedder；切真实 CLIP 需同时设置 `EMBEDDER=clip` 与 `INSTALL_ML=true`（worker 镜像重新构建装 `[ml]` 组）。

## 后续里程碑（概览）

- **M1**：采集入库（已完成）——登录鉴权、采集任务（跟卖/自建）、六维筛选、WebSocket 进度推送
- **M2**：货源匹配（已完成）——账号池、双源（1688/拼多多）候选采集、CLIP 跨平台去重、匹配/候选 API
- **M3**：五维评分与审核台（已完成）——五维评分引擎+tier、LLM 抽象（mock/OpenAI 兼容）、审核台（采用/拒绝/自动采用）、评分/审核 API
- **M4**：跟卖定价与挂靠上架（已完成）——定价引擎（内置反推/自定义公式+最低价保护）、Ozon 写入抽象（mock/real）、草稿生成/确认闸门/自动确认、挂靠上架回写 Ozon 商品 ID、店铺凭据管理、上架 API + 前端。**注意**：M4 是确认后直接挂靠，暂无节奏/时间调度，节奏调度是 M5 的范围
- **M5**：上架节奏调度（待开发）
- **M6**：自建改图与类目映射（待开发）
- **M7**：公网部署（Nginx + HTTPS）（待开发）

# Ozon 跟卖/铺货自动化系统（M1 + M2 + M3 + M4 + M5 + M6 + M7）

面向 Ozon 平台跟卖/铺货场景的自动化辅助系统。M7 补齐了公网部署能力：Nginx + Let's Encrypt 生产部署包（HTTPS 终结、内部端口不公开、证书自动续期）、CORS 白名单收紧、登录失败限流，以及前端建任务页的类目树浏览入口（详见下方 M7 小节及 [`docs/部署与访问说明.md`](docs/部署与访问说明.md)）。M6 在自建（`listing_mode=create`）分支上补齐了「改图 → 类目属性映射 → 定价 → 自建草稿 → 类目/图确认闸门 → 按 M5 节奏上架 → 回写 Ozon 商品 ID」的完整闭环（详见下方 M6 小节），至此跟卖与自建两条分支均端到端可跑通（mock-first）。M1 完成骨架搭建：登录鉴权、采集任务管理（跟卖/自建两种模式、mock/composer/apify 三种数据源）、商品入库去重、六维条件筛选浏览、WebSocket 采集进度推送，以及 Docker Compose 一键启动。M2 在此基础上新增货源匹配：账号池、双源（1688/拼多多）候选采集、跨平台 CLIP 去重、匹配/候选管理 API。M3 在匹配候选之上新增五维评分与审核台：图像/标题/属性/价格/供应商五维打分 + tier 分级、LLM 抽象（mock/OpenAI 兼容，用于译标题与抽属性）、人工审核（采用/拒绝）或按阈值自动采用、评分/审核 API + 审核台前端。M4 在已采用候选之上新增跟卖定价与挂靠上架：定价引擎（内置毛利率反推 / simpleeval 自定义公式 + 最低价保护）、Ozon 写入抽象（MockOzonSeller/RealOzonSeller）、草稿生成与人工确认闸门（或按阈值自动确认）、挂靠上架回写 Ozon 商品 ID、店铺凭据管理（Fernet 加密）、上架 API + 前端 ListingReview/Shops 页面。M5 在确认草稿之上新增**上架节奏调度**：节奏配置（随机间隔/每日上限/活跃时段/是否等 Ozon 审核通过再推进下一条）、`plan_schedule` 把已确认草稿排出 `scheduled_at`、`tick_publish` 按节奏逐一挂靠并支持等审核门、ARQ cron 每分钟自动 tick、跨进程实时进度广播（`Broadcaster` memory/redis 双后端可切）、节奏/排期/tick/监控 API，以及首个使用 WebSocket 的前端页面 PublishMonitor。

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

> `docker-compose.yml` 是**本地测试/开发栈**（纯 HTTP，无域名/证书），用于本地开发与上服务器前的全流程验证。**生产环境**（公网域名 + HTTPS）请改用 `docker-compose.prod.yml`，完整步骤见下方「生产部署」章节及 [`docs/部署与访问说明.md`](docs/部署与访问说明.md)。

## 生产部署

生产部署走独立的 `docker-compose.prod.yml`（Nginx 终结 HTTPS + 反代，db/redis/api/worker 不发布公网端口）+ `deploy/certbot-init.sh`（Let's Encrypt 首次签证）。概要（完整 runbook 见 [`docs/部署与访问说明.md`](docs/部署与访问说明.md)）：

1. 服务器装好 Docker/Compose，域名 A 记录解析到公网 IP，放行 80/443。
2. `cp .env.prod.example .env.prod`，填 `DOMAIN`/`CERTBOT_EMAIL`/`POSTGRES_PASSWORD`，**重新生成** `JWT_SECRET`/`FERNET_KEY`，收紧 `CORS_ORIGINS` 为实际域名。
3. 首次签证（此时全栈尚未启动，certbot `--standalone` 临时占用 80）：`DOMAIN=<域名> CERTBOT_EMAIL=<邮箱> sh deploy/certbot-init.sh`。
4. 起全栈：`docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build`，浏览器访问 `https://<域名>`。

后续续期由 `certbot` 容器自动 `renew --webroot` 完成，无需人工干预。

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
| `OZON_SELLER_PROVIDER` | Ozon 跟卖挂靠：`mock`（默认，无需真实凭据）或 `real`（真实调用 Ozon Seller API，需店铺真实凭据）。仅影响**异步/worker 路径**（`run_publish`、`run_publish_tick` 及其 cron），`sync=true` 的同步路径当前仍固定用 `mock`，见 M4/M5 章节说明 | `mock` |
| `PROGRESS_BACKEND` | WS 进度广播后端：`memory`（默认，单进程本地 fan-out）或 `redis`（Redis pub/sub 跨进程广播，`worker`/`api` 分属不同进程时需要，例如生产环境 cron tick 的进度要推给 API 进程持有的 WS 连接） | `memory` |
| `IMAGE_PROVIDER` | 自建改图（M6）的 `gen`（AI 生图）op 用哪个 provider：`mock`（占位，返回确定性假 URL）/`local`（Pillow 本地处理，当前未接 AI 生图，选中等价于占位）/`openai_compat`/`http`（外部 AI 生图适配器，均为 `NotImplementedError` 占位，live 后置）。**`rmbg`/`whitebg`/`watermark`/`crop_norm` 四个本地类 op 恒走 Pillow `LocalProvider`，不受此变量影响**；改图默认流水线（`POST /images/process`）只跑 `whitebg`+`crop_norm`，不含 `rmbg`/`gen`。`rmbg` 去背景需 `rembg`（属 `[ml]` 组，随 `INSTALL_ML=true` 一起装），未安装时自动降级为白底（`meta.degraded=true`），不会报错中断 | `mock` |
| `CORS_ORIGINS`（M7）| 允许跨域访问后端 API 的来源白名单（JSON 数组字符串，如 `["https://your-domain.com"]`）；生产环境务必收紧为实际前端域名，`allow_credentials` 恒为 `false` | `["*"]` |
| `LOGIN_MAX_ATTEMPTS`（M7）| 登录失败限流：滑动窗口 `LOGIN_WINDOW_SEC` 内失败达此次数则锁定 `LOGIN_LOCKOUT_SEC` 秒（按 `用户名\|IP` 维度计数，`/auth/login` 锁定期间返回 `429` + `Retry-After`） | `5` |
| `LOGIN_WINDOW_SEC`（M7）| 登录失败计数的滑动窗口（秒） | `300` |
| `LOGIN_LOCKOUT_SEC`（M7）| 登录触发限流后的锁定时长（秒） | `900` |

生成生产用 `FERNET_KEY`：

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## 目录结构

```
ozon-listing-auto/
├── docker-compose.yml       # 本地测试/开发栈（HTTP）：postgres(pgvector) + redis + api + worker + web 一键启动
├── docker-compose.prod.yml  # 生产栈（HTTPS）：同上 + nginx(TLS 终结/反代) + certbot(自动续期)，内部服务不发布公网端口
├── .env.example             # 本地测试栈环境变量样例
├── .env.prod.example        # 生产栈环境变量样例（DOMAIN/CERTBOT_EMAIL/密钥/CORS_ORIGINS 等）
├── deploy/                  # 生产部署脚本与配置：certbot-init.sh（首次签证）、nginx.prod.conf（反代模板）
├── server/               # FastAPI 后端
│   ├── app/
│   │   ├── api/          # 路由（auth/tasks/collect/products/settings/ws/accounts/match/candidates/
│   │   │                 #   score/review/shops/listing/pace/publish/images/category/imagegen）
│   │   ├── core/         # 配置、数据库、鉴权、加密、progress.py（Broadcaster 进度广播 memory/redis）等基础设施
│   │   ├── models/       # SQLAlchemy ORM 模型（含 source_account/supply_candidate/review_decision/
│   │   │                 #   shop/listing_draft/publish_pace/product_image/category_map）
│   │   ├── services/     # 业务逻辑：六维筛选、入库去重、ozon_market 采集 provider、
│   │   │                 #   sources/（1688/拼多多货源 provider）、embedding/（mock/CLIP）、账号池、候选去重入库、
│   │   │                 #   scoring.py（五维评分引擎+tier）、review.py（审核队列/采用拒绝/自动采用/并发锁）、
│   │   │                 #   llm/（mock/OpenAI 兼容 LLM 抽象，译标题+抽属性）、
│   │   │                 #   pricing.py（内置反推+simpleeval 自定义公式定价引擎+最低价保护）、
│   │   │                 #   ozon_seller/（Ozon 写入抽象 mock/real，create_follow_offer/create_product/get_product_status）、
│   │   │                 #   listing_builder.py（候选+定价→跟卖/自建草稿）、publish_scheduler.py（节奏调度 plan_schedule）、
│   │   │                 #   imagegen/（改图 provider 抽象 mock/local/openai_compat/http）、
│   │   │                 #   category_map.py + category_tree.py（类目属性映射：记忆表→LLM 建议→兜底）
│   │   ├── workers/      # ARQ 后台任务（采集 collector、货源匹配 matcher、评分 scorer、上架 publisher、
│   │   │                 #   改图 imager，均支持断点续传/暂停；publisher.py 含 run_publish 直发 + tick_publish/
│   │   │                 #   run_publish_tick 节奏 tick，后者按分钟 cron 调度，按 draft.mode 分派 follow/create）
│   │   └── seed.py       # 启动种子：幂等创建首个管理员
│   ├── alembic/          # 数据库迁移
│   ├── static/images/    # 改图产物落盘目录（运行时生成，已 .gitignore，经 /static 对外暴露）
│   └── tests/
├── docs/                 # 里程碑设计文档（如 M2-货源匹配说明.md、M3-评分审核说明.md、M4-定价上架说明.md、
│                         #   M5-节奏调度说明.md、M6-自建分支说明.md）+ 部署与访问说明.md（M7 生产部署 runbook）+
│                         #   真实爬虫接入说明.md（composer-api 真实抓取：cookie/代理/反爬硬化/@live 测试）
└── web/                  # React + Vite 前端
    ├── src/
    │   ├── api/
    │   ├── pages/         # 登录、任务中心、商品列表、审核台（ReviewBoard）、上架审核（ListingReview，含自建
    │   │                  #   类目/属性/图确认）、店铺管理（Shops）、上架监控（PublishMonitor，节奏配置+队列
    │   │                  #   监控+实时 WS）、图片工作室（ImageStudio，/image-studio）、AI 生图配置
    │   │                  #   （settings/ImagegenSettings，/settings/imagegen）等页面
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
  - `OpenAICompatLLM`：真实 OpenAI 兼容 Chat Completions 客户端（Bearer 鉴权、失败重试 3 次、容错解析模型返回的 JSON），默认对接**通义千问 DashScope**，也可指向任意 OpenAI 兼容服务
  - `get_configured_llm(session)`（`app/services/llm/config.py`）：优先读后台 `/settings/llm`（admin）配置页——`llm_provider`(`mock`/`openai`) + `llm_base_url` + `llm_api_key`(Fernet 加密、`GET` 脱敏、留空不覆盖) + `llm_model`——`provider=openai` 且已填 key 时构造真实 `OpenAICompatLLM`，否则回退 `MockLLM`；配置页为空时进一步回退 `.env` 的 `LLM_PROVIDER`/`LLM_BASE_URL`/`LLM_API_KEY`/`LLM_MODEL`。评分 worker（`run_score`，即 `/score/start?sync=false` 异步路径）、类目建议 `POST /category/suggest`、自建草稿译标题 `POST /listing/build` 均走此函数（真实可用）；`POST /score/start?sync=true` 同步演示路径仍固定用 `mock`，不受配置页/env 影响。前端配置页：`web/src/pages/settings/LlmSettings.tsx`（`/settings/llm`）
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
  - `RealOzonSeller`（`get_ozon_seller("real")`）：以店铺 `Client-Id`/`Api-Key` 调 Ozon Seller API 创建跟卖 offer + 查询审核状态（`get_product_status`，M5 新增）的真实实现；**接口地址与请求体仍是占位实现**（`create_follow_offer` 的 `_ENDPOINT` 指向 `product/import`、`get_product_status` 指向 `product/info` 且返回值恒为 `pending`），**真实跟卖端点字段与审核状态映射需在 live 联调时校正**。M5 起挂靠 seller 由环境变量 **`OZON_SELLER_PROVIDER`**（`mock`/`real`，默认 `mock`）控制，但**只影响异步/worker 路径**（`POST /listing/publish?sync=false` 的 `run_publish`、`POST /publish/tick?sync=false` 入队后由 cron/`run_publish_tick` 执行）；`sync=true` 的同步路径（两个接口皆是）**仍固定使用 `mock`**，便于本地/演示/测试快速看到结果而不误触真实 Ozon 写入。要在生产环境真实挂靠，设置 `OZON_SELLER_PROVIDER=real` 并配好店铺真实凭据、始终走 `sync=false` 异步路径即可，无需再改代码；详见 [`docs/M4-定价上架说明.md`](docs/M4-定价上架说明.md) 第 5 节与 [`docs/M5-节奏调度说明.md`](docs/M5-节奏调度说明.md)。
- **草稿生成**（`app/services/listing_builder.py`，`POST /listing/build`）：把某任务下已采用（`adopted`/`auto_adopted`）的候选按定价参数逐个生成 `listing_drafts` 记录（幂等，同一候选不会重复生成），写入进价 `cost`、售价 `price`、毛利率 `margin`、定价明细 `pricing_detail`；被最低价拦截的候选草稿状态为 `below_min`，其余为 `draft`。
- **确认闸门与自动确认**（`app/workers/publisher.py`）：草稿默认需人工 `POST /listing/{id}/confirm` 确认（`draft → confirmed`）才能进入挂靠；若任务 `review_config.listing_review_required=false`，`POST /listing/auto-confirm` 会按可选阈值 `listing_score_min`（对比候选 `score_total`）批量把达标草稿从 `draft` 置为 `confirmed`。
- **挂靠上架**（`POST /listing/publish`）：对该任务下 `confirmed` 状态的草稿逐条调用 `OzonSellerProvider.create_follow_offer()`，成功则草稿状态置为 `published` 并回写 `ozon_result.ozon_product_id`；失败（含店铺凭据解密失败等异常）则置为 `failed` 并记录 `error`，单条失败不影响同批其余草稿。`sync=true` 请求内同步跑完（固定用 `mock` seller，便于本地/演示/测试）；`sync=false`（默认）经 ARQ 入队由 `worker` 异步执行 `app.workers.publisher.run_publish`（按 `OZON_SELLER_PROVIDER` 选 seller，生产设为 `real` 即走真实挂靠）。**M4 是「确认后直接挂靠全部 `confirmed` 草稿」，不经排期/节奏；M5 新增的 `/publish/schedule` + `/publish/tick` 是在此之上加一层节奏调度，两条路径并存**——不想要节奏调度时仍可直接用本节的 `/listing/publish`。
- **店铺凭据管理**（`/shops`，admin，`app/models/shop.py`）：Ozon 店铺 `Client-Id`（明文）+ `Api-Key`（`FERNET_KEY` 加密存储）CRUD，响应统一脱敏（不回传 `api_key` 字段）；草稿关联 `shop_id` 后挂靠时按店铺解密取用凭据。
- **上架 API**（`/listing`，`app/api/listing.py`）：`POST /listing/build`（operator 及以上）、`GET /listing/drafts`（按任务/状态过滤）、`POST /listing/{id}/confirm`（reviewer/admin）、`POST /listing/auto-confirm`（operator 及以上）、`POST /listing/publish`（publisher/admin，`sync` 参数控制同步/入队）、`GET /listing/monitor`（按状态统计草稿数量）。
- **前端**：`ListingReview`（`/listing`）——按任务生成草稿、选店铺、草稿列表展示进价/售价/毛利率/状态/Ozon 回写结果，逐条确认或按开关批量自动确认、一键挂靠；`Shops`（`/shops`）——新增/列表/删除店铺，`Api-Key` 输入框脱敏、列表不回显凭据。

详细操作流程（建店铺→配定价→build→确认→publish→切真实）见 [`docs/M4-定价上架说明.md`](docs/M4-定价上架说明.md)。

## M5 已实现功能（上架节奏调度）

- **节奏配置**（`publish_pace` 表 + `app/models/publish_pace.py`，`/pace` API）：`min_interval_sec`/`max_interval_sec`（两条上架之间的随机等待区间，默认 60~180 秒）、`daily_limit`（每日上架条数上限，默认 200，`≤0` 视为不限）、`active_hours`（活跃时段 `[start, end]` 小时数组，默认 `[9, 23]`，排期落在时段外会自动挪到下一个时段起点）、`wait_ozon_approval`（是否等上一批提交审核的草稿在 Ozon 侧出结果后才推进下一条，默认 `true`）。支持按任务覆盖（`task_id` 指定）或全局默认（`task_id=null`）：`GET /pace?task_id=<id>`（operator 及以上，任务未配置时按「任务级 → 全局默认 → 内置 `DEFAULT_PACE`」三级回退返回）、`PUT /pace?task_id=<id>`（写入/更新该任务或全局的节奏配置）。
- **排期调度**（`app/services/publish_scheduler.py::plan_schedule`，`POST /publish/schedule`，operator 及以上）：对该任务下所有 `confirmed` 且未排期（`scheduled_at is null`）的草稿，按节奏配置逐条累加「随机间隔」算出候选上架时间，用 `next_active_window()` 把落在 `active_hours` 时段外的时间点挪到下一个时段起点，并按 `daily_limit` 控制同一天排入的条数（超限则顺延到次日时段起点）；排定后草稿状态由 `confirmed` 置为 `scheduled` 并写入 `scheduled_at`。
- **逐一挂靠 + 等审核门**（`app/workers/publisher.py::tick_publish`）：每次 tick 先检查该任务是否有 `pending_review`（已提交待 Ozon 审核）的草稿——若 `wait_ozon_approval=true` 且存在，逐条调用 `OzonSellerProvider.get_product_status()` 轮询，只要有一条仍未出结果（非 `approved`/`rejected`）本轮就不再推进下一条（`approved` 转 `published`，`rejected` 转 `failed` 并记录 `error`）；否则取 `scheduled_at <= now` 的下一批到期草稿（默认 `max_batch=1`，逐条挂靠）调用 `create_follow_offer()`，成功后视 `wait_ozon_approval` 置为 `pending_review`（等审核）或直接 `published`（不等审核），失败置 `failed`。每条草稿独立 session + 独立 try/except，单条失败不影响同批其余草稿；每挂靠一条（第二步）通过 `Broadcaster` 广播一次进度（第一步的审核轮询本身不广播）。
- **周期调度**（`app/workers/arq_worker.py`）：`run_publish_tick`（ARQ cron，每分钟触发一次）扫描所有存在到期 `scheduled` 或 `pending_review` 草稿的任务并逐个 `tick_publish`；也可手动触发 `POST /publish/tick?task_id=<id>&sync=true|false`（publisher/admin）——`sync=true` 请求内同步跑一次（固定用 `mock` seller，便于演示/测试立即看到效果），`sync=false`（默认）经 ARQ 入队立即触发一次 `run_publish_tick`（按 `OZON_SELLER_PROVIDER` 选 seller）。
- **跨进程实时进度广播**（`app/core/progress.py::Broadcaster`）：M1 起 WS 进度推送一直是「单进程内 fan-out」，M5 起可切换后端——`memory`（默认）行为不变；`redis`（`PROGRESS_BACKEND=redis`）下 `publish()` 改为 `PUBLISH` 到 Redis 频道 `ws:progress`，API 进程在 `lifespan` 里额外起一个后台协程订阅该频道并本地 fan-out 给自己持有的 WS 连接——解决了 M5 场景下 `worker`/cron 进程产生的 tick 进度需要广播到 `api` 进程所持有的 WS 连接、而两者不在同一进程内的问题。
- **监控 API**（`GET /publish/monitor?task_id=<id>`，任意登录用户）：按状态（`draft`/`confirmed`/`scheduled`/`pending_review`/`published`/`failed`）统计草稿数量，附带下一条待上架草稿的 `next_scheduled_at`（`scheduled` 中最早的 `scheduled_at`）与当前生效的节奏配置 `pace`。
- **`OzonSellerProvider` 新增 `get_product_status()`**（M5 起协议方法，`app/services/ozon_seller/base.py`）：`MockOzonSeller` 默认返回 `approved`，可在构造时注入 `pending_ids` 集合使指定 `ozon_product_id` 返回 `pending`，供测试/本地演示模拟「审核中」；`RealOzonSeller` 为占位实现（请求 `product/info`，**真实的 Ozon 审核状态字段与 approved/pending/rejected 映射需在 live 联调时校正**，当前恒返回 `pending`）。
- **前端 PublishMonitor**（`/monitor`，`web/src/pages/PublishMonitor.tsx`，**M5 是首个使用 WebSocket 的前端页面**）：节奏配置表单（读取/保存 `/pace`）、「开始排期」（`/publish/schedule`）、「手动上架一条」（`/publish/tick?sync=true`）按钮，以及按状态分组的队列统计卡片（草稿/已确认/已排期/审核中/已上架/失败）+ 下一条 ETA。连上 `/ws/progress` 后收到任意消息即刷新监控数据实现近实时更新；WS 连接失败/出错/断开（`onerror`/`onclose`）都会回退为每 5 秒轮询 `GET /publish/monitor`，避免 WS 异常导致页面静默停更。

详细操作流程（配节奏→排期→tick→监控，生产切 `PROGRESS_BACKEND=redis` + `OZON_SELLER_PROVIDER=real`）见 [`docs/M5-节奏调度说明.md`](docs/M5-节奏调度说明.md)。

## M6 已实现功能（自建分支：改图与类目映射）

M6 把 `listing_mode=create`（自建）任务已采用的候选，补齐了跟卖分支没有的三步——**改图 → 类目属性映射 → 自建建品**——从而让自建分支走通「采集 → 匹配 → 评分 → 采用 → 改图 → 类目映射 → 定价 → 生成自建草稿 → 类目/图确认闸门 → 按 M5 节奏上架 → 回写 Ozon 商品 ID」的完整端到端链路（mock-first，全程本地/CI 可跑通）。

- **改图流水线**（`app/services/imagegen/` + `app/workers/imager.py::run_image_process_core`，`product_images` 表）：对任务下已采用候选的源图逐张跑一组 op，每 (候选, op) 产出一行 `product_images` 记录（含 `status`：`pending`/`processing`/`done`/`failed`、`result_url`、`provider`），单图下载/处理失败仅标记该行 `failed` 并记录 `error`，不影响同批其余图片。默认流水线 `ops=["whitebg", "crop_norm"]`（白底 + 裁剪归一）。
  - **Provider 分派**（`app/services/imagegen/factory.py::process_op`）：本地类 op（`rmbg` 去背景 / `whitebg` 白底 / `watermark` 去水印 / `crop_norm` 裁剪归一）恒走 `LocalProvider`（Pillow 真实处理，不受 `IMAGE_PROVIDER` 影响）；`gen`（AI 生图，当前默认流水线未启用）才按 `gen_provider` 参数分派到 `mock`（占位假 URL）/`local`/`openai_compat`/`http`（后两者为外部 AI 生图适配器，方法体 `NotImplementedError`，live 后置）。
  - **rmbg 降级**：`LocalProvider._rmbg()` 惰性 `import rembg`，未安装（默认镜像）时自动捕获异常降级为白底处理并在 `meta.degraded=true` 标记，不抛错中断流水线；需要真实去背景效果须以 `INSTALL_ML=true` 构建镜像安装 `rembg`（属 `[ml]` 可选依赖组，与 torch/cn_clip 同组）。
  - **API**（`/images`，operator/reviewer）：`POST /images/process?task_id=&sync=`（`sync=true` 请求内同步跑完；`sync=false` 经 ARQ 入队 `run_image_process` 异步执行，与 `/listing/publish?sync=` 同语义）、`GET /images?task_id=&status=`（列图）、`POST /images/{id}/approve|reject`（人工采用/弃用某张产物，只有 `approved` 的图会被自建草稿采纳）。前端 **ImageStudio**（`/image-studio`）：按任务触发改图、产物网格展示 + 逐张采用/弃用。
- **类目属性映射三级兜底**（`app/services/category_map.py::suggest_category` + `category_maps` 表）：
  1. **记忆表命中**：按候选标题归一化出的 `signature`（取标题前 120 字符）查 `category_maps`，命中且 `confirmed=true` 直接复用（`usage_count` 自增），跨任务同类商品无需重复问 LLM。
  2. **LLM 建议**：未命中时把候选标题 + `CategoryTreeProvider` 枚举的叶子类目列表交给 `LLMProvider.extract_json`，要求返回 `{category_id, path, attributes}` 结构化 JSON；解析失败或未给出 `category_id` 时判定 LLM 建议无效。
  3. **兜底默认**：LLM 也未给出有效结果时兜底为固定类目（当前写死 `category_id=15621048`「Дом」，`source="fallback"`）。
  - **人工确认写回复用**（`confirm_category`）：审核人在 `POST /listing/{draft_id}/confirm-category` 里改定的类目/属性会写回该草稿，同时 upsert 一条 `category_maps` 记录（`confirmed=true`），供后续同类商品的记忆表命中复用——形成「越用越准」的闭环。
  - **类目树**（`app/services/category_tree.py::CategoryTreeProvider`）：`mock`（默认，6 节点固定小树，含 3 个一级分类 + 3 个叶子类目，供 LLM 候选枚举 + 前端下拉 `GET /categories`）；`real`（走 composer-api `categoryChildV3` 真实全量类目树，`/settings/system` 切 `category_tree_provider=real`，详见下方「真实类目树说明」）。
- **自建草稿生成**（`app/services/listing_builder.py::build_create_drafts`，`POST /listing/build` 按任务 `listing_mode` 自动分派到此函数）：对已采用候选逐个译标题（`llm.translate`）+ 定价（复用 M4 `pricing.py`）+ 类目建议（上述三级）+ 拉取该候选 `status="approved"` 的改图产物 URL 列表，写入 `listing_drafts`（`mode="create"`）；按 `(task_id, candidate_id)` 幂等，无已采用图时 `images=[]` 待人工在确认页补齐。
- **确认闸门**（`app/workers/publisher.py::confirm_draft`）：`mode="create"` 的草稿在 `category_id is None` 或 `images` 为空时，`POST /listing/{id}/confirm` 会直接返回错误提示「自建草稿需先确认类目与图片再确认上架」而不放行，倒逼「先在 ImageStudio 采用图 + 在 ListingReview 确认类目属性，再确认上架」的顺序；跟卖（`mode="follow"`）草稿不受此闸门影响。前端 **ListingReview**（`/listing`）新增自建分支 UI：展示已采用图、类目下拉（`GET /categories`）+ LLM 建议（`POST /category/suggest`）+ 属性 JSON 编辑，确认后调 `POST /listing/{id}/confirm-category`。
- **自建建品（mock-first）**（`app/services/ozon_seller/`，`create_product()`，`_call_seller()` 按 `draft.mode` 分派）：`MockOzonSeller.create_product` 确定性返回成功、`ozon_product_id="OZC-{offer_id}"`，供本地/CI/演示全链路验证；`RealOzonSeller.create_product` 为占位实现（构造请求体但**不发真实网络请求**，恒返回 `ok=False` + `error="...未联调(live 校正)"`），真实 Ozon 建品端点（`/v2/product/import`）的字段与鉴权需 live 联调时校正。上架路径与跟卖分支共用 M5 节奏调度（`plan_schedule`/`tick_publish`），由 `OZON_SELLER_PROVIDER` 环境变量控制异步路径用 mock 还是 real（`sync=true` 同步路径固定 mock，语义同 M4/M5）。
- **AI 生图配置中心**（`GET/PUT /settings/imagegen`，admin，`app/api/imagegen.py`）：`provider`（`mock`/`local`/`openai_compat`/`http`）、`img_base_url`、`img_api_key`（`FERNET_KEY` 加密存储，`GET` 脱敏返回 `"***"`，`PUT` 时留空不覆盖已存密钥）、`img_model`、`fallback`（降级顺序）。前端 **AI 生图配置页**（`/settings/imagegen`，`ImagegenSettings.tsx`）。当前该配置项尚**未接入**改图流水线的实际 provider 选择（`run_image_process_core` 的 `gen_provider` 参数与默认 `ops` 列表未读取此配置或 `IMAGE_PROVIDER` 环境变量），留作后续把「gen 类 op + 外部适配器」接入主流程时的配置面。
- **数据模型**（迁移 `0006_m6_create_branch`）：新建 `product_images`（改图产物）、`category_maps`（类目映射记忆表，`signature` 唯一索引）；`listing_drafts` 新增 `title`/`description`/`category_id`/`attributes`/`images` 列，`ozon_product_id` 改为可空（自建草稿在建品成功前没有 Ozon 商品 ID）。
- **改图产物存储**：落盘到 `server/static/images/`（运行时生成，已 `.gitignore`），FastAPI 用 `StaticFiles` 挂载到 `/static` 对外提供；Docker Compose 下 `api`/`worker` 两个服务共享同一个宿主机目录卷（`./server/static:/app/static`），保证同步路径（`api` 容器内跑）与异步路径（`worker` 容器内跑）写入的产物互相可见、且容器重建不丢失。**若要接 Ozon 拉图上架真实生产环境，需要这个静态目录能被公网访问**（例如反代出公网域名，或替换为对象存储 + CDN 直链），当前 mock-first 阶段尚未处理，留作 M7/live 后置项。

详细设计取舍与 live 后置清单见 [`docs/M6-自建分支说明.md`](docs/M6-自建分支说明.md)。

## M7 已实现功能（公网部署与安全加固）

- **生产部署包**（`docker-compose.prod.yml` + `deploy/nginx.prod.conf` + `deploy/certbot-init.sh`）：Nginx 终结 TLS + 反代（`/api`、`/ws` 转发到内部 `api:8000`，静态前端走 `try_files`），db/redis/api/worker **不发布公网端口**（仅 nginx 发布 80/443），内部服务间通过 compose 网络互通；HTTPS 强制跳转 + HSTS（`Strict-Transport-Security`）等安全响应头。首次证书用 `certbot certonly --standalone`（证书与反代服务解耦，避开"nginx 需证书才能启动、证书又需 nginx 服务 HTTP-01 挑战"的先有鸡还是先有蛋问题），后续续期由独立 `certbot` 容器循环 `certbot renew --webroot` 自动完成。
- **CORS 白名单收紧**（`CORS_ORIGINS` 环境变量，JSON 数组字符串）：开发默认 `["*"]`（放行一切来源，便于本地联调），生产环境须收紧为实际前端域名；`allow_credentials` 恒为 `false`。
- **登录失败限流**（`app/api/auth.py` 调用 `app/core/login_throttle.py` 的 `LoginThrottle`，`LOGIN_MAX_ATTEMPTS`/`LOGIN_WINDOW_SEC`/`LOGIN_LOCKOUT_SEC`）：按 `用户名|IP` 维度滑动窗口计数，窗口内失败达到上限则锁定，`/auth/login` 锁定期间返回 `429` + `Retry-After`，登录成功或锁定到期后自动重置计数；IP 优先取 nginx 权威写入的 `X-Real-IP`（`$remote_addr`，不可伪造），避免通过伪造 `X-Forwarded-For` 首段绕过限流。
- **前端类目树浏览**：建任务页选类目入口改为 `TreeSelect` 树形浏览（复用 M6 已有的 `GET /categories`），无需再手填类目 ID。
- **本地测试栈仍是上线前的验收基线**：`docker compose up`（`docker-compose.yml`，纯 HTTP、无域名/证书）用来在本地/上服务器前跑一遍完整业务流程（建任务→采集→匹配→评分→审核→定价→上架→监控），验证通过后再按「生产部署」章节切到 `docker-compose.prod.yml` 上线。

完整生产部署 runbook（服务器准备→首次签证→起全栈→安全加固清单→更新方式→证书续期排查→已知 live 后置项）见 [`docs/部署与访问说明.md`](docs/部署与访问说明.md)。

## 测试

后端（156 个用例，另有 6 个标记为 `live` 的真实网络冒烟测试默认跳过，覆盖 M1 采集 + M2 货源匹配 + M3 评分审核 + M4 定价上架 + M5 节奏调度 + M6 自建改图/类目映射 + M7 CORS/登录限流 + 真实爬虫接入 + 真实 LLM 全链路 + 真实类目树）：

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

### 真实采集

`provider=composer` 从占位实现变为可用的真实抓取需要三步配置 + 了解一个前置限制，完整设计取舍见 [`docs/真实爬虫接入说明.md`](docs/真实爬虫接入说明.md)：

1. **填 cookie/代理**：后台 `/settings/crawler`（admin）填入浏览器 DevTools 复制的 Cookie 头（Network 面板任选一个 `ozon.ru` 请求，复制其 `Cookie` 请求头完整值）与可选代理（建议 RU 出口），另有 `timeout`/`min_delay`/`max_delay`/`max_retries` 可调；留空字段保存时不覆盖已存值。
2. **建任务即走真实抓取**：新建采集任务时 `entry_type` 选 `keyword`/`category`/`seller` 任一、`provider` 选 `composer`，启动后就会用上一步配置的 cookie/代理真实请求 Ozon。
3. **反爬失效可见**：请求命中 307/301/302/403/429 会指数退避重试，重试耗尽后任务状态置为 `failed`、错误信息写入任务 `stats.error`（在任务列表/监控页可见「疑似反爬/cookie 失效，请更新 cookie 或代理」的可操作提示），不会静默卡住。
4. **Seller real/mock 切换**（挂靠上架，非采集）：`/settings/system`（admin）切 `ozon_seller_provider` 为 `mock`/`real`，只影响 `run_publish`/`run_publish_tick` 的异步路径，`sync=true` 同步路径恒用 `mock`。

**关键前置**：Ozon 前台有滑块反机器人验证码，干净会话（新 IP/无历史 cookie）几乎必被拦截——真实采集前必须先在浏览器里人工通过一次验证码，再从该会话复制 cookie 填入配置页，光配置代理不足以绕过。

`@live` 真实抓取冒烟测试（默认跳过，不影响日常回归）：

```bash
cd server
OZON_COOKIE='<浏览器复制的 Cookie 值>' .venv/bin/python -m pytest tests/test_live_crawler.py -m live -v
```

未设 `OZON_COOKIE` 时用例自动 `skip`；断言真实搜索能解析出至少一条商品（含 `sku`/`title`）。

## M2 货源 provider 说明

详细流程与切换步骤见 [`docs/M2-货源匹配说明.md`](docs/M2-货源匹配说明.md)。要点：

- 货源 provider 默认 `mock`，供本地/CI 免外部依赖跑通「建账号 → 采集(M1) → 匹配 → 候选」全链路。
- 切真实 1688 需在账号池配置可用 cookie，对应 live 冒烟测试 (`server/tests/test_source_live.py`) 默认跳过，需 `pytest -m live` 显式触发。
- 拼多多一期仅完成 JSON 解析层（`parse_pdd_items`），图搜/关键词搜索仍是占位（`NotImplementedError`），真实抓取（`selenium` + 代理截获）留待后续接入，暂无法通过环境变量切换为真实可用状态。
- CLIP 去重默认 `mock` embedder；切真实 CLIP 需同时设置 `EMBEDDER=clip` 与 `INSTALL_ML=true`（worker 镜像重新构建装 `[ml]` 组）。

## 真实 LLM 说明

- 后台 `/settings/llm`（admin，前端 `LLM 配置` 菜单）填 `llm_base_url`/`llm_api_key`/`llm_model` 并把 `llm_provider` 切到 `openai`，保存后评分/类目建议/自建译标题即走真实模型，无需改 `.env` 或重启容器；留空 `llm_api_key` 保存不会覆盖已存密钥。
- 走真实 LLM 的路径：评分 worker（`run_score`，即 `POST /score/start?sync=false` 异步路径）、类目建议 `POST /category/suggest`、自建草稿译标题 `POST /listing/build`（自建分支）。`POST /score/start?sync=true` 同步演示路径仍固定用 `mock`，不受配置页/env 影响。
- 配置页留空时回退 `.env` 里的 `LLM_PROVIDER`/`LLM_BASE_URL`/`LLM_API_KEY`/`LLM_MODEL`（见上方环境变量表）。

`@live` 真实 LLM 冒烟测试（默认跳过，不影响日常回归）：

```bash
cd server
LLM_API_KEY=sk-... .venv/bin/python -m pytest tests/test_live_llm.py -m live -v
```

未设 `LLM_API_KEY` 时用例自动 `skip`；`LLM_BASE_URL`/`LLM_MODEL` 未设时分别默认通义千问 DashScope 地址与 `qwen-plus`；断言一次真实 `chat()` 调用返回非空字符串。

## 真实类目树说明

- 后台 `/settings/system`（admin）新增 `category_tree_provider`（`mock`/`real`）切换，与同页 `ozon_seller_provider` 并列；`real` 需先在 `/settings/crawler` 填好爬虫 cookie/代理（与真实采集共用同一份配置）。
- 切到 `real` 后，`RealCategoryTree`（`app/services/ozon_market/category_tree_real.py`）复用真实爬虫的 `composer_fetch`（cookie/代理轮换、退避重试、`CrawlerBlockedError` 识别）请求 `https://api.ozon.ru/composer-api.bx/_action/v2/categoryChildV3`，解析 `data.columns[].categories[]` 得到真实子类目（`id` 取自类目 `url` 末尾数字、`name` 取 `title`、`path` 取 `url`、无嵌套 `categories` 判定为叶子）。
- 前端类目浏览器（建任务/自建草稿确认页的 `TreeSelect`，复用 `GET /categories` 的惰性逐层加载）无需任何改动——切到 `real` 后自动变为真实全量类目树、逐层下钻。
- **前置限制同真实采集**：Ozon 前台有滑块反机器人验证码，干净会话大概率被拦截，需先在浏览器人工过一次验证码，再从该会话复制 cookie 填入 `/settings/crawler`。

`@live` 真实类目树抓取冒烟测试（默认跳过，不影响日常回归）：

```bash
cd server
OZON_COOKIE='<浏览器复制的 Cookie 值>' .venv/bin/python -m pytest tests/test_live_category_tree.py -m live -v
```

未设 `OZON_COOKIE` 时用例自动 `skip`；对 `parent_id=15500`（Электроника，真实一级类目）请求子类目，断言返回非空列表且每个节点含 `id`/`name`/`path`/`leaf`。

## 真实 CLIP 说明

`.env` 同时设置 `INSTALL_ML=true` + `EMBEDDER=clip` 后 `docker compose up -d --build worker` 重建镜像，货源匹配（M2）的跨平台去重即从 mock 向量切到真实中文 CLIP（`cn_clip` ViT-B/16，CPU 推理）；详细步骤、资源占用、验证方式见 [`docs/真实CLIP启用说明.md`](docs/真实CLIP启用说明.md)。

`@live` 真实 CLIP 向量冒烟测试（默认跳过，不影响日常回归；需先装 `[ml]`）：

```bash
cd server
.venv/bin/pip install -e '.[ml]'
.venv/bin/python -m pytest tests/test_live_clip.py -m live -v
```

## 后续里程碑（概览）

- **M1**：采集入库（已完成）——登录鉴权、采集任务（跟卖/自建）、六维筛选、WebSocket 进度推送
- **M2**：货源匹配（已完成）——账号池、双源（1688/拼多多）候选采集、CLIP 跨平台去重、匹配/候选 API
- **M3**：五维评分与审核台（已完成）——五维评分引擎+tier、LLM 抽象（mock/OpenAI 兼容）、审核台（采用/拒绝/自动采用）、评分/审核 API
- **M4**：跟卖定价与挂靠上架（已完成）——定价引擎（内置反推/自定义公式+最低价保护）、Ozon 写入抽象（mock/real）、草稿生成/确认闸门/自动确认、挂靠上架回写 Ozon 商品 ID、店铺凭据管理、上架 API + 前端。`POST /listing/publish` 仍保留「确认后直接挂靠全部 `confirmed` 草稿」的直发路径，不经排期
- **M5**：上架节奏调度（已完成）——节奏配置 `/pace`、`plan_schedule` 排期（随机间隔/活跃时段/每日上限）、`tick_publish` 逐一挂靠 + 等 Ozon 审核门、ARQ cron 每分钟自动 tick、`Broadcaster` 跨进程实时进度（memory/redis 可切）、排期/tick/监控 API、首个 WS 前端页面 PublishMonitor
- **M6**：自建改图与类目映射（已完成）——改图流水线（provider 抽象 mock/local(Pillow)/openai_compat/http，rmbg 降级白底）、类目属性映射三级兜底（记忆表/LLM/兜底）+ 记忆表复用、自建草稿生成、类目+图确认闸门、自建建品（mock-first，`RealOzonSeller.create_product` 占位待 live 联调）、`/images`、`/categories`、`/settings/imagegen` API + 前端 ImageStudio/ImagegenSettings
- **M7**：公网部署与安全加固（已完成）——生产部署包（`docker-compose.prod.yml` + Nginx TLS 终结/反代 + certbot 首签/自动续期，内部端口不公开）、CORS 白名单收紧、登录失败限流、前端类目树浏览入口；详见 [`docs/部署与访问说明.md`](docs/部署与访问说明.md)

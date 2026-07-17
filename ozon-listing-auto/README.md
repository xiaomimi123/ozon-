# Ozon 跟卖/铺货自动化系统（M1 + M2）

面向 Ozon 平台跟卖/铺货场景的自动化辅助系统。M1 完成骨架搭建：登录鉴权、采集任务管理（跟卖/自建两种模式、mock/composer/apify 三种数据源）、商品入库去重、六维条件筛选浏览、WebSocket 采集进度推送，以及 Docker Compose 一键启动。M2 在此基础上新增货源匹配：账号池、双源（1688/拼多多）候选采集、跨平台 CLIP 去重、匹配/候选管理 API。

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
| `FERNET_KEY` | 对称加密密钥（用于加密存储配置中心的第三方凭据，如 cookie/代理/API key） | 开发默认值，生产务必替换 |
| `ADMIN_USER` | 启动种子创建的首个管理员用户名 | `admin` |
| `ADMIN_PASSWORD` | 启动种子创建的首个管理员密码 | `admin123` |
| `EMBEDDER` | 货源匹配用的图像 embedder：`mock`（无需 torch）或 `clip`（真实 `ChineseClipEmbedder`） | `mock` |
| `INSTALL_ML` | worker 镜像构建参数，是否安装 `[ml]`（torch/cn_clip，体积达数 GB）；仅 `EMBEDDER=clip` 时需要设为 `true` | `false` |

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
│   │   ├── api/          # 路由（auth/tasks/collect/products/settings/ws/accounts/match/candidates）
│   │   ├── core/         # 配置、数据库、鉴权、加密等基础设施
│   │   ├── models/       # SQLAlchemy ORM 模型（含 source_account/supply_candidate）
│   │   ├── services/     # 业务逻辑：六维筛选、入库去重、ozon_market 采集 provider、
│   │   │                 #   sources/（1688/拼多多货源 provider）、embedding/（mock/CLIP）、账号池、候选去重入库
│   │   ├── workers/      # ARQ 后台任务（采集 collector、货源匹配 matcher，均支持断点续传/暂停）
│   │   └── seed.py       # 启动种子：幂等创建首个管理员
│   ├── alembic/          # 数据库迁移
│   └── tests/
├── docs/                 # 里程碑设计文档（如 M2-货源匹配说明.md）
└── web/                  # React + Vite 前端
    ├── src/
    │   ├── api/
    │   ├── pages/         # 登录、任务中心、商品列表等页面
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

## 测试

后端（50 个用例，默认跳过标记为 `live` 的真实网络冒烟测试，覆盖 M1 采集 + M2 货源匹配全链路）：

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
- **M3**：五维评分与审核台（待开发）
- **M4**：跟卖定价与上架（待开发）
- **M5**：上架节奏调度（待开发）
- **M6**：自建改图与类目映射（待开发）
- **M7**：公网部署（Nginx + HTTPS）（待开发）

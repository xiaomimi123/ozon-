# Ozon 跟卖 / 铺货自动化系统 — 开发文档 v3.0

> 面向 Claude Code 执行开发。相比 v2，v3 的核心变化：
> **① 以「跟卖」为主线**（挂 offer 到 Ozon 已有商品，不改图直接改价上架），自建 listing 为辅；
> **② 货源扩为 1688 + 拼多多 双源**；
> **③ 新增上架节奏控制**（审核后延时/随机间隔逐一上架）；
> **④ 定价支持自定义公式，对齐 Ozon 官方计算器口径**。
> 版本：v3.0 ｜ 日期：2026-07-16

---

## 0. 技术路线选型（同 v2）

采用工程化后端服务路线（而非 OpenClaw Agent 编排），原因：多人协作、大批量稳定、可断点续传、风控可控、可追溯。AI 只用于翻译/属性抽取/类目映射/生图等语义环节，其余为确定性代码流水线。保留一个可选 OpenClaw 对话入口作为轻量通道（§9）。

## 1. 两条业务主线（v3 核心）

系统支持两种上架模式，**跟卖为主、自建为辅**，在任务创建时选择：

| | 跟卖模式（主） | 自建模式（辅） |
|---|---|---|
| 目标 | 挂自己的 offer 到 Ozon **已存在的商品卡**，同款销售 | 创建**全新商品 listing** |
| 是否改图 | **跳过改图**（复用原商品卡图文） | 需改图（去背景/白底/水印） |
| 是否需类目属性映射 | 否（关联已有商品，属性继承商品卡） | 是（LLM 建议+人工确认） |
| Ozon 提供内容 | 仅价格 + 库存 + 发货方式 | 标题/描述/图/类目/属性/价格全套 |
| 前提 | 该品类 Ozon 允许自由跟卖（已确认） | 无 |

统一流程：
```
Ozon采集(选品/竞品) → 筛选 → 货源匹配(1688+拼多多) → 五维评分
  → 人工确认货源(可配置开关+评分阈值)
  → [跟卖分支] 定价 → 生成跟卖offer草稿 → 人工确认 → 按节奏逐一挂靠上架
  → [自建分支] 改图 → 类目属性映射 → 定价 → 生成listing草稿 → 人工确认 → 按节奏逐一上架
```

## 2. 技术栈（在 v2 基础上，货源侧新增拼多多）

| 层 | 选型 | 说明 |
|---|---|---|
| 服务端 | Python 3.11 + FastAPI | REST + WebSocket |
| 数据库 | PostgreSQL 16 + pgvector | 业务数据 + 向量 |
| 队列 | Redis + ARQ | 各环节异步 worker |
| Ozon 采集 | **前台爬虫(composer-api)** | 关键词/类目/竞品市场数据(官方API不提供)，见 §5.1 |
| Ozon 自有店/上架 | Ozon Seller 官方 API | 读自有店 + 跟卖offer(写) + 自建import(写)，需店铺 Client-Id/Api-Key |
| 货源 | 1688 客户端 + **拼多多客户端**（统一 SourceProvider 抽象） | 图搜+关键词，各自账号池 |
| 图片匹配 | Chinese-CLIP | CPU 推理 |
| LLM | **OpenAI 兼容接口**（base_url + api_key + model 可配） | 翻译/属性/类目映射；默认接通义千问，可换任意 OpenAI 格式模型/中转 |
| 生图（仅自建） | **OpenAI 兼容 / 通用 HTTP 接口**（provider 可配） | 可接入千问万相、GRSAI、云舞AI 或其他，配置切换 |
| Web 前端 | React + TS + Vite + Ant Design | 浏览器访问，无需安装客户端 |
| 反向代理 | Nginx + HTTPS(Let's Encrypt) | 托管前端静态资源 + 反代 API，公网访问 |
| 部署 | Docker Compose | |

## 3. 目录结构（增补货源多源 + 上架分支）

```
ozon-listing-auto/
├── server/app/
│   ├── workers/
│   │   ├── collector.py
│   │   ├── matcher.py        # 调多个 SourceProvider
│   │   ├── scorer.py
│   │   ├── imager.py         # 仅自建
│   │   └── publisher.py      # 含跟卖/自建两分支 + 节奏调度
│   ├── services/
│   │   ├── ozon_api.py       # 读 + 跟卖写 + 自建写
│   │   ├── sources/          # 货源抽象
│   │   │   ├── base.py       # SourceProvider 接口
│   │   │   ├── ali1688.py
│   │   │   └── pinduoduo.py
│   │   ├── embedding.py  scoring.py  llm.py
│   │   ├── imagegen.py       # 仅自建
│   │   ├── pricing.py        # 自定义公式引擎
│   │   ├── category_map.py   # 仅自建
│   │   ├── publish_scheduler.py  # 上架节奏(延时/随机)
│   │   └── exporter.py
│   └── core/
└── web/                    # Web 前端(React+Vite)，构建后由 Nginx 托管
    └── src/pages/  # Tasks/Filters/ReviewBoard/ImageStudio/ListingReview/PublishMonitor/Settings
```

## 4. 数据库 Schema（v3 增补）

在 v2 基础上：

```sql
-- 采集任务增加 listing_mode
ALTER TABLE collect_tasks ADD COLUMN listing_mode TEXT DEFAULT 'follow'; -- follow(跟卖)|create(自建)
ALTER TABLE collect_tasks ADD COLUMN source_platforms JSONB DEFAULT '["ali1688","pinduoduo"]';
ALTER TABLE collect_tasks ADD COLUMN review_config JSONB;
-- review_config: {source_review_required:bool, source_score_min:num|null,
--                 listing_review_required:bool, listing_score_min:num|null}

-- 货源候选增加来源平台
ALTER TABLE supply_candidates ADD COLUMN platform TEXT DEFAULT 'ali1688'; -- ali1688|pinduoduo

-- 上架草稿增加模式与节奏
ALTER TABLE listing_drafts ADD COLUMN mode TEXT DEFAULT 'follow';   -- follow|create
ALTER TABLE listing_drafts ADD COLUMN target_ozon_sku TEXT;         -- 跟卖: 目标商品卡SKU
ALTER TABLE listing_drafts ADD COLUMN barcode TEXT;                 -- 跟卖关联用条码
ALTER TABLE listing_drafts ADD COLUMN scheduled_at TIMESTAMPTZ;     -- 计划上架时间(节奏)
ALTER TABLE listing_drafts ADD COLUMN stock_qty INT DEFAULT 0;

-- 货源平台账号池增加 platform
ALTER TABLE ali_accounts RENAME TO source_accounts;
ALTER TABLE source_accounts ADD COLUMN platform TEXT DEFAULT 'ali1688'; -- ali1688|pinduoduo

-- 上架节奏配置(全局或按任务)
CREATE TABLE publish_pace (
  id SERIAL PRIMARY KEY, task_id INT REFERENCES collect_tasks(id),
  min_interval_sec INT DEFAULT 60,   -- 相邻两次上架最小间隔
  max_interval_sec INT DEFAULT 180,  -- 最大间隔(在min~max间随机)
  daily_limit INT DEFAULT 200,       -- 每日上架上限
  active_hours JSONB DEFAULT '[9,23]',-- 允许上架时段
  wait_ozon_approval BOOLEAN DEFAULT true -- 上一条Ozon审核通过后再上下一条
);
```

## 5. 模块规格

### 5.1 Ozon 采集（v3 重要修正：市场/竞品数据靠爬虫，自有店靠官方 API）

> **关键事实：Ozon 官方 Seller API 只能读写"你自己店铺"的商品（own_shop），它不提供"按关键词/类目搜市场商品""看竞品店铺卖什么"的公开接口。** 而跟卖选品的本质就是要找到"别人在卖的好商品"，这类市场/竞品数据官方给不了，必须靠爬取 Ozon 前台。因此采集分两条腿：

| 数据用途 | 数据来源 | 说明 |
|---|---|---|
| 关键词搜索、类目/首页选品、竞品店铺 | **爬取 Ozon 前台（composer-api）** | 跟卖选品的核心数据 |
| 自有店铺商品管理、上架写入、库存价格 | **Ozon Seller 官方 API** | 官方唯一能做且必须用官方 |

**采集技术方案（爬虫侧，composer-api 路线）：**
- 核心端点：`https://api.ozon.ru/composer-api.bx/page/json/v2`，传入前台页面 URL 参数（搜索页/类目页/卖家页），返回该页所有组件的结构化 JSON。
  - 该端点与 `www.ozon.ru/api/entrypoint-api.bx/page/json/v2` 功能一致，但**前者即使去掉认证/绕过相关 header 也不被 Cloudflare 拦截**，是当前最省资源的采集路径（该端点为非官方接口，可能随 Ozon 改版失效，需版本化封装、便于快速调整）。
- 类目树：`composer-api.bx/_action/v2/categoryChildV3?categoryId=<id>` 获取类目层级，用于"类目选品入口"与后续类目映射。
- 三个业务入口共用同一采集器与解析器，仅传入 URL 不同：
  - 关键词：`/search/?text=<kw>&page=<n>`
  - 类目/首页：类目路径 URL
  - 竞品店铺：`/seller/<id>/`（附带抓店铺评分、评价、总订单数）
- 解析层与请求层分离：端点或页面结构变化时只改解析器；解析 widget 结构抽取商品字段（SKU/标题/价格/月销/评分/评论/图/变体等，见 ozon_products 表）。
- 防反爬：随机 UA、请求间隔随机抖动、代理池、429/403 指数退避；竞品/商品详情可能需要有效 cookie 会话（参考成熟实现的会话保持策略）。

**SourceProvider 抽象（Ozon 侧，与货源侧同一设计思路，可切换）：**
```python
class OzonMarketProvider:                 # 抽象接口
    def search_by_keyword(kw, page) -> list[Product]: ...
    def list_by_category(category_url, page) -> list[Product]: ...
    def list_by_seller(seller_id, page) -> list[Product]: ...

# 实现：
# OzonComposerProvider  —— 自建爬虫(默认，composer-api)
# OzonApifyProvider     —— 可选：接付费成品采集API(如Apify的Ozon Scraper,按结果计费)作稳定兜底
# OzonMockProvider      —— 开发期mock数据,先跑通链路
```
配置页可选当前 Provider 与降级顺序：演示/早期可用付费 API 保稳定，规模化后切自建爬虫省成本；两者返回结构统一，上层无感。

**自有店官方 API（ozon_api.py）：** own_shop 商品读取用 `/v2/product/list` + `/v2/product/info`；上架写入见 §5.9。遵守官方频控。

**M1 攻坚落地（爬虫为主，三步走，降风险）：**
1. **打通 composer-api 单点**：用 `api.ozon.ru/composer-api.bx/page/json/v2` 传一个搜索/类目页 URL，成功解析出商品 JSON —— 数据源通了，整条链路就通了。
2. **抽象成 OzonMarketProvider**：先实现 `OzonComposerProvider` + `OzonMockProvider`（mock 先让筛选/列表界面可跑），预留 `OzonApifyProvider`。
3. **三入口复用**：关键词/类目/竞品共用采集器，跑通 采集→筛选→列表 整条链路。

**可参考的开源实现（起点，非直接依赖）：**
- `wondersell/wildsearch-crawler`：Scrapy 按类目/商品 URL 采集 Ozon，含变体，参考其解析与限速。
- `JTJag/ozon-sellers-parser`：竞品卖家采集，阐明了 composer-api 绕过 CF 的关键做法。
- `welel/ozon-scraper`：整理好的 Ozon 类目树 JSON，可直接用于类目映射。
- `sergerdn/ozon-search-queries-collector`：Ozon 选品分析搜索词数据（热度/加购率/卖家数等选品指标）。

变体归集、限速、断点续传：同 v2（parent 归并 + pHash 聚类；进度落库可暂停续跑）。

### 5.2 筛选（同 v2）
月销量/退货率/评分/重量/上架时间/跟卖数量等，可空可改重筛。

### 5.3 货源匹配（v3 改造：多源）

**SourceProvider 抽象接口**（sources/base.py）：
```python
class SourceProvider:
    platform: str
    def image_search(self, image_url) -> list[Candidate]: ...
    def keyword_search(self, kw) -> list[Candidate]: ...
    def fetch_detail(self, offer_id) -> CandidateDetail: ...
```
- 实现 `Ali1688Provider`、`PinduoduoProvider`，各自独立账号池与限速（拼多多同样有风控，参数独立可配）。
- matcher 按 `task.source_platforms` 遍历启用的 provider，各自图搜+关键词，结果合并进 supply_candidates（带 `platform` 字段），跨平台按图片指纹去重。
- 每个 Ozon 商品可同时得到 1688 与拼多多候选，评分后统一排序，审核台可见来源标签。

限速（各平台独立）：单账号≥6s/次、日上限可配、触发风控冷却换号，任务不中断。

### 5.4 五维评分（同 v2）
`总分 = 图45% + 标题20% + 属性15% + 价格5% + 供应商15%`；tier ≥85 auto / 70-84 review / <70 rejected。权重阈值可配。拼多多候选同一套评分逻辑。

### 5.5 人工审核台（v3 增补：可配置开关 + 评分阈值）

> 铁律不变：默认每条进入上架流程的货源都需人工确认。但**新增两个可配置项**（对应客户说明书要求）：

审核配置（review_config，任务级，设置页可调）：
- `source_review_required`（默认 true）：货源是否需人工审核。若客户信任评分，可关闭 → 达到阈值的候选自动采用。
- `source_score_min`（可空）：货源自动采用/进入下一步的最低分阈值；为空则不按分过滤。
- `listing_review_required`（默认 true）：上架草稿是否需人工确认。
- `listing_score_min`（可空）：同上，用于上架前筛选。

界面：审核台顶部提供「需要审核」开关（默认开）+ 评分阈值输入框（可空）。关闭审核开关时二次确认弹窗提示风险并留痕。
其余交互同 v2：左 Ozon 商品 / 右候选（带平台标签），✅采用❌拒绝🔄换候选，Redis 并发锁，决策写 review_decisions。

### 5.5.5 AI 接口抽象（LLM 与生图，统一 OpenAI 兼容）· v3 明确

所有 AI 能力（文本 LLM 与生图）**不绑定任何特定厂商**，统一走可配置的 OpenAI 兼容接口，换模型只改配置、不改代码。

**文本 LLM（llm.py）——翻译 / 属性抽取 / 类目映射建议：**
- 使用标准 OpenAI Chat Completions 协议：`POST {base_url}/chat/completions`，`Authorization: Bearer {api_key}`，body 含 `model` / `messages` / `temperature`。
- 配置项（设置页可维护，加密存储）：`llm_base_url`、`llm_api_key`、`llm_model`。
  - 默认接入通义千问：`base_url = https://dashscope.aliyuncs.com/compatible-mode/v1`，`model = qwen-plus`（或 qwen-max/qwen-turbo，按需）。
  - 也可填任意 OpenAI 格式服务（官方 OpenAI、其他中转、自建），无需改动代码。
- 用法：调用处只依赖 `llm.chat(messages, **opts)`，内部读配置发请求；属性抽取/类目映射要求返回结构化 JSON（temperature=0，失败重试）。

**生图（imagegen.py）——仅自建模式改图/营销图：**
- 定义统一 `ImageProvider` 接口：`generate(image, ops, params) -> url`。
- 内置适配器：
  - `OpenAICompatImageProvider`：走 OpenAI 兼容的图像接口（如千问万相 DashScope 兼容端点），配置 `img_base_url`/`img_api_key`/`img_model`。
  - `HttpImageProvider`：通用 HTTP 适配器，用于不完全遵循 OpenAI 格式的服务（如 GRSAI、云舞AI），通过配置映射请求/响应字段接入。
  - `LocalProvider`：本地 rembg 兜底（去背景/白底，不依赖外部 API）。
- 设置页选择当前生图 provider 及其 base_url/api_key/model，可配置失败降级顺序。
- 本地能做的（去背景、换白底、水印、裁剪归一化）优先本地处理，只有 AI 生成/增强营销图才调外部生图接口，省成本。

> 设计要点：LLM 与生图都做成"配置驱动的 provider"，客户/我方可自由切换千问、其他大模型或生图服务，避免被单一厂商锁定。密钥统一 Fernet 加密存库，不硬编码。

### 5.6 生图改图（v3：**仅自建模式**）
跟卖模式**跳过本模块**。自建模式：rmbg/whitebg/watermark/crop_norm 优先本地处理，gen（AI营销图）走 §5.5.5 的可配置生图 provider，失败降级，产物需 ImageStudio 人工确认。

### 5.7 类目属性映射（v3：**仅自建模式**）
跟卖模式无需映射（关联已有商品卡）。自建模式：通过 §5.5.5 的 LLM 接口建议 Ozon category_id + 属性（返回结构化 JSON），人工补齐，映射记忆表复用。

### 5.8 定价（v3 改造：自定义公式引擎）

`pricing.py` 支持两种模式：
1. **内置毛利率反推**（默认）：`Ozon售价 = 到手成本 / (1 - 目标毛利率 - Ozon佣金率 - 履约费率) × 汇率`，可加划线价系数。
2. **自定义公式**：设置页提供公式编辑器，变量白名单：`cost`(货源价)、`logistics`(物流)、`commission_rate`、`fx`(汇率)、`weight`、`target_margin` 等；用安全表达式求值（asteval/simpleeval，禁用任意代码）。
3. **对齐 Ozon 官方计算器口径**：佣金率、履约费按 Ozon 计算器的费率结构建模，参数在设置页可维护，便于与官方计算器核对一致。

每条草稿展示 进价/售价/毛利率 供审核。含最低价保护（低于阈值拦截）。

### 5.9 上架（v3 核心改造：双分支 + 节奏调度）

**publisher.py 按 draft.mode 分支：**

**跟卖分支（follow）：**
1. 对已采用货源，定价后生成跟卖草稿（mode=follow，含 target_ozon_sku / barcode / price / stock）
2. 人工在 ListingReview 确认（若开关要求）
3. 调 Ozon Seller API 以相同条码/SKU 创建 offer 关联到目标商品卡（复用原商品卡图文），提交 price + stock
4. **不涉及图片/类目/属性**，比自建快且成功率高

**自建分支（create）：** 同 v2，`/v2/product/import` 创建全新商品。

**上架节奏调度（publish_scheduler.py，v3 新增，两分支通用）：**
- 已确认草稿进入上架队列，**不一次性全推**，按 `publish_pace` 逐一上架：
  - 相邻两条间隔在 `min_interval_sec ~ max_interval_sec` 间**随机取值**（防风控特征）
  - 仅在 `active_hours` 时段上架
  - `daily_limit` 每日上限
  - `wait_ozon_approval=true` 时，**上一条 Ozon 后台审核通过后再上下一条**（轮询商品状态）；false 则仅按时间间隔
- PublishMonitor 页实时展示：队列、已上架、审核中、失败、下一条预计时间
- 失败重试；published 回写 Ozon 商品ID/状态

> Ozon 上架后有后台审核延时，节奏调度既是防风控，也匹配审核节拍——审核通过再上下一条，避免大批同时提交被判异常。

### 5.10 导出（同 v2 + 上架结果）
`scope=approved` 默认导已采用货源；上架结果表含 mode(跟卖/自建)、平台来源、Ozon商品ID、售价、毛利、上架时间、状态。

## 6. API（v3 增补）

```
POST /tasks   # body含 listing_mode, source_platforms[], review_config
POST /match/start?task_id=            # 遍历启用的货源平台
GET  /review/queue   POST /review/{candidate_id}
POST /images/process (仅自建)  POST /images/{id}/approve
POST /listing/build?task_id=          # 按mode生成跟卖/自建草稿
GET  /listing/drafts   POST /listing/{draft_id}/confirm
POST /listing/publish?task_id=        # 进节奏队列
GET  /publish/monitor?task_id=        # 上架进度/下一条时间
GET/PUT /settings/pricing  /settings/publish_pace  /settings/review_config
GET/PUT /settings/llm  /settings/imagegen   # OpenAI兼容接口配置(base_url/api_key/model/provider)
GET/POST /accounts?platform=ali1688|pinduoduo
GET/POST /shops
WS   /ws/progress
```

## 7. Web 前端页面（浏览器访问，无需安装）
登录 / 任务中心(选跟卖或自建、选货源平台) / 筛选 / 货源审核台(平台标签+审核开关+阈值) / 图片工作室(仅自建) / 上架审核 / 上架监控(PublishMonitor) / 导出 / 系统设置(店铺·评分·定价公式·上架节奏·货源账号池·汇率费率·**AI模型配置(LLM 与生图的 base_url/api_key/model)**)。前端为响应式设计，兼容桌面浏览器与平板。

## 8. 里程碑（v3 调整：跟卖优先）

| # | 内容 | 验收 |
|---|---|---|
| M1 | Docker+JWT+**Ozon前台爬虫(composer-api)打通**+OzonMarketProvider抽象(含mock)+关键词/竞品入口+筛选+商品列表+任务选跟卖/自建 | composer-api真实采到商品、三入口可跑、可筛、可选模式 |
| M2 | 货源匹配 1688 + 拼多多双源 + 账号池 + 跨平台去重 | 100 SKU 出双平台候选 |
| M3 | 五维评分 + 审核台(平台标签+审核开关+阈值) | 多人审核、可配开关 |
| M4 | **跟卖上架分支** + 定价(自定义公式) + 上架草稿确认 | 跟卖草稿→测试店成功挂靠 |
| M5 | **上架节奏调度**(随机间隔/时段/日限/等审核) + 上架监控页 | 逐一按节奏上架、可视 |
| M6 | 自建分支(改图+类目映射+自建上架) | 自建 listing 成功上架 |
| M7 | 竞品/类目入口 + OpenClaw入口 + Web前端部署上线(Nginx+HTTPS+域名) | 浏览器公网访问、全流程跑通 |

> 跟卖为主线，M4/M5 先交付跟卖闭环，客户可先跑起来；自建放 M6。

## 9. OpenClaw 轻量入口（可选，同 v2）
瘦客户端入口，调后端 API，非重跑逻辑。

## 9.5 交付形态与部署（Web 应用，浏览器访问）

**交付形态：Web 应用，员工通过浏览器访问，无需安装任何客户端。**

**最终交付物：**
- 完整源代码（服务端 + Web 前端）
- Docker 部署包 + docker-compose.yml + 《部署与访问说明》
- 操作手册

**部署架构：**
```
浏览器(员工) ──HTTPS──> Nginx ──┬─ 静态资源(Web前端构建产物)
                                └─ /api 反向代理 → FastAPI 服务端
                                                    ├ PostgreSQL / Redis
                                                    └ worker×N
```
- Web 前端 `vite build` 产出静态文件，由 Nginx 托管。
- Nginx 同时反向代理 `/api` 与 `/ws` 到后端；WebSocket 需配置 upgrade 头透传。
- 全部服务 Docker Compose 一键起。

**公网访问（本项目采用）：**
- 需一个域名，解析到服务器公网 IP。
- Nginx 配置 HTTPS，证书用 Let's Encrypt 免费签发并自动续期（certbot）。
- 员工在公司或外网均可通过 `https://域名` 访问；登录走系统账号权限体系（admin/operator/reviewer/publisher），JWT 鉴权。
- 安全加固：强制 HTTPS、登录失败限流、敏感接口鉴权、可选 IP 白名单/双因子（按需）。

**更新方式：** 前端/后端更新在服务器完成，员工刷新浏览器即为最新版，无需任何客户端升级操作。

**开发说明：** 开发者在 macOS 本机 `npm run dev`(前端) + 本地/远程后端即可完整开发调试，环境与最终线上一致，无跨平台打包问题。

## 10. 风险与降级
| 风险 | 应对 |
|---|---|
| 跟卖被 Ozon 限制(品牌/类目) | 已确认可自由跟卖；上架失败按错误码归类提示，不硬试 |
| 拼多多风控 | 独立账号池+限速，同1688策略 |
| 上架过快触发风控 | 节奏调度随机间隔+日限+等审核(核心防护) |
| 自定义公式写错致错价 | 安全表达式求值+最低价保护+上架前人工确认 |
| Ozon 前台爬虫(composer-api)失效 | 请求/解析分层版本化；OzonMarketProvider 可切换付费成品采集API(Apify等)兜底；持续跟踪端点变化 |
| 平台接口变化 | ozon_api/sources 版本化封装 |

## 11. 编码规范（同 v2）
全异步；worker 幂等；敏感信息 Fernet 加密；上架/定价/节奏模块必须单测覆盖边界（负毛利、零价、间隔为0、跨时段）；structlog 全链路 task_id。

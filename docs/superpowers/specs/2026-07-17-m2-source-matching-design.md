# 设计文档：M2 — 货源匹配（1688 + 拼多多双源 + 账号池 + CLIP 跨平台去重）

> Ozon 跟卖/铺货自动化系统 v3.0，第二个里程碑。建立在已合入 main 的「骨架 + M1」之上。
> 版本：v2 ｜ 日期：2026-07-17 ｜ 依据：`开发文档v3-*.md` §5.3/§5.4、`货源采集技术参考-1688与拼多多.md`、里程碑表 M2、M1 代码。

> **采集技术参考要点（据《货源采集技术参考》）**：
> - **1688 采集难度低、字段现成**：图搜（拍立淘）为主，参考 Zhui-CN/1688_image_search_crawler 的返回结构，字段基本覆盖候选表与 M3 五维评分所需。**主力货源，先做。**
> - **拼多多难度高**：anti_content 加密 + 需登录态 + 策略常变。**真实实现走 selenium/playwright + 代理截获移动端 API**（参考 SZFsir/pddSpider，"截流"而非"重放"），而非纯 JS 逆向；**一期先关键词检索、图搜后补**。**后做。**
> - **降级**：拼多多不稳定时，任务可**仅用 1688 货源完成，不阻塞主流程**（SourceProvider 抽象按平台启停）。拼多多优质代理 IP 属运行成本（甲方承担）。
> - **落地顺序**：先 1688 图搜跑通，再攻拼多多。

## 1. 目标与范围

**M2 交付 = 纯后端 + API 的货源匹配管线。** 验收「100 SKU 出双平台候选」。

Ozon 商品 → 遍历启用的货源平台(1688/拼多多) → 图搜 + 关键词搜 → CLIP 向量化 → 跨平台去重 → 落 `supply_candidates`；配套 cookie 账号池 + 各平台独立限速/冷却/换号。

**四个已确认决策：**
- **Mock-first**：先 `MockSourceProvider` + `MockEmbedder` 跑通「匹配→候选→去重」整条链路可测，再在同一接口后置真实 1688/拼多多 provider 与 Chinese-CLIP。
- **现在就上 CLIP**：跨平台去重用 Chinese-CLIP(ViT-B/16, 512 维) + pgvector 向量相似度，而非 pHash。
- **账号 = cookie/会话**：`source_accounts` 存 Fernet 加密的 cookie/会话 + 限速状态；provider 用 cookie 抓前台。
- **仅后端 + API**：前端候选展示与完整审核台归 M3。

**范围外（后续里程碑）**：五维评分、审核台、前端（M3）；跟卖定价/上架（M4）；节奏调度（M5）；自建改图/类目映射（M6）；公网部署（M7）。

## 2. 架构与新增文件

沿用 M1 的抽象 + 工厂 + mock-first 模式，新增两个 provider 家族，均配置驱动、mock 默认。

```
server/app/
├── services/
│   ├── sources/
│   │   ├── base.py        # SourceProvider 接口 + SupplyCandidateDTO
│   │   ├── mock.py        # MockSourceProvider(fixtures, 含跨平台近似重复样本+完整供应商字段)
│   │   ├── ali1688.py     # Ali1688Provider(httpx+cookie 拍立淘图搜/关键词, 参考 Zhui-CN 字段)
│   │   ├── pinduoduo.py   # PinduoduoProvider(selenium/playwright+代理截获, 一期先关键词; 参考 SZFsir)
│   │   └── factory.py     # get_source_provider(platform)
│   ├── embedding/
│   │   ├── base.py        # Embedder 接口(dim=512)
│   │   ├── mock.py        # MockEmbedder(URL 确定性哈希→归一化向量)
│   │   ├── clip.py        # ChineseClipEmbedder(cn_clip ViT-B/16 CPU 懒加载)
│   │   └── factory.py     # get_embedder(name)  默认 mock
│   ├── account_pool.py    # acquire/report_risk/限速/冷却/换号(Redis 锁)
│   └── candidate_ingest.py# dedup_and_upsert(CLIP 聚簇去重 + 幂等 upsert)
└── workers/
    └── matcher.py         # run_match_core / run_match(ARQ)
```

要点：
- Provider 与 Embedder 都配置驱动 + mock 默认；测试恒用 mock（无模型/无网络，CI 快稳）。
- CLIP 只在 matcher worker 用（懒加载 torch + cn_clip）；api 容器不装 ML。
- 账号池 cookie 加密存，`acquire` 满足「≥6s/次、日上限、非冷却」，风控换号任务不中断。
- 跨平台去重语义：**同一 Ozon 商品的候选集内**，CLIP 余弦相似度 > 阈值(默认 0.92, 可配) 折叠为一簇、保留代表；跨平台不同款各自成簇都保留 → 满足「双平台候选」。

## 3. 数据库 Schema（migration 0002）

pgvector 扩展在 0001 已建。向量 512 维（配置常量，MockEmbedder 同维）。

### 3.1 `source_accounts`
```
id, platform('ali1688'|'pinduoduo'), label,
credentials_encrypted(bytea, Fernet 存 cookie/会话 JSON),
status('active'|'cooldown'|'disabled' 默认 active),
last_used_at(timestamptz null),
daily_used_date(date null), daily_used_count(int 默认0),
daily_limit(int 默认200), min_interval_sec(int 默认6),
cooldown_until(timestamptz null), risk_hits(int 默认0),
created_at, updated_at
```

### 3.2 `supply_candidates`
```
id, task_id(fk collect_tasks), ozon_product_id(fk ozon_products),
platform('ali1688'|'pinduoduo'), offer_id,
title, price(numeric null), currency,
quantity_begin(int null 起批量), quantity_prices(jsonb null 阶梯价),
image_url, images(jsonb), phash(varchar null),
embedding(vector(512) null),
detail_url, supplier_name,
supplier_info(jsonb  # 复购率/信用/注册资本/省市/验厂标签/分项评分/GMV, M3 五维评分用),
dedup_group(int null), is_representative(bool 默认true),
source_account_id(fk source_accounts null),
status('candidate' 默认), raw(jsonb), created_at
```
- 唯一约束 `(task_id, ozon_product_id, platform, offer_id)`（幂等 upsert）
- 索引 `(task_id, ozon_product_id)`、`(ozon_product_id, platform)`
- `embedding` 建 hnsw/ivfflat 余弦近邻索引

### 3.3 `collect_tasks` 增列（匹配阶段状态，与采集分离）
```
ALTER TABLE collect_tasks ADD:
  match_status('pending'|'running'|'paused'|'done'|'failed' 默认 pending),
  match_cursor(jsonb null), match_stats(jsonb null)
```

限速配置放 `source_accounts`（账号级 min_interval_sec/daily_limit）；平台级默认可选走 `app_settings.source`。

## 4. 模块规格

### 4.1 SourceProvider（`services/sources/`）
```python
@dataclass
class SupplyCandidateDTO:
    platform: str; offer_id: str
    title: str | None; price: float | None; currency: str | None
    quantity_begin: int | None          # 起批量
    quantity_prices: list | None         # 阶梯价 [{qty, price}, ...]
    image_url: str | None; images: list[str]
    detail_url: str | None
    supplier_name: str | None            # company_name
    supplier_info: dict                  # 供应商质量指标(M3 五维评分用), 见下
    raw: dict
```
`supplier_info` 目标字段（对齐 Zhui-CN 1688 图搜返回，拼多多尽量映射，缺则 null）：
`repurchase_rate`(复购率) · `credit_level`/`credit_text`(信用 AAA) · `reg_capital`(注册资本) · `province`/`city` · `position_labels`(深度验厂/7×24H响应/先采后付…) · `scores`(综合/咨询/物流/退货等分项) · `gmv_price`(GMV)。M3 五维评分（供应商质量15%/属性一致性15%/价格5%）直接消费这些字段。

```python
class SourceProvider(Protocol):
    platform: str
    async def image_search(self, image_url: str, *, session) -> list[SupplyCandidateDTO]: ...
    async def keyword_search(self, kw: str, *, session) -> list[SupplyCandidateDTO]: ...
    async def fetch_detail(self, offer_id: str, *, session) -> SupplyCandidateDTO: ...
```
- `session` = 账号池取到的会话句柄：1688 为 cookie 会话（httpx）；拼多多为浏览器+代理句柄（selenium/playwright，"截流"返回 JSON）。接口对上层无感，具体用法由各 provider 决定。
- `MockSourceProvider`：fixtures 返回候选，样本含跨平台近似重复图 + 不同款，且填充完整 `supplier_info` 字段（供 M3 评分链路先跑通）；无账号/网络。
- `Ali1688Provider`（主力，先做）：httpx + cookie 拍立淘图搜为主、关键词为辅，字段结构参考 Zhui-CN；请求层与解析层分离（同 M1 composer）。真实版 `@pytest.mark.live` 默认跳过。
- `PinduoduoProvider`（后做）：selenium/playwright + 代理**截获移动端 API 返回 JSON**（不死磕 anti_content 逆向）；**一期先 `keyword_search`，`image_search` 后补**（可先 `NotImplementedError` 占位）；独立账号池 + 优质代理。真实版 `@pytest.mark.live` 默认跳过。
- `factory.get_source_provider(platform)`。

### 4.2 Embedder（`services/embedding/`）
```python
class Embedder(Protocol):
    dim: int  # 512
    async def embed_image(self, image_url: str) -> list[float]: ...
    async def embed_images(self, urls: list[str]) -> list[list[float]]: ...
```
- `MockEmbedder`：URL 确定性哈希 → 归一化 512 维向量（相近 URL 给相近向量）。
- `ChineseClipEmbedder`：懒加载 cn_clip ViT-B/16 CPU 推理，下载图片 → 向量，失败重试。
- `factory.get_embedder(name)` 默认 mock。

### 4.3 账号池（`services/account_pool.py`）
- `acquire(session_factory, platform) -> Account | None`：选 `status=active`、非冷却、`now-last_used_at>=min_interval_sec`、当日 `<daily_limit` 的账号；更新 `last_used_at`/`daily_used_count`（跨天重置 `daily_used_date`）；Redis 分布式锁防并发取同号。无可用 → 返回 None（该轮跳过，不报错）。
- `report_risk(account_id)`：`risk_hits+1`、`cooldown_until=now+冷却`、`status=cooldown`；matcher 换号继续。
- 解密 `credentials_encrypted` 得 cookie 会话交 provider。

### 4.4 候选入库 + 去重（`services/candidate_ingest.py`）
- `dedup_and_upsert(session, task_id, ozon_product_id, dtos, embedder)`：
  1. 每个 DTO 主图取 CLIP 向量。
  2. 候选集内按余弦相似度聚簇（`sim_threshold` 默认 0.92 可配）；簇内保留代表(`is_representative=true`)，其余标 false + 同 `dedup_group`；跨平台不同款各成簇都保留。
  3. 按 `(task_id, ozon_product_id, platform, offer_id)` 幂等 upsert，写 embedding/platform/dedup_group/source_account_id。
- 候选集小，相似度可内存计算；embedding 仍入库供 M3。

### 4.5 matcher worker（`workers/matcher.py`）
`run_match_core(session_factory, task_id, *, embedder, max_products=None, progress_cb=None)`：
1. 读 task → 遍历其 `ozon_products`（分批，`match_cursor` 断点续传）。
2. 每商品：遍历启用平台 → `account_pool.acquire` → provider `image_search(main_image_url)` + `keyword_search(title)` → 汇总 DTO。
3. `candidate_ingest.dedup_and_upsert` → 写库。
4. 限速：调用间按账号 `min_interval_sec`；风控 `report_risk` 换号。
5. 进度经 WS 广播（复用 M1 Broadcaster，`match` 事件）+ 写 `match_stats`；`match_status` running→done，异常置 failed（同 M1 collector §4.2.6）。
6. `run_match(ctx, task_id)`：ARQ 入口，真实 `async_session` + 配置选中的 Embedder。

## 5. API（M2）
```
POST /match/start?task_id=&sync=false     # operator+；sync=true 供测试
POST /match/pause?task_id=                # operator+
GET  /match/monitor?task_id=              # match_status/进度
GET  /candidates?task_id=&ozon_product_id=&platform=&only_representative=  # 分页
GET/POST/PUT/DELETE /accounts?platform=   # 账号池 CRUD(admin)，cookie 加密存/脱敏读
GET/PUT /settings/source                  # 限速/去重阈值/embedder 选择(admin)
WS   /ws/progress                         # 复用 Broadcaster + match 事件
```

## 6. Docker
- `pyproject.toml` 加可选组 `[ml] = ["torch(cpu)","cn_clip","pillow"]`。
- `server/Dockerfile` 加 `ARG INSTALL_ML=false`，条件安装 `.[dev,ml]` 或 `.[dev]`。
- `docker-compose.yml`：`worker` `build.args: INSTALL_ML=true`，`api` 默认 false。
- 默认 embedder=mock：不配 ML 也能 `docker compose up` 跑通 mock；切 clip 才需 worker ML 依赖。

## 7. 测试策略（TDD，mock-first）
- Provider 解析层单测（真实版 `@pytest.mark.live` 默认跳过）。
- MockEmbedder 单测：相近 URL 高余弦、不同低余弦（确定性）。
- 去重单测（核心）：跨平台近似重复 + 不同款 → 聚簇/代表正确、双平台不同款保留。
- 账号池单测：≥6s、日上限、跨天重置、冷却跳过、风控换号、无账号跳过不报错、Redis 锁。
- matcher worker 单测：Mock provider+embedder 跑 `run_match_core`，断言写库计数、跨商品断点续传、暂停/续跑幂等、异常置 failed。
- API 集成测：建任务→采集(mock)→`/match/start?sync=true`→`/candidates` 出双平台候选。
- `pytest` 0 warnings；测试全 mock，无 torch/网络。

## 8. M2 验收标准（「100 SKU 出双平台候选」）
1. 迁移 0002 建表 + `collect_tasks.match_*`；向量列可用。
2. `docker compose up`(embedder=mock) 一键跑通；`/accounts` CRUD（cookie 加密/脱敏）。
3. 建任务→采集(mock 100 商品)→`/match/start`→每商品对 `["ali1688","pinduoduo"]` 各出候选，落 `supply_candidates` 带 platform。
4. 跨平台 CLIP 去重生效：近似重复折叠为代表、双平台不同款保留；阈值可配。
5. 账号池限速/冷却/换号可用，风控不中断任务；断点续传/暂停/失败同 M1。
6. MockEmbedder 全链路可跑；ChineseClipEmbedder 走配置切换（worker ML 镜像）；真实 provider live 默认跳过。
7. 非 live 测试全绿 0 warnings；README/docs 更新 M2。

## 9. 风险与降级
| 风险 | 应对 |
|---|---|
| 1688 图搜反爬 | 难度低；mock-first 先通；cookie 账号池 + 限速(≥6s+抖动) + 冷却换号；真实版 live 默认跳过 |
| 拼多多 anti_content/策略常变 | **selenium/playwright + 代理截流**（不逆向 anti_content）；**一期先关键词、图搜后补**；真实版 live 默认跳过 |
| 拼多多这条腿不稳 | **降级：任务仅用 1688 完成，不阻塞主流程**（SourceProvider 按平台启停）；拼多多优质代理成本甲方承担 |
| CLIP 镜像重/下载慢 | 默认 mock embedder；ML 仅 worker 镜像装；懒加载；模型可预热 |
| 前台结构变化 | 请求层与解析层分离，只改解析器；provider 版本化 |
| 账号并发取同号 | Redis 分布式锁 + `last_used_at` 更新 |
| 匹配中断 | match_cursor 断点续传 + 幂等 upsert |

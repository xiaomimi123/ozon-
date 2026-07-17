# 设计文档：M3 — 五维评分 + 人工审核台（含 LLM 抽象）

> Ozon 跟卖/铺货自动化系统 v3.0，第三个里程碑。建立在已合入 main 的 M1（采集/筛选）+ M2（货源匹配）之上。
> 版本：v1 ｜ 日期：2026-07-17 ｜ 依据：`开发文档v3-*.md` §5.4/§5.5/§5.5.5、里程碑表 M3、M2 代码。

## 1. 目标与范围

**M3 交付** = 五维评分 + 人工审核台（含 LLM 抽象、审核台前端）。验收「多人审核、可配开关」。
管线：采集(M1) → 匹配(M2) → **评分(M3) → 审核(M3)**。

**三个已确认决策：**
- **现在引入 LLM 抽象**（mock-first、OpenAI 兼容、默认通义千问、配置驱动），用于「译标题 + 抽属性」。
- **给 `ozon_products` 加 `embedding` 列**（图评分需要 Ozon 主图向量，评分时用同一 Embedder 算，mock 确定性）。
- **做完整审核台前端**（左 Ozon／右候选带平台标签+五维分+tier，采用/拒绝/换候选，审核开关+阈值，Redis 锁提示）。

**范围外（后续里程碑）**：跟卖定价+上架（M4）；节奏调度（M5）；自建改图+类目映射（M6，LLM 类目映射在此）；公网部署（M7）。

## 2. 架构与新增文件

沿用 mock-first + 配置驱动 provider 模式，新增 LLM 家族 + 评分/审核模块 + 审核台前端。

```
server/app/
├── models/{review_decision.py}                     # 新增 ORM
├── models/{ozon_product.py, supply_candidate.py, collect_task.py}  # 增列(见 §3)
├── alembic/versions/0003_m3_scoring_review.py
├── schemas/{score.py, review.py}
├── api/{score.py, review.py}
├── services/
│   ├── llm/{base.py, mock.py, openai_compat.py, factory.py}
│   ├── scoring.py
│   └── review.py
└── workers/{scorer.py, arq_worker.py(增 run_score)}
web/src/pages/ReviewBoard.tsx
web/src/api/review.ts
```

要点：
- **五维评分**（§5.4，权重/阈值可配，存 `app_settings.scoring`）：图45%/标题20%/属性15%/价格5%/供应商15%；tier ≥85 auto / 70-84 review / <70 rejected。
- **mock-first**：MockLLM + MockEmbedder 下整条评分链路确定性可测，不需真实 key/网络/torch。
- **评分作为独立 worker**（采集→匹配→评分→审核）；LLM 只做译标题+抽属性两件事。
- **审核台**：scorer 写回分数 → review 队列（按 Ozon 商品聚合候选、按总分降序、平台标签）→ 决策写 `review_decisions`（Redis 并发锁）→ review_config 消费（不需审核+达阈值→自动采用）。

## 3. 数据库 Schema（migration 0003）

### 3.1 `ozon_products` 增列
```
ADD embedding vector(512)   # 同 M2 with_variant(JSON, sqlite)
```

### 3.2 `supply_candidates` 增列（审核结果复用已有 status）
```
ADD score_image float, score_title float, score_attr float, score_price float, score_supplier float,
ADD score_total float, tier varchar(16),           # auto|review|rejected
ADD score_detail jsonb
# status(M2, 默认 'candidate') → 审核后 adopted|rejected|auto_adopted
```

### 3.3 `collect_tasks` 增列（评分阶段状态）
```
ADD score_status varchar(16) default 'pending', score_cursor jsonb, score_stats jsonb
```

### 3.4 `review_decisions` 新表（多人审核留痕）
```
id, task_id(fk collect_tasks), ozon_product_id(fk ozon_products),
candidate_id(fk supply_candidates), reviewer_id(fk users, null=系统自动),
decision('adopt'|'reject'|'auto_adopt'), note(text null), created_at
```
索引 `(task_id, ozon_product_id)`、`(candidate_id)`。

### 3.5 配置（不建表）
- `app_settings.scoring`：`w_image=0.45/w_title=0.20/w_attr=0.15/w_price=0.05/w_supplier=0.15`、`tier_auto=85`、`tier_review=70`（缺省用代码默认）。
- `app_settings.llm`：base_url/api_key/model（Fernet 加密，M1 机制）。默认通义千问 `https://dashscope.aliyuncs.com/compatible-mode/v1` / `qwen-plus`。

## 4. 模块规格

### 4.1 LLM 抽象（`services/llm/`，§5.5.5）
```python
class LLMProvider(Protocol):
    name: str
    async def chat(self, messages: list[dict], **opts) -> str: ...
    async def translate(self, text: str, target_lang: str = "zh") -> str: ...
    async def extract_json(self, prompt: str) -> dict: ...
```
- `MockLLM`：translate 用确定性规则（内置小词表 + 回显）、extract_json 返回确定性 dict、chat 回显——无 key/网络、可复现。
- `OpenAICompatLLM`：标准 `POST {base_url}/chat/completions` + `Bearer api_key` + `model`；translate/extract_json 构造 prompt 调 chat，temperature=0、失败重试；配置从 `app_settings.llm` 读，默认通义千问。惰性 import httpx。
- `factory.get_llm(name)` 默认 mock；openai 惰性。

### 4.2 评分引擎（`services/scoring.py`）
```python
@dataclass
class ScoreResult:
    image: float; title: float; attr: float; price: float; supplier: float
    total: float; tier: str; detail: dict

async def score_candidate(ozon, candidate, *, embedder, llm, weights, thresholds, price_range=None) -> ScoreResult
def compute_tier(total, tier_auto, tier_review) -> str
```
各维（0–100，mock 下确定性）：
- image = `cosine(ozon.embedding, candidate.embedding)` 夹 [0,1]×100。
- title = `text_sim(llm.translate(ozon.title), candidate.title)`×100（difflib SequenceMatcher）。
- attr = `overlap(llm.extract_json(候选标题→属性), ozon.attributes)`×100（键值重叠率）。
- price = 价格合理性启发式（有效正价且落 price_range 内→高，缺失/异常→低）。
- supplier = supplier_info 加权（复购率 + 信用等级映射 + 分项评分均值）→ 0–100。
- total = Σ(权重×维度分)；tier = compute_tier。权重/阈值从 `app_settings.scoring` 读，缺省默认。

### 4.3 scorer worker（`workers/scorer.py`）
`run_score_core(session_factory, task_id, *, embedder, llm, max_products=None, progress_cb=None)`：
1. 遍历 ozon_products（score_cursor 断点续传）；给 Ozon 主图算向量写回 `ozon_products.embedding`（已算跳过）。
2. 每候选 → score_candidate → 写回五维分/总分/tier/score_detail。
3. 写 score_stats；score_status running→done；商品级异常置 failed（§4.2.6 范式）；paused 停止。
4. `run_score(ctx, task_id)`：ARQ 入口，配置选中 embedder + llm。

### 4.4 审核服务（`services/review.py`）
- `apply_auto_adopt(session, task_id, review_config)`：`source_review_required=false` 时，总分≥`source_score_min`（空则不过滤）的候选自动采用——写 `review_decisions(decision='auto_adopt', reviewer_id=null)` + `status='auto_adopted'`，不进人工队列。
- `get_review_queue(session, task_id, page, page_size)`：按 Ozon 商品聚合仍需人工审核的候选（已评分、总分降序、平台标签/tier/五维分）。
- `decide(session, candidate_id, reviewer_id, decision, note, *, lock=None)`：`decision ∈ {adopt, reject}`（前端「换候选」= 采用另一条）；Redis 锁锁住该 Ozon 商品（锁可注入，测试 no-op）；写 `review_decisions` + 更新 `candidate.status`（adopt→adopted / reject→rejected）。
- `review_lock(product_id)`：异步上下文管理器，默认 no-op，生产用 Redis。

## 5. API
```
POST /score/start?task_id=&sync=false     # operator+; sync=true 跑 run_score_core(mock embedder+llm)
POST /score/pause?task_id=                # operator+
GET  /score/monitor?task_id=              # score_status + score_stats
GET  /review/queue?task_id=&page=&page_size=   # 需人工审核的商品+候选(五维分/tier/平台标签)
POST /review/{candidate_id}               # body {decision:adopt|reject, note?}; reviewer+
POST /review/auto-adopt?task_id=          # operator+
GET/PUT /settings/scoring   /settings/llm  # 权重阈值/LLM 配置(admin, 复用通用端点)
```
角色：审核决策 `reviewer`（admin 超级通过）；评分启动 `operator`+。

## 6. 审核台前端（`web/src/pages/ReviewBoard.tsx`）
- 选任务 → 拉 `/review/queue`。左 Ozon 商品；右候选卡片（平台标签 + 五维分 + 总分 + tier 徽章），每卡 ✅采用 ❌拒绝（换候选=采用另一条）。
- 顶部审核开关（source_review_required）+ 阈值（source_score_min）；关开关二次确认 → `/review/auto-adopt`。
- 商品上/下一条切换；并发锁状态提示。
- `api/review.ts`：startScore/getQueue/decide/autoAdopt。加路由+菜单；任务页加「开始评分」。

## 7. 测试策略（TDD，mock-first）
- MockLLM 单测：translate/extract_json/chat 确定性；OpenAICompatLLM 解析用样本（live 默认跳过）。
- 评分引擎单测（核心）：score_candidate（MockEmbedder+MockLLM）确定性五维分+总分+tier；tier 边界；权重配置生效。
- scorer worker 单测：mock 跑 run_score_core——写回分、Ozon 向量、断点/暂停/失败。
- review 服务单测：apply_auto_adopt（不需审核+达阈值→auto_adopted 不进队列）；get_review_queue（排除自动采用）；decide（adopt/reject→status+review_decisions）；Redis 锁 no-op。
- API 集成测：采集→匹配→/score/start?sync=true→候选有分；/review/queue；/review/{id}；/review/auto-adopt。
- 前端：ReviewBoard 渲染队列 + 采用/拒绝（Vitest + mock api）。
- pytest 0 warnings；测试全走 mock（无 key/网络/torch/真实 Redis）。

## 8. M3 验收标准（「多人审核、可配开关」）
1. 迁移 0003：ozon_products.embedding + supply_candidates 五维分/tier + review_decisions + collect_tasks.score_*。
2. 采集→匹配→/score/start(mock)→候选得五维分+总分+tier。
3. 审核台前端：左 Ozon／右候选（平台标签+分+tier），采用/拒绝/换候选，决策写 review_decisions。
4. 可配开关：source_review_required=false+阈值→自动采用（不进队列、留痕）；关开关二次确认。
5. 多人审核：Redis 并发锁（同一商品/候选同时只被一人审）。
6. MockLLM+MockEmbedder 全链路；真实 OpenAICompatLLM 配置切换、live 默认跳过。
7. 非 live 全绿 0 warnings + README/docs + 前端 build。

## 9. 风险与降级
| 风险 | 应对 |
|---|---|
| LLM 反爬/超时/费用 | mock-first；temperature=0+重试；配置驱动可换模型/中转；标题/属性两处调用可缓存 |
| 俄→中翻译质量影响标题分 | 标题仅占 20%；译文可缓存；后续可换更强模型 |
| Ozon 主图向量缺失 | 无图则图分置 0 或按缺失降权，不崩 |
| 评分权重误配 | 代码默认兜底 + 归一校验（权重和≈1）|
| 多人并发审核冲突 | Redis 锁锁商品；无锁时靠 status 幂等 |
| 评分中断 | score_cursor 断点续传 + 幂等写回 |

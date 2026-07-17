# 设计文档：M5 — 上架节奏调度 + 跨进程实时进度（Redis pub/sub）

> Ozon 跟卖/铺货自动化系统 v3.0，第五个里程碑。建立在已合入 main 的 M1-M4 之上。
> 版本：v1 ｜ 日期：2026-07-17 ｜ 依据：`开发文档v3-*.md` §5.9(节奏调度)、publish_pace schema(§4)、里程碑表 M5、M4 代码。

## 1. 目标与范围

**M5 交付** = 上架节奏调度(随机间隔/时段/日限/等审核) + 跨进程实时进度(Redis pub/sub) + PublishMonitor 监控页。验收「逐一按节奏上架、可视」。把 M4 的"确认后直接挂靠"升级为"确认→排期→逐一按节奏挂靠"。

**四个已确认决策：**
- **scheduled_at 规划 + 周期 tick**：调度器给确认草稿排 `scheduled_at`(随机间隔内/避 active_hours 外/日限)，周期 ARQ cron tick 把到期草稿逐一上架。状态入库、重启安全、可测(M4 已预留 scheduled_at 列)。
- **现在上 Redis pub/sub**：Broadcaster 后端可选(memory 测试/redis 生产跨进程)，闭合 M1 起的遗留项。
- **OzonSeller 加 get_product_status 轮询**：wait_ozon_approval=true 时下一条前轮询上一条 Ozon 审核状态。
- **完整 PublishMonitor**：队列/已上架/审核中/失败 + 下一条 ETA + 实时 WS + 节奏配置。

**范围外(后续里程碑)**：自建分支改图+类目映射(M6)；公网部署(M7)。

## 2. 架构与新增文件

```
server/app/
├── models/publish_pace.py
├── alembic/versions/0005_m5_publish_pacing.py
├── schemas/pace.py
├── api/{pace.py, publish.py}
├── core/progress.py                 # 改造: Broadcaster 后端可选(memory/redis pub/sub)
├── core/config.py                   # 加 progress_backend
├── services/{publish_scheduler.py, ozon_seller/*(加 get_product_status)}
└── workers/{publisher.py(加 tick_publish + run_publish_tick), arq_worker.py(cron)}
web/src/{pages/PublishMonitor.tsx, api/pace.ts, api/publish.ts}
```

要点：
- 节奏调度: `plan_schedule` 排 scheduled_at + `tick_publish` 逐一上架(等审核门)。
- Redis pub/sub: worker publish → Redis → API 订阅 → 本地 fan-out 到 WS。现有 broadcaster.publish 调用点无感。
- publish_pace 三级回退: 任务 → 全局 → 代码默认。
- M4 `/listing/publish`(直发)保留; M5 加 `/publish/schedule` + tick。
- 草稿状态流: draft→confirmed→scheduled→publishing→published|pending_review|failed。

## 3. 数据库 Schema(migration 0005)

### 3.1 `publish_pace` 新表
```
id, task_id(fk collect_tasks, null=全局默认),
min_interval_sec(int 默认60 NOT NULL), max_interval_sec(int 默认180 NOT NULL),
daily_limit(int 默认200 NOT NULL), active_hours(jsonb 默认[9,23] NOT NULL),
wait_ozon_approval(bool 默认true NOT NULL), created_at, updated_at
```
索引 task_id(应用层 get-or-create: 任务→全局[task_id null]→代码默认 DEFAULT_PACE)。

### 3.2 无需改表
- `listing_drafts`: M4 已有 scheduled_at + status(varchar16); M5 新增状态值 scheduled/pending_review(字符串, 无迁移)。
- `collect_tasks`: 监控计数从 listing_drafts 聚合, 不加列。

### 3.3 配置(不建表)
`config.py` 加 `progress_backend: str = "memory"`(memory|redis)；生产 `PROGRESS_BACKEND=redis` + redis_url(M1 已有)。`DEFAULT_PACE` 常量兜底。

## 4. 模块规格

### 4.1 Broadcaster 后端可选(`core/progress.py` 改造)
- 保留本地连接管理 + `_local_broadcast(msg)`(fan-out 到本进程 WS)。
- `publish(msg)`: progress_backend=="redis" → `redis.publish("ws:progress", json)`; 否则 `_local_broadcast(msg)`。现有调用点无感。
- `start_redis_subscriber()`(仅 redis, API lifespan 起后台任务): SUBSCRIBE ws:progress → 收到消息 `_local_broadcast`。worker publish → Redis → API fan-out → WS。
- 测试用 memory: publish → 本地 fan-out, 无真 Redis。

### 4.2 OzonSeller 审核状态轮询
```python
class OzonSellerProvider(Protocol):
    ...
    async def get_product_status(self, *, client_id, api_key, ozon_product_id) -> str: ...  # approved|pending|rejected
```
- MockOzonSeller: 默认 "approved"; 可注入 pending_ids 模拟审核中(wait_approval 测试)。
- RealOzonSeller: 查 Ozon 商品信息端点(live)。

### 4.3 调度器(`services/publish_scheduler.py`)
```python
DEFAULT_PACE = {"min_interval_sec":60,"max_interval_sec":180,"daily_limit":200,"active_hours":[9,23],"wait_ozon_approval":True}
async def get_pace(session, task_id) -> dict          # 任务→全局→DEFAULT_PACE
def next_active_window(dt, active_hours) -> datetime   # dt 落 [start,end) 否则滚下个时段起点
async def plan_schedule(session, task_id, pace, *, now, rng) -> dict
```
plan_schedule: status='confirmed' 且 scheduled_at 空的草稿(按 id 序)逐一排:
1. cursor=now; per_day 计数(含当日已排/已上架起点)。
2. 每条: cursor += rng.randint(min,max)秒 → next_active_window(cursor) → 若 per_day[cursor.date()]>=daily_limit 滚次日时段起点; 置 scheduled_at=cursor, status='scheduled', per_day+=1。
3. 返回 {scheduled:n}。确定性(注入 now+种子 rng)。

### 4.4 tick 上架(`workers/publisher.py`)
```python
async def tick_publish(session_factory, task_id, *, seller, now, max_batch=1) -> dict
async def run_publish_tick(ctx)   # ARQ cron: 扫描有到期草稿的任务逐个 tick
```
tick_publish:
1. 读 pace.wait_ozon_approval。
2. 等审核门: 存在 status='pending_review' 的草稿 → get_product_status: pending→{waiting:True} 不推下条; approved→置 published(终态); rejected→failed。仅无 pending_review 才继续。
3. 取下一条到期: status='scheduled' 且 scheduled_at<=now, 按 scheduled_at 升序取 max_batch(默认1)。
4. 解密店铺凭据 → create_follow_offer → ok: wait_approval 则 pending_review 否则 published, 回写 ozon_result; not ok: failed+error。单条失败隔离。
5. broadcaster.publish 广播进度。返回 {published, pending_review, failed, waiting}。
- run_publish_tick(ARQ cron 每分钟): 有到期 scheduled 草稿的任务逐个 tick_publish(真实 seller/now)。

## 5. API
```
GET/PUT /pace?task_id=              # 节奏配置(operator+; get-or-create; task_id 空=全局)
POST /publish/schedule?task_id=     # plan_schedule 排 scheduled_at(operator+)
POST /publish/tick?task_id=&sync=   # 触发 tick(publisher+; sync=true mock seller + 当前 now)
GET  /publish/monitor?task_id=      # 各状态计数 + 下一条 scheduled_at(ETA) + pace 摘要
WS   /ws/progress                   # 复用; Redis 后端跨进程
```
角色: pace/schedule → operator+; tick → publisher+; monitor → 认证。

## 6. 前端 PublishMonitor
- 节奏配置: min/max 间隔/daily_limit/active_hours(起止小时)/wait_ozon_approval → PUT /pace。
- 监控: 各状态统计卡(草稿/已确认/已排期/审核中/已上架/失败)+ 下一条预计时间 + 开始排期 + 手动 tick。
- 实时: 连 /ws/progress(首个前端 WS 客户端)刷新; 断开回退轮询 /publish/monitor。
- api/pace.ts api/publish.ts; 路由+菜单。

## 7. 测试策略(TDD, mock-first)
- next_active_window 单测: 时段内/前/后。
- plan_schedule 单测(核心): 种子 rng 间隔递增、active_hours、daily_limit 滚次日; 确定性。
- tick_publish 单测(核心): 到期→published(或 wait_approval 下 pending_review); 等审核门(pending→waiting, approved→published 后可推下条); 未到期不推。
- get_product_status 单测: mock approved/注入 pending。
- Broadcaster 单测: memory publish→本地 fan-out; redis 路由分支(monkeypatch, 不连真 Redis)。
- API 集成测: pace get/put; schedule→scheduled+scheduled_at; tick sync→published; monitor 计数+ETA。
- 前端: PublishMonitor 渲染(Vitest + mock api + mock WS)。
- pytest 0 warnings; 测试全走 mock。

## 8. M5 验收标准(「逐一按节奏上架、可视」)
1. 迁移 0005 publish_pace。
2. 配节奏→采集→…→采用→定价→确认→/publish/schedule(排 scheduled_at)。
3. tick 逐一上架: 到期草稿逐条 published; 随机间隔/active_hours/daily_limit 生效; wait_approval 等上一条审核通过再下一条。
4. Redis pub/sub: Broadcaster 后端可切(memory 测试/redis 生产跨进程)。
5. PublishMonitor 前端: 队列/已上架/审核中/失败 + 下一条 ETA + 实时 WS + 节奏配置。
6. MockOzonSeller.get_product_status 全链路; 真实 live 默认跳过。
7. 非 live 0 warnings + README/docs + 前端 build。

## 9. 风险与降级
| 风险 | 应对 |
|---|---|
| 长跑调度不稳/重启丢状态 | scheduled_at 入库 + 周期 tick(无长 sleep), 重启安全 |
| Redis 不可用 | progress_backend=memory 兜底(单进程仍工作); pub/sub 失败不阻塞上架主流程 |
| 上架过快触发风控 | 随机间隔+日限+active_hours+等审核(核心防护) |
| 等审核轮询卡死 | get_product_status 超时/重试; rejected 置 failed 不无限等 |
| 前端 WS 断线 | 回退轮询 /publish/monitor |
| 真实 Ozon 审核端点未定 | mock-first; RealOzonSeller live 校正 |

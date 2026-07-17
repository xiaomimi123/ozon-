# 骨架 + M1 执行进度

计划: docs/superpowers/plans/2026-07-17-scaffold-m1.md
分支: feat/scaffold-m1
基线: bd1cd57 (计划提交)

## 任务状态
（每个任务 review 通过后追加一行）
Task 1: complete (commits c10ec3f..be76aff, review clean)
  - Minor 待办(留给后续): CORS allow_origins=["*"] 部署前收紧(M7); 3.11 解释器在 ~/.local/bin/python3.11
Task 2: complete (commits be76aff..953a1d3, review clean)
  - Minor 模式: 新模块缺中文 docstring(Global Constraint) → 后续 dispatch 显式要求补一行中文 docstring
Task 3: complete (commits 953a1d3..363b67f, review clean)
  - 修正了计划两处 bug: JSONB 在 SQLite 用 with_variant(JSON); env.py offline 函数
  - Minor 待办: 缺 alembic/script.py.mako(未来 autogenerate 才需); _JSONB 可提到 db.py 复用; 迁移 docstring 英文
Task 4: complete (commits 363b67f..d951ec4, review clean after 1 fix)
  - 修复 Important: conftest 未导入 app.models 致内存库空表; 已加 import + 回归测试 test_fixtures.py; override 精准清理
Task 5: complete (commits d951ec4..4bb996b, review clean, DONE_WITH_CONCERNS 已核实)
  - 修复 conftest `import app.models` 遮蔽 FastAPI app 对象的隐患 → 改 `from app import models`
  - 固定 bcrypt<4.1 (passlib 1.7.4 兼容)
  - Minor 待办: passlib crypt DeprecationWarning 可用 scoped filterwarnings 抑制(留给收尾)
Task 6: complete (commits 4bb996b..c3ecabd, review clean)
  -- 阶段0(骨架) 完成: 工程/核心基础设施/DB+ORM+迁移/测试基座/鉴权/配置中心 --
Task 7: complete (commits c3ecabd..144ff3d, review clean)
Task 8: complete (commits 144ff3d..65be305, review clean, DONE_WITH_CONCERNS 已核实)
  - 修复计划 bug: fixtures 路径多了一个 "app" 段 → parents[2]/"fixtures"
  - 关键事实: 12 条样本 dedup(sku→phash) 后 = 10 唯一(后续 collector 测试基准)
Task 9: complete (commits 65be305..2d66dc7, review clean)
Task 10: complete (commits 2d66dc7..b7bf798, review clean after 1 fix)
  - 采集 worker: 逐页+跨页去重+断点续传+暂停; 修复 stats 跨续跑累计 + 补 paused 回归测试
  - Minor 待办(留 Task 18/后续): provider 异常未置 failed 状态; 无并发锁(靠 DB 唯一约束兜底)
Task 11: complete (commits b7bf798..770b58a, review clean)
  - 用 ConfigDict 替 class Config(避免 pydantic 弃用告警)
  - Minor 待办(收尾批量清理): Starlette HTTP_422_UNPROCESSABLE_ENTITY→_CONTENT; 404 用 status 常量; passlib filterwarnings
Task 12: complete (commits 770b58a..beacdc9, review clean after 1 fix)
  - 采集启动(sync/入队)/暂停 API + WS Broadcaster; 修复 ARQ 连接池泄漏 + conftest 恢复 monkeypatch
  - 架构待办(留 M5): 内存 Broadcaster 无法跨进程(ARQ worker→API WS); 生产 sync=false 路径需 Redis pub/sub 才能推 WS 进度. M1 前端走 sync=true, WS 正常.
Task 13: complete (commits beacdc9..6a028da, review clean)
  -- 阶段1(M1 后端) 完成: Provider抽象/mock/去重/采集worker/任务API/采集API+WS/筛选+商品API. 后端 25 测试全绿 --
  - Minor 待办(收尾): /products page/page_size 加 Query(ge=1) 边界
Task 14: complete (commits 6a028da..303138e, review clean, DONE_WITH_CONCERNS 已核实)
  - 前端脚手架(React+TS+Vite+AntD)+登录+路由守卫; 测试基座加 matchMedia polyfill; node_modules 未提交
  - Minor 注: package-lock 用 npmmirror 镜像源(功能正常, CI/onboarding 需注意)
Task 15: complete (commits 303138e..9573778, review clean)
  - 任务中心页(建任务选跟卖/自建+启动sync=true+暂停+任务表)
  - 观察: 任务页用 sync+refresh 显示最终 stats, 无实时 WS(计划级设计, M1 可接受); Minor: 无 try/catch 错误提示(继承自计划)
  - 待办(Task16内处理): 缺 src/vite-env.d.ts 致 import.meta.env 类型报错, 会挡 npm run build
Task 16: complete (commits 9573778..8ec257a, review clean after 1 fix)
  - 商品列表页+六维筛选; 修复 Important: 补齐第六维 上架时间(listed_after) + 查询错误处理; vite-env.d.ts 使 npm run build 通过
  -- 阶段2(前端) 完成: 脚手架+登录+任务中心+商品列表; 前端 3 测试全绿, npm run build 通过 --
Task 17: complete (commits 8ec257a..5477eb5, review clean after 1 fix)
  - Docker Compose 一键启动: pg(pgvector)+redis+api+worker+web; alembic upgrade + 幂等种子 admin; nginx 反代 /api /ws
  - 修复 Important: 加 .dockerignore(修复 web 构建被宿主 node_modules 污染) + db healthcheck(api/worker RestartCount=0 干净启动) + npm ci + .env.example 可用 Fernet
  - 实测: docker compose up 全绿(health/login/web); 因宿主端口占用用 scratchpad 端口 override 验证
Task 18: complete (commits 5477eb5..92e193d, review clean, DONE_WITH_CONCERNS 已核实)
  - 真实 composer-api 爬虫 + parser(价格/图片/容错) + live 冒烟(默认跳过); 非 live 27 测试全绿, 0 warnings
  - 改 main.py on_event→lifespan(消除弃用告警, 种子仍在 startup 触发); httpx 0.28 proxies→proxy
  - live 实测: Ozon 返回 307 反爬(需 proxy/cookie 调优, 按计划推迟)
  - Minor 待办: composer 每次重试新建 AsyncClient; _parse_price 吞 0; lifespan 缺 docstring
Task 19: complete (commits 92e193d..f121ec8, review clean)
  - README + M1 使用说明; 收尾清理(422→UNPROCESSABLE_CONTENT / 404 常量 / products 分页 Query 边界)
  -- 全部 19 任务完成. 后端 27 测试 0 warnings; 前端 3 测试 + build; docker compose 一键启动实测通过 --

## 累计 Minor(留给最终评审 triage / 后续里程碑):
- CORS allow_origins=["*"] 部署前收紧(M7)
- composer 每次重试新建 AsyncClient; _parse_price 吞 0; lifespan 缺 docstring
- 内存 Broadcaster 跨进程限制(M5 Redis pub/sub); 生产 sync=false 不推 WS
- collector: provider 异常未置 failed; 无并发锁(靠 DB 唯一约束)
- 前端: Tasks/Products 部分调用无 try/catch(继承计划); 任务ID 输入无 name 不受 reset
- package-lock 用 npmmirror 镜像源; nginx 未设 Host 头

## 最终整支评审 (opus): READY TO MERGE
- 7 项 M1 验收全部满足; 无 Critical/Important 正确性缺陷; 后端27+前端3 全绿
- F1(前端未订阅 /ws/progress): 推迟 M5 — 与 Broadcaster 跨进程限制同源, 现在接客户端也收不到有效广播; M1 mock 走 sync+refresh 可接受
- 收尾: 补 collector provider 异常置 failed(spec §4.2.6) 后 finish 分支
收尾 fix: collector provider 异常置 failed + 日志 + 测试 (commit b27daab); 后端 28 测试 0 warnings
=== 骨架 + M1 全部完成, 待 finish 分支 ===

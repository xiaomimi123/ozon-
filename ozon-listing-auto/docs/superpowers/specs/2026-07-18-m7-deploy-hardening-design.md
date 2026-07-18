# 设计文档：M7 — 公网部署上线（Nginx + HTTPS）+ 安全加固 + 类目树浏览

> Ozon 跟卖/铺货自动化系统 v3.0，第七个（收尾）里程碑。建立在已合入 main 的 M1-M6 之上。
> 版本：v1 ｜ 日期：2026-07-18 ｜ 依据：`开发文档v3-*.md` §9.5(部署)、§5.1(类目入口)、里程碑表 M7、现有 docker-compose/nginx/main.py 代码。

## 1. 目标与范围

**M7 交付** = 公网部署上线（Nginx + HTTPS + 域名）+ 安全加固 + 类目树浏览辅助。验收「浏览器公网访问、全流程跑通」。这是收尾里程碑，把已完成的 M1-M6 功能包装成可公网交付的生产形态。

**两段式交付流程（用户确认）**：先用**本地 HTTP docker 栈**在本机全流程测试调整，再上服务器用**生产 HTTPS 栈**正式部署。

**四条工作线：**
1. **生产部署包**：`deploy/nginx.prod.conf`（HTTPS + HSTS + 强制跳转 + 反代 `/api` `/ws` + 托管静态）、`docker-compose.prod.yml`（nginx 终结 TLS + certbot 卷；db/redis/api/worker 不发布公网端口）、certbot 初始化/续期、`.env.prod.example`。
2. **CORS 收紧**：`main.py` 改读 `settings.cors_origins`（配置驱动，不再硬编码 `["*"]`）。
3. **登录失败限流**：`/auth/login` 加失败计数 + 锁定窗口（可注入时钟，单测覆盖）。
4. **类目树浏览辅助（前端）**：建任务选"类目"入口时用 M6 `GET /categories` 逐层浏览选类目回填 entry_value。
5. **《部署与访问说明》文档**：本地测试 → 域名解析 → certbot 签证 → prod compose up → 安全加固 → 更新方式。

**明确不做**：OpenClaw（本系统为独立产品，与 OpenClaw 无关）；真实域名解析与证书签发（用户按 runbook 在服务器执行）；self-signed 本地冒烟。

**已具备无需重做**：竞品/类目/关键词三采集入口 —— 后端 collector 已按 `entry_type` 分派、composer provider 三方法齐全，前端 Tasks.tsx 入口下拉已含 keyword/category/seller/own_shop。M7 仅加"类目树浏览辅助"这一便利增强。

**范围外/后置**（沿用既有 live 项）：RealOzonSeller / RealCategoryTree / 外部生图 / 真实爬虫 cookie·代理 的 live 校正；内存限流的 Redis 多实例后端。

## 2. 部署架构与生产配置

### 2.1 部署架构（生产）
```
浏览器 ──HTTPS(443)──> nginx ──┬─ 静态资源(前端 vite build 产物)
   (80 强制跳 443)            ├─ /api/ 反代 → api:8000  (剥离 /api 前缀)
                              └─ /ws/  反代 → api:8000  (Upgrade 头透传)
                                        api/worker ──> db(pgvector)/redis (仅内网)
```
前端 `api` 客户端 baseURL 默认相对 `/api`，WS 用 `${proto}://${location.host}/ws/progress`（协议感知，HTTPS 下自动 wss）—— 部署态**同源**，不触发 CORS，wss 自动生效。同一份 `vite build` 产物本地 HTTP 与生产 HTTPS 通用（无需注入域名）。

### 2.2 `deploy/nginx.prod.conf`
- `server{ listen 80 }`：`location /.well-known/acme-challenge/ { root <certbot-webroot>; }`（签证/续期），其余 `return 301 https://$host$request_uri`。
- `server{ listen 443 ssl; server_name ${DOMAIN}; }`：
  - `ssl_certificate /etc/letsencrypt/live/${DOMAIN}/fullchain.pem;` + `ssl_certificate_key .../privkey.pem;`
  - `add_header Strict-Transport-Security "max-age=63072000" always;` + `X-Content-Type-Options nosniff` + `X-Frame-Options SAMEORIGIN` + `Referrer-Policy strict-origin-when-cross-origin`。
  - `location /api/ { proxy_pass http://api:8000/; proxy_set_header Host $host; proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for; proxy_set_header X-Forwarded-Proto $scheme; }`（尾斜杠剥离 `/api`）。
  - `location /ws/ { proxy_pass http://api:8000/ws/; proxy_http_version 1.1; proxy_set_header Upgrade $http_upgrade; proxy_set_header Connection "upgrade"; }`。
  - `location / { root /usr/share/nginx/html; try_files $uri /index.html; }`。
- `${DOMAIN}` 由容器 entrypoint 用 `envsubst` 渲染模板 → 实际 conf。

### 2.3 `docker-compose.prod.yml`
- `db`(pgvector)/`redis`：**无 `ports:`**（仅内网，不对公网暴露）；db 挂 `pgdata` 卷。
- `api`/`worker`：**无 `ports:`**；`env_file: .env.prod`；`depends_on` db/redis 健康。
- `nginx`：`build: ./web`（多阶段：构建前端 + nginx 托管）；发布 `80:80` `443:443`；挂载渲染后的 `nginx.prod.conf`、`letsencrypt` 证书卷、`certbot-webroot` 卷；`DOMAIN` 环境变量。
- `certbot`：`image: certbot/certbot`；共享 `letsencrypt` + `certbot-webroot` 卷；`entrypoint` 续期循环（`trap exit TERM; while :; do certbot renew; sleep 12h; done`）。
- 命名卷：`pgdata`、`letsencrypt`、`certbot-webroot`。

### 2.4 `deploy/certbot-init.sh`
首次签发脚本（服务器执行一次）：
```
docker compose -f docker-compose.prod.yml run --rm certbot certonly \
  --webroot -w /var/www/certbot -d "$DOMAIN" --email "$CERTBOT_EMAIL" --agree-tos --no-eff-email
```
之后 nginx reload 加载证书；续期由 certbot 容器自动完成。

### 2.5 `.env.prod.example`
`DOMAIN`、`CERTBOT_EMAIL`、`CORS_ORIGINS=https://<域名>`、`DATABASE_URL`（内网服务名 db）、`REDIS_URL`（redis）、`JWT_SECRET`/`FERNET_KEY`（**显著提示生产必须重生成**）、`OZON_SELLER_PROVIDER`/`LLM_PROVIDER`/`EMBEDDER`/`IMAGE_PROVIDER`/`PROGRESS_BACKEND` 等 provider 开关。

### 2.6 本地测试栈 `docker-compose.yml`（保留 + 整理）
保持 HTTP（现有 web/nginx.conf 已反代 `/api` `/ws` + 托管静态）；整理注释，文档标注"上服务器前用它在本地 `docker compose up` 全流程验证"。不改变端口/服务结构（避免破坏既有本地开发）。

## 3. 安全加固

### 3.1 CORS 配置化（`app/main.py`）
- 现硬编码 `allow_origins=["*"]` → 改为 `allow_origins=settings.cors_origins`；`allow_methods`/`allow_headers` 保持 `["*"]`；`allow_credentials=False`（JWT 走 `Authorization: Bearer` 头、非 cookie，无需 credentials，故可用具体 origin 列表且不与 `*` 冲突）。
- 默认 `cors_origins=["*"]` 保留（仅 `npm run dev` 跨域用）；生产 `.env.prod` 设 `CORS_ORIGINS=https://域名`。部署态经 nginx 同源，此为纵深防御。

### 3.2 登录失败限流（`app/core/login_throttle.py` + `app/api/auth.py`）
```python
class LoginThrottle:
    def __init__(self, max_attempts=5, window_sec=300, lockout_sec=900): ...
    def check(self, key: str, *, now: datetime) -> int | None    # 锁定中返回剩余秒数, 否则 None
    def record_failure(self, key: str, *, now: datetime) -> None
    def reset(self, key: str) -> None
```
- key = `username` + 客户端 IP（`request.client.host` / `X-Forwarded-For` 首段）。
- `/auth/login`：进入先 `check` —— 锁定中直接返回 **429**（`Retry-After: <剩余秒>`）；密码错 `record_failure`；成功 `reset`。
- 内存 dict 存储 + 可注入 `now`（单测）。配置：`login_max_attempts=5`、`login_window_sec=300`、`login_lockout_sec=900`（`config.py`，env 覆盖）。
- 多 api 实例不共享 → 单实例够用；文档标注"横向扩容改 Redis 后端"（同 progress_backend 范式，后置）。

### 3.3 内部端口不公开 / nginx 加固
已在 §2：prod compose db/redis/api/worker 不发布端口；nginx 强制 HTTPS 跳转 + HSTS + 安全响应头。

> 沿用既有：JWT + 角色门、Fernet 加密、响应脱敏（M1-M6 已具备，不重复）。

## 4. 类目树浏览辅助（前端）

- `web/src/pages/Tasks.tsx`：`entry_type === "category"` 时，`entry_value` 处渲染 antd `TreeSelect`（惰性 `loadData`），复用 M6 `web/src/api/category.ts::getCategories(parentId)`（`GET /categories?parent_id=`）。
- 交互：展开惰性拉子类目（`getCategories(node.id)`），叶子可选；选中回填 `entry_value = 节点 path`。非"类目"入口保持原纯文本 Input。
- 数据映射：`{id,name,path,leaf}` → TreeSelect 节点（`value=path`、`title=name`、`isLeaf=leaf`）。
- 说明：类目树现为 M6 mock 固定小树，浏览器即可用；接 `RealCategoryTree`（composer-api `categoryChildV3`，live 后置）后自动变真实全量，前端无需改。

## 5. 测试策略（mock-first, 0 warnings）
- `login_throttle` 单测（核心）：连续失败达阈值→锁定返回剩余秒、锁定窗口过期→重置、成功→清零；注入 `now` 确定性。
- `/auth/login` 集成测：N 次错密码→第 N+1 次 429（含 `Retry-After`）；正确密码未锁定时正常发 token。
- CORS 配置化测：monkeypatch `settings.cors_origins` → 带 `Origin` 的请求响应 `Access-Control-Allow-Origin` 反映配置值（非恒 `*`）。
- 前端：`Tasks.tsx` 选"类目"入口 → TreeSelect 类目浏览器渲染（Vitest + mock `getCategories`）；非类目入口仍为 Input。
- 配置校验：`docker-compose.prod.yml` 合法 YAML；`deploy/nginx.prod.conf`/certbot 脚本存在且结构正确（nginx 语法本环境不跑，评审核对）。
- pytest 0 warnings；测试全走 mock。

## 6. M7 验收标准（「浏览器公网访问、全流程跑通」）
1. 生产部署包：`deploy/nginx.prod.conf`（HTTPS/HSTS/强制跳转/反代/静态）+ `docker-compose.prod.yml`（db/redis/api/worker 不公开端口）+ certbot 签证/续期 + `.env.prod.example`。
2. 本地测试栈 `docker-compose.yml`：`docker compose up` 后浏览器 `localhost` 全流程可跑（登录→建任务→采集→…→上架监控）。
3. CORS 配置化收紧（`main.py` 读 `settings.cors_origins`）。
4. 登录失败限流（默认 5 次锁定，可测）。
5. 类目树浏览辅助（建任务选类目→浏览选类目→回填 entry_value）。
6. 《部署与访问说明》：本地测试→域名→certbot→prod compose up→加固清单→更新方式。
7. 非 live 0 warnings + README/docs + 前端 build。

## 7. 风险与降级
| 风险 | 应对 |
|---|---|
| 真实域名/证书/服务器不在本环境 | 交付生产配置 + runbook，用户在服务器执行；本地 HTTP 栈先验证全流程 |
| composer-api 非官方接口失效 | 已版本化封装、解析层分离；live 校正 |
| 内存限流多 api 实例不共享 | 单 api 实例够用；Redis 后端后置（同 progress_backend 范式） |
| 证书续期失败致 HTTPS 中断 | certbot 定时续期 + nginx reload；文档给排查步骤 |
| 生产误用弱密钥 | `.env.prod.example` 显著提示 JWT_SECRET/FERNET_KEY 必须重生成 |
| 收紧 CORS 误伤本地开发 | 默认保留 `["*"]`；仅生产 env 收紧；部署态本同源 |

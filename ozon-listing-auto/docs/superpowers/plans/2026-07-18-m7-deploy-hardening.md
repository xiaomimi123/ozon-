# M7 公网部署 + 安全加固 + 类目树浏览 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把已完成的 M1-M6 包装成可公网交付的生产形态：Nginx+HTTPS 生产部署包、CORS 配置化收紧、登录失败限流、类目树浏览辅助、部署文档。验收「浏览器公网访问、全流程跑通」。

**Architecture:** 生产用 `docker-compose.prod.yml`（nginx 终结 TLS + certbot 自动续期；db/redis/api/worker 不发布公网端口）；本地测试沿用现有 HTTP `docker-compose.yml`。前端经 nginx 同源代理 `/api`·`/ws`（协议感知 wss），部署态不触发 CORS。安全加固为可测的后端改动（CORS 读配置 + 登录限流）+ nginx 层（HTTPS/HSTS/内部端口不公开）。

**Tech Stack:** FastAPI / Starlette CORS / Nginx(官方镜像 templates+envsubst) / certbot(Let's Encrypt) / Docker Compose / React+Ant Design TreeSelect / Vitest / pytest。

## Global Constraints

- Python 3.11；测试用 `.venv/bin/python -m pytest`（从 `ozon-listing-auto/server/`）。**不要**用系统 python3(3.9)。
- **pytest 0 warnings**；测试全走 mock（无真实网络/证书/域名/Redis）。
- 部署态前端与 API **同源**（nginx 反代 `/api`·`/ws`），故部署本身不依赖 CORS；CORS 收紧为纵深防御，默认 `["*"]` 保留（仅 `npm run dev` 跨域用）。
- 真实域名/证书/服务器不在本环境：TLS 部分交付为**生产配置 + runbook**，用户在服务器执行；本环境只验证可测代码 + 配置合法性。
- 登录限流内存实现、单 api 实例够用；多实例 Redis 后端为文档标注的后置项（同 progress_backend 范式）。
- 新代码沿用现有中文 docstring 风格与命名。

---

### Task 1: 安全加固后端 —— CORS 配置化 + 登录失败限流

**Files:**
- Modify: `app/core/config.py`（加 login_max_attempts / login_window_sec / login_lockout_sec）
- Modify: `app/main.py`（CORS 读 settings.cors_origins）
- Create: `app/core/login_throttle.py`
- Modify: `app/api/auth.py`（登录集成限流）
- Test: `tests/test_security_hardening.py`

**Interfaces:**
- Produces: `LoginThrottle(max_attempts, window_sec, lockout_sec)` with `check(key,*,now)->int|None`、`record_failure(key,*,now)`、`reset(key)`、`clear()`；模块单例 `login_throttle`。`/auth/login` 锁定中返回 429 + `Retry-After`。

- [ ] **Step 1: 写失败测试** `tests/test_security_hardening.py`

```python
import pytest
from datetime import datetime, timezone, timedelta
from starlette.middleware.cors import CORSMiddleware
from app.core.login_throttle import LoginThrottle, login_throttle
from app.core.security import hash_password
from app.models import User

_NOW = datetime(2026, 7, 18, 12, 0, tzinfo=timezone.utc)


def test_throttle_locks_after_max_attempts():
    t = LoginThrottle(max_attempts=3, window_sec=300, lockout_sec=900)
    for i in range(3):
        assert t.check("k", now=_NOW) is None
        t.record_failure("k", now=_NOW)
    rem = t.check("k", now=_NOW)
    assert rem is not None and rem > 0                     # 锁定, 返回剩余秒
    assert t.check("k", now=_NOW + timedelta(seconds=901)) is None   # 锁定过期→放行


def test_throttle_window_expiry_drops_old_failures():
    t = LoginThrottle(max_attempts=3, window_sec=300, lockout_sec=900)
    t.record_failure("k", now=_NOW)
    t.record_failure("k", now=_NOW + timedelta(seconds=400))   # 超窗, 旧的应失效
    t.record_failure("k", now=_NOW + timedelta(seconds=401))
    assert t.check("k", now=_NOW + timedelta(seconds=402)) is None  # 窗口内仅2次<3, 未锁


def test_throttle_reset_clears():
    t = LoginThrottle(max_attempts=2, window_sec=300, lockout_sec=900)
    t.record_failure("k", now=_NOW); t.record_failure("k", now=_NOW)
    assert t.check("k", now=_NOW) is not None
    t.reset("k")
    assert t.check("k", now=_NOW) is None


def test_cors_middleware_reads_settings():
    from app.main import app
    from app.core.config import settings
    cors = [m for m in app.user_middleware if m.cls is CORSMiddleware]
    assert cors, "CORS 中间件未注册"
    assert cors[0].kwargs.get("allow_origins") == settings.cors_origins   # 配置驱动, 非硬编码字面量
    assert cors[0].kwargs.get("allow_credentials") in (False, None)


@pytest.mark.asyncio
async def test_login_rate_limited_after_failures(client, db_session):
    login_throttle.clear()                                  # 单例跨测试隔离
    db_session.add(User(username="thr", password_hash=hash_password("right"), role="operator"))
    await db_session.commit()
    for _ in range(5):
        r = await client.post("/auth/login", data={"username": "thr", "password": "wrong"})
        assert r.status_code == 401
    r = await client.post("/auth/login", data={"username": "thr", "password": "wrong"})
    assert r.status_code == 429 and "Retry-After" in r.headers
    login_throttle.clear()
    ok = await client.post("/auth/login", data={"username": "thr", "password": "right"})
    assert ok.status_code == 200 and ok.json()["access_token"]
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/python -m pytest tests/test_security_hardening.py -q`
Expected: FAIL（ModuleNotFoundError: app.core.login_throttle）

- [ ] **Step 3: 改 `app/core/config.py`** —— 在 `progress_backend`/`image_provider` 段后加：

```python
    # 登录失败限流（§3.2）：窗口内失败达 max 次锁定 lockout 秒。
    login_max_attempts: int = 5
    login_window_sec: int = 300
    login_lockout_sec: int = 900
```

- [ ] **Step 4: 建 `app/core/login_throttle.py`**

```python
"""登录失败限流（§3.2）：滑动窗口计失败次数 + 锁定窗口。内存实现, now 可注入供测试。
多 api 实例不共享计数（单实例够用；横向扩容改 Redis, 后置, 同 progress_backend 范式）。"""
from datetime import datetime, timedelta
from app.core.config import settings


class LoginThrottle:
    def __init__(self, max_attempts: int = 5, window_sec: int = 300, lockout_sec: int = 900):
        self.max_attempts = max_attempts
        self.window = timedelta(seconds=window_sec)
        self.lockout = timedelta(seconds=lockout_sec)
        self._fails: dict[str, list[datetime]] = {}   # key -> 窗口内失败时刻
        self._locked: dict[str, datetime] = {}        # key -> 锁定截止时刻

    def check(self, key: str, *, now: datetime) -> int | None:
        """锁定中返回剩余秒数(>0)，否则 None（顺带清理过期锁定）。"""
        until = self._locked.get(key)
        if until is not None:
            if now < until:
                return int((until - now).total_seconds()) + 1
            self._locked.pop(key, None)
            self._fails.pop(key, None)
        return None

    def record_failure(self, key: str, *, now: datetime) -> None:
        fails = [t for t in self._fails.get(key, []) if now - t < self.window]
        fails.append(now)
        self._fails[key] = fails
        if len(fails) >= self.max_attempts:
            self._locked[key] = now + self.lockout

    def reset(self, key: str) -> None:
        self._fails.pop(key, None)
        self._locked.pop(key, None)

    def clear(self) -> None:
        self._fails.clear()
        self._locked.clear()


login_throttle = LoginThrottle(settings.login_max_attempts, settings.login_window_sec, settings.login_lockout_sec)
```

- [ ] **Step 5: 改 `app/main.py`** —— CORS 读配置。把：

```python
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)
```
改为：
```python
from app.core.config import settings as _settings
app.add_middleware(
    CORSMiddleware, allow_origins=_settings.cors_origins, allow_methods=["*"],
    allow_headers=["*"], allow_credentials=False,
)
```
（若 `main.py` 顶部已 import settings，则复用，不要重复 import；用已有名字即可。）

- [ ] **Step 6: 改 `app/api/auth.py`** —— 登录集成限流。整体替换 `login` 函数为：

```python
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request, status
from app.core.login_throttle import login_throttle
# ... 其余 import 保持

@router.post("/login", response_model=TokenOut)
async def login(request: Request, form: OAuth2PasswordRequestForm = Depends(), s: AsyncSession = Depends(get_session)):
    ip = (request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
          or (request.client.host if request.client else "?"))   # 生产在 nginx 后, 取 XFF 首段
    key = f"{form.username}|{ip}"
    now = datetime.now(timezone.utc)
    remaining = login_throttle.check(key, now=now)
    if remaining is not None:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "登录尝试过多，请稍后再试",
                            headers={"Retry-After": str(remaining)})
    u = (await s.execute(select(User).where(User.username == form.username))).scalar_one_or_none()
    if not u or not verify_password(form.password, u.password_hash):
        login_throttle.record_failure(key, now=now)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "用户名或密码错误")
    login_throttle.reset(key)
    return TokenOut(access_token=create_token(u.username, u.role), role=u.role)
```
（`Request` 需加入 fastapi import；`datetime/timezone` 加 import。）

- [ ] **Step 7: 运行测试通过 + 回归**

Run: `.venv/bin/python -m pytest tests/test_security_hardening.py -q && .venv/bin/python -m pytest tests -q`
Expected: 全绿 0 warnings。

> 注意回归：现有大量测试调 `/auth/login` 成功登录（成功即 `reset`），不会触发限流；本任务新测试用独立用户名 `thr` 且首尾 `clear()`，避免污染单例。若回归出现某测试被 429，检查是否有测试用错密码多次未清理——用 `login_throttle.clear()`。

- [ ] **Step 8: 提交**

```bash
git add app/core/config.py app/core/login_throttle.py app/main.py app/api/auth.py tests/test_security_hardening.py
git commit -m "feat(m7): CORS 配置化收紧 + 登录失败限流(可测, 429+Retry-After)"
```

---

### Task 2: 类目树浏览辅助（前端）

**Files:**
- Modify: `web/src/pages/Tasks.tsx`（entry_type=category 时用 TreeSelect 浏览类目）
- Test: `web/src/pages/Tasks.test.tsx`（扩展）

**Interfaces:**
- Consumes: `web/src/api/category.ts::getCategories(parentId?)`（M6 已有，`GET /categories?parent_id=` → `[{id,name,path,leaf}]`）。

- [ ] **Step 1: 读现有** `web/src/pages/Tasks.tsx` 与 `web/src/pages/Tasks.test.tsx` 与 `web/src/api/category.ts`，确认 Form 结构、现有测试 mock/render 范式、getCategories 签名与返回。

- [ ] **Step 2: 写/扩展测试** `web/src/pages/Tasks.test.tsx`（mirror 现有 mock-api 范式）

新增一个测试：mock `../api/category` 的 `getCategories` 返回 `[{id:17028922,name:"Обувь",path:"Обувь",leaf:false}]`；渲染 Tasks；把"入口"Select 改选"类目"；断言类目 TreeSelect 出现（例如 placeholder "浏览选择类目" 可见）且 `getCategories` 被调用。若现有测试文件已 mock 其它 api，保持一致的 mock 方式（`vi.mock`）。关键断言示例：
```tsx
// vi.mock("../api/category", () => ({ getCategories: vi.fn().mockResolvedValue([{ id: 17028922, name: "Обувь", path: "Обувь", leaf: false }]) }));
// ...渲染后选择 entry_type=category, 断言:
expect(await screen.findByText("浏览选择类目")).toBeInTheDocument();
expect(getCategories).toHaveBeenCalled();
```
（具体选择"类目"的交互方式对齐现有测试操作 antd Select 的写法。）

- [ ] **Step 3: 运行确认失败**

Run（从 `web/`）: `source ~/.nvm/nvm.sh && nvm use 20 >/dev/null && npx vitest run src/pages/Tasks.test.tsx`
Expected: FAIL（TreeSelect/placeholder 未渲染）

- [ ] **Step 4: 改 `web/src/pages/Tasks.tsx`**

顶部 import 加：
```tsx
import { TreeSelect } from "antd";
import { useEffect, useState } from "react";   // 若已 import useState/useEffect 则复用
import { getCategories } from "../api/category";
```
组件内加类目树惰性加载状态与 loader（放在 `const [form] = Form.useForm()` 之后）：
```tsx
  const [catTree, setCatTree] = useState<any[]>([]);
  const loadRoots = async () => {
    if (catTree.length === 0) {
      const ns = await getCategories();
      setCatTree(ns.map((n: any) => ({ id: String(n.id), pId: 0, value: n.path, title: n.name, isLeaf: n.leaf })));
    }
  };
  const onLoadCat = async (node: any) => {
    const children = await getCategories(Number(node.id));
    setCatTree((prev) => prev.concat(children.map((n: any) => ({
      id: String(n.id), pId: node.id, value: n.path, title: n.name, isLeaf: n.leaf }))));
  };
```
把原来的固定 `entry_value` Input：
```tsx
<Form.Item name="entry_value" rules={[{ required: true }]}><Input placeholder="关键词/类目URL/卖家ID" /></Form.Item>
```
替换为按入口类型条件渲染（category → TreeSelect, 其余 → Input）：
```tsx
<Form.Item noStyle shouldUpdate={(p, c) => p.entry_type !== c.entry_type}>
  {({ getFieldValue }) => getFieldValue("entry_type") === "category" ? (
    <Form.Item name="entry_value" rules={[{ required: true }]}>
      <TreeSelect treeDataSimpleMode style={{ width: 240 }} placeholder="浏览选择类目"
        treeData={catTree} loadData={onLoadCat} onFocus={loadRoots} allowClear />
    </Form.Item>
  ) : (
    <Form.Item name="entry_value" rules={[{ required: true }]}>
      <Input placeholder="关键词 / 卖家ID" />
    </Form.Item>
  )}
</Form.Item>
```
说明：`treeDataSimpleMode` 用扁平 `{id,pId,value,title,isLeaf}`；根节点 `pId:0`；选中把节点 `value=path` 写入 `entry_value`。类目树为 M6 mock，接 RealCategoryTree(live) 后自动变真实全量，前端无需改。

- [ ] **Step 5: 运行测试通过 + 前端回归 + 构建**

Run（从 `web/`）:
```bash
source ~/.nvm/nvm.sh && nvm use 20 >/dev/null && npx vitest run && npm run build
```
Expected: 全部通过 + build 成功。

- [ ] **Step 6: 提交**

```bash
git add web/src/pages/Tasks.tsx web/src/pages/Tasks.test.tsx
git commit -m "feat(m7): 建任务选类目入口时用 TreeSelect 浏览类目(复用 /categories)"
```

---

### Task 3: 生产部署包（nginx.prod.conf + docker-compose.prod.yml + certbot + .env.prod.example）

**Files:**
- Create: `deploy/nginx.prod.conf`
- Create: `docker-compose.prod.yml`
- Create: `deploy/certbot-init.sh`
- Create: `.env.prod.example`
- Test: `server/tests/test_prod_compose.py`

**Interfaces:** 纯部署配置 + 一个校验测试（合法 YAML + 内部端口不公开 + nginx 发布 443）。

- [ ] **Step 1: 写失败测试** `server/tests/test_prod_compose.py`

```python
import pathlib
import yaml

_ROOT = pathlib.Path(__file__).resolve().parents[2]   # ozon-listing-auto/


def test_prod_compose_is_valid_and_hardened():
    data = yaml.safe_load((_ROOT / "docker-compose.prod.yml").read_text())
    svcs = data["services"]
    # 内部服务不发布公网端口
    for name in ("db", "redis", "api", "worker"):
        assert name in svcs, f"缺少服务 {name}"
        assert "ports" not in svcs[name], f"{name} 不应对公网发布端口"
    # nginx 对外 80/443
    nginx_ports = " ".join(str(p) for p in svcs["nginx"]["ports"])
    assert "443" in nginx_ports and "80" in nginx_ports
    assert "certbot" in svcs, "缺少 certbot 服务"


def test_prod_deploy_files_exist():
    assert (_ROOT / "deploy" / "nginx.prod.conf").exists()
    assert (_ROOT / "deploy" / "certbot-init.sh").exists()
    assert (_ROOT / ".env.prod.example").exists()
    conf = (_ROOT / "deploy" / "nginx.prod.conf").read_text()
    assert "listen 443 ssl" in conf and "Strict-Transport-Security" in conf
    assert "/api/" in conf and "/ws/" in conf and "Upgrade" in conf
    assert "301 https" in conf                        # 80→443 强制跳转
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/python -m pytest tests/test_prod_compose.py -q`
Expected: FAIL（文件不存在）。若报 `ModuleNotFoundError: yaml`，先 `.venv/bin/pip install pyyaml` 并把 `pyyaml>=6.0` 加入 `pyproject.toml` 的 `[project.optional-dependencies].dev`。

- [ ] **Step 3: 建 `deploy/nginx.prod.conf`**（用官方 nginx 镜像 templates+envsubst，`${DOMAIN}` 为环境变量；`$host/$scheme/$http_upgrade` 等非环境变量不会被 envsubst 替换）

```nginx
# 生产 nginx：80 强制跳 443 + ACME 挑战；443 TLS 托管前端静态 + 反代 /api /ws。
# 作为 /etc/nginx/templates/default.conf.template 挂载，nginx 官方镜像启动时 envsubst 渲染 ${DOMAIN}。
server {
    listen 80;
    server_name ${DOMAIN};
    location /.well-known/acme-challenge/ { root /var/www/certbot; }
    location / { return 301 https://$host$request_uri; }
}

server {
    listen 443 ssl;
    server_name ${DOMAIN};

    ssl_certificate     /etc/letsencrypt/live/${DOMAIN}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/${DOMAIN}/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;

    add_header Strict-Transport-Security "max-age=63072000" always;
    add_header X-Content-Type-Options nosniff always;
    add_header X-Frame-Options SAMEORIGIN always;
    add_header Referrer-Policy strict-origin-when-cross-origin always;

    client_max_body_size 20m;

    location /api/ {
        proxy_pass http://api:8000/;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
    location /ws/ {
        proxy_pass http://api:8000/ws/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
    location / {
        root /usr/share/nginx/html;
        try_files $uri /index.html;
    }
}
```

- [ ] **Step 4: 建 `docker-compose.prod.yml`**

```yaml
# 生产栈：nginx 终结 TLS + 反代；db/redis/api/worker 不发布公网端口。
# 首次签证见 deploy/certbot-init.sh；证书由 certbot 容器自动续期。
services:
  db:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_USER: ${POSTGRES_USER:-ozon}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?set in .env.prod}
      POSTGRES_DB: ${POSTGRES_DB:-ozon}
    volumes: ["pgdata:/var/lib/postgresql/data"]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-ozon} -d ${POSTGRES_DB:-ozon}"]
      interval: 5s
      timeout: 3s
      retries: 10
    restart: unless-stopped
  redis:
    image: redis:7-alpine
    restart: unless-stopped
  api:
    build: ./server
    env_file: .env.prod
    restart: unless-stopped
    depends_on:
      db: { condition: service_healthy }
      redis: { condition: service_started }
    volumes: ["static:/app/static"]
  worker:
    build:
      context: ./server
      args:
        INSTALL_ML: "${INSTALL_ML:-false}"
    command: sh -c "arq app.workers.arq_worker.WorkerSettings"
    env_file: .env.prod
    restart: unless-stopped
    depends_on:
      db: { condition: service_healthy }
      redis: { condition: service_started }
    volumes: ["static:/app/static"]
  nginx:
    build: ./web
    environment:
      DOMAIN: ${DOMAIN:?set in .env.prod}
    ports: ["80:80", "443:443"]
    volumes:
      - ./deploy/nginx.prod.conf:/etc/nginx/templates/default.conf.template:ro
      - letsencrypt:/etc/letsencrypt
      - certbot-webroot:/var/www/certbot
    depends_on: [api]
    restart: unless-stopped
  certbot:
    image: certbot/certbot
    volumes:
      - letsencrypt:/etc/letsencrypt
      - certbot-webroot:/var/www/certbot
    entrypoint: /bin/sh -c 'trap exit TERM; while :; do certbot renew --webroot -w /var/www/certbot; sleep 12h & wait $${!}; done'
    restart: unless-stopped
volumes:
  pgdata:
  static:
  letsencrypt:
  certbot-webroot:
```

- [ ] **Step 5: 建 `deploy/certbot-init.sh`**

```bash
#!/usr/bin/env sh
# 首次签发 Let's Encrypt 证书（服务器上执行一次；域名须已解析到本机公网 IP）。
# 用法：DOMAIN=example.com CERTBOT_EMAIL=you@x.com sh deploy/certbot-init.sh
set -e
: "${DOMAIN:?需设置 DOMAIN}"
: "${CERTBOT_EMAIL:?需设置 CERTBOT_EMAIL}"

# 先起 nginx（提供 80 端口 ACME 挑战 webroot）
docker compose -f docker-compose.prod.yml up -d nginx

# webroot 方式签发
docker compose -f docker-compose.prod.yml run --rm --entrypoint certbot certbot \
  certonly --webroot -w /var/www/certbot \
  -d "$DOMAIN" --email "$CERTBOT_EMAIL" --agree-tos --no-eff-email

# 重载 nginx 以加载新证书
docker compose -f docker-compose.prod.yml exec nginx nginx -s reload
echo "证书签发完成。现在可 docker compose -f docker-compose.prod.yml up -d 起全栈。"
```

- [ ] **Step 6: 建 `.env.prod.example`**

```
# 生产环境变量样例。复制为 .env.prod 并按实际填写；切勿提交真实值。
# 域名（须解析到本机公网 IP）与证书邮箱
DOMAIN=example.com
CERTBOT_EMAIL=you@example.com

# 数据库（内网服务名 db，不对公网开放）
POSTGRES_USER=ozon
POSTGRES_PASSWORD=CHANGE_ME_strong_password
POSTGRES_DB=ozon
DATABASE_URL=postgresql+asyncpg://ozon:CHANGE_ME_strong_password@db:5432/ozon
REDIS_URL=redis://redis:6379/0

# 密钥（生产务必重新生成！）
# JWT_SECRET: 任意长随机串；FERNET_KEY: python -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())"
JWT_SECRET=CHANGE_ME_random_secret
FERNET_KEY=CHANGE_ME_generate_new_fernet_key

# CORS 收紧到你的域名（部署态经 nginx 同源, 此为纵深防御）
CORS_ORIGINS=["https://example.com"]

# provider 开关（默认全 mock；按需切真实并配相应凭据）
OZON_SELLER_PROVIDER=mock
LLM_PROVIDER=mock
EMBEDDER=mock
IMAGE_PROVIDER=mock
PROGRESS_BACKEND=memory
INSTALL_ML=false

# 管理员初始账号
ADMIN_USER=admin
ADMIN_PASSWORD=CHANGE_ME_admin_password
```

- [ ] **Step 7: 运行测试通过 + 回归**

Run: `.venv/bin/python -m pytest tests/test_prod_compose.py -q && .venv/bin/python -m pytest tests -q`
Expected: 全绿 0 warnings。

- [ ] **Step 8: 提交**

```bash
chmod +x deploy/certbot-init.sh
git add deploy/nginx.prod.conf docker-compose.prod.yml deploy/certbot-init.sh .env.prod.example server/tests/test_prod_compose.py pyproject.toml
git commit -m "feat(m7): 生产部署包 nginx.prod.conf+compose.prod(内部端口不公开)+certbot 签证/续期+.env.prod.example"
```

> 注：`CORS_ORIGINS` 为 JSON 数组字符串（pydantic-settings 解析 `list[str]`），故 `.env.prod.example` 写 `["https://example.com"]`。

---

### Task 4: 文档 + 本地 compose 整理 + 全量回归

**Files:**
- Modify: `README.md`（M7 章节：本地测试栈 + 生产部署 + 安全加固 + 环境变量）
- Create: `docs/部署与访问说明.md`
- Modify: `docker-compose.yml`（仅补注释标注为"本地测试栈"，不改结构/端口）
- Test: 全量后端 + 前端回归

- [ ] **Step 1: 读现有** `README.md`（定位 M6 段落、环境变量表、快速开始）与 `docker-compose.yml`。

- [ ] **Step 2: 更新 `README.md`** —— 加 M7 到功能/里程碑，新增「部署」小节：本地测试栈（`docker compose up` → 浏览器 `http://localhost:8080`）与生产栈（见《部署与访问说明》）；环境变量表补 `CORS_ORIGINS`、`login_*`、`DOMAIN`/`CERTBOT_EMAIL`；说明 CORS 默认 `["*"]`（dev）、生产收紧。保持精简、与代码一致。

- [ ] **Step 3: 建 `docs/部署与访问说明.md`** —— runbook：
  1. **本地测试**：`docker compose up -d` → 浏览器 `http://localhost:8080` 登录（admin/admin123）→ 全流程验证（建任务→采集→匹配→评分→审核→定价→上架→监控；自建含改图/类目）。
  2. **服务器准备**：装 Docker/Compose；域名 A 记录解析到公网 IP；放行 80/443。
  3. **首次签证**：复制 `.env.prod.example`→`.env.prod` 填 `DOMAIN`/`CERTBOT_EMAIL`/密钥/`CORS_ORIGINS`；执行 `DOMAIN=… CERTBOT_EMAIL=… sh deploy/certbot-init.sh`。
  4. **起全栈**：`docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build`；浏览器 `https://域名`。
  5. **安全加固清单**：强制 HTTPS/HSTS（nginx）、内部端口不公开、登录失败限流（5 次锁 15 分钟）、CORS 收紧、密钥已重生成、（可选）云安全组仅放 80/443/SSH。
  6. **更新方式**：`git pull` → `docker compose -f docker-compose.prod.yml up -d --build`，员工刷新浏览器即最新。
  7. **证书续期/排查**：certbot 容器自动 `renew`；查 `docker compose -f docker-compose.prod.yml logs certbot`；续期后 `nginx -s reload`。
  8. **已知 live 后置项**：RealOzonSeller/RealCategoryTree/外部生图/真实爬虫 cookie·代理；多 api 实例限流需 Redis 后端。

- [ ] **Step 4: 改 `docker-compose.yml`** —— 顶部加一行注释标注「本地测试/开发栈（HTTP）：上服务器前用它全流程验证；生产用 docker-compose.prod.yml」。不改服务/端口结构。

- [ ] **Step 5: 全量回归**

Run:
```bash
cd server && .venv/bin/python -m pytest tests -q
cd ../web && source ~/.nvm/nvm.sh && nvm use 20 >/dev/null && npx vitest run && npm run build
```
Expected: 后端全绿 0 warnings；前端测试通过 + build 成功。

- [ ] **Step 6: 提交**

```bash
git add README.md docs/部署与访问说明.md docker-compose.yml
git commit -m "docs(m7): README + 部署与访问说明 + 本地测试栈标注"
```

---

## Self-Review（写计划后自检）

- **Spec 覆盖**：§2 生产部署包→Task 3；§3.1 CORS→Task 1；§3.2 登录限流→Task 1；§3.3 内部端口/nginx→Task 3；§4 类目树浏览→Task 2；§5 测试贯穿；§6 验收→全量；§1 本地测试栈→Task 3/4。OpenClaw 已剔除（不在任何任务）。全覆盖。
- **占位符扫描**：无 TBD/TODO 式空步骤；后端/配置步骤含完整代码；前端 Task 2 与文档 Task 4 以「结构 + 关键调用/要点」给出并要求先读现有范式（既有里程碑一致做法）。
- **类型/名称一致**：`LoginThrottle.check/record_failure/reset/clear` 在 Task 1 定义并在测试/auth 使用一致；模块单例 `login_throttle`；`login_max_attempts/window_sec/lockout_sec` config 名一致；`docker-compose.prod.yml` 服务名 `nginx`（Task 3 建、测试断言一致）；`getCategories(parentId?)` Task 2 复用 M6 既有签名。
- **已知落地注意**：登录限流为模块单例，测试须 `clear()` 首尾隔离（Task 1 已写明）；`CORS_ORIGINS` 为 JSON 数组字符串（Task 3 .env 已注明）；nginx `${DOMAIN}` 走官方镜像 templates+envsubst，nginx 运行时变量 `$host` 等非环境变量不被替换（Task 3 已注明）；`yaml` 若缺则加 dev 依赖（Task 3 Step 2 已写明）。

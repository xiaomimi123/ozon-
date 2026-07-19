# 子项 C 外部生图接入 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`).

**Goal:** 外部生图从 mock 切真实（文生图）：`OpenAICompatImageProvider`(标准 OpenAI images) + `HttpImageProvider`(可配字段映射) + `/settings/imagegen` 扩展 + `get_configured_gen_provider` + 接线；用户后配服务/key。

**Architecture:** 两 provider 真实实现 + 共享 `save_image_bytes`；`process_op`/imager 读 `/settings/imagegen` 配置选 gen provider（sync 仍 mock）；gen 保持 opt-in。

**Tech Stack:** FastAPI / httpx(MockTransport) / React+AntD / pytest / Vitest。

## Global Constraints

- Python 3.11；`.venv/bin/python -m pytest`（从 `server/`）。不用系统 python3。
- **pytest 0 warnings**；非 live 全 mock（httpx.MockTransport，无真实网络）；真实生图 `@pytest.mark.live` 默认跳过。
- api_key Fernet 脱敏/留空不覆盖（现状）；新字段 request_template/response_path 非 secret。
- sync `/images/process` 恒 mock（gen_provider_obj=None → mock）。
- 角色门：/settings/imagegen → admin（现状）。

---

### Task 1: 共享 save_image_bytes + OpenAICompatImageProvider

**Files:**
- Create: `app/services/imagegen/save.py`
- Modify: `app/services/imagegen/openai_compat.py`（实现 process）
- Test: `tests/test_imagegen_openai.py`

**Interfaces:**
- Produces: `save_image_bytes(raw: bytes, static_dir: str, *, prefix="gen") -> str`；`OpenAICompatImageProvider(base_url, api_key, model, static_dir=DEFAULT_STATIC_DIR, timeout=30.0, transport=None)` with `process(*, image, op, params) -> ImageResult`。

- [ ] **Step 1: 写失败测试** `tests/test_imagegen_openai.py`
```python
import base64, io, pytest, httpx
from PIL import Image
from app.services.imagegen.openai_compat import OpenAICompatImageProvider


def _png_bytes():
    b = io.BytesIO(); Image.new("RGB", (8, 8), (1, 2, 3)).save(b, format="PNG"); return b.getvalue()


@pytest.mark.asyncio
async def test_openai_gen_url_response(tmp_path):
    png = _png_bytes()
    def handler(req):
        if req.url.path.endswith("/images/generations"):
            return httpx.Response(200, json={"data": [{"url": "https://img.test/x.png"}]})
        return httpx.Response(200, content=png)   # 图片下载
    prov = OpenAICompatImageProvider("https://api.test/v1", "sk-x", "wanx", static_dir=str(tmp_path),
                                     transport=httpx.MockTransport(handler))
    res = await prov.process(image=b"", op="gen", params={"prompt": "蓝色童鞋 电商主图"})
    assert res.provider == "openai_compat" and res.url.startswith("/static/images/")
    import os
    assert os.path.exists(os.path.join(str(tmp_path), res.url.split("/")[-1]))


@pytest.mark.asyncio
async def test_openai_gen_b64_response(tmp_path):
    b64 = base64.b64encode(_png_bytes()).decode()
    def handler(req):
        return httpx.Response(200, json={"data": [{"b64_json": b64}]})
    prov = OpenAICompatImageProvider("https://api.test/v1", "sk-x", "wanx", static_dir=str(tmp_path),
                                     transport=httpx.MockTransport(handler))
    res = await prov.process(image=b"", op="gen", params={"prompt": "x"})
    assert res.url.startswith("/static/images/")


@pytest.mark.asyncio
async def test_openai_gen_error_raises(tmp_path):
    def handler(req): return httpx.Response(500)
    prov = OpenAICompatImageProvider("https://api.test/v1", "sk-x", "wanx", static_dir=str(tmp_path),
                                     transport=httpx.MockTransport(handler))
    with pytest.raises(Exception):
        await prov.process(image=b"", op="gen", params={"prompt": "x"})
```

- [ ] **Step 2: 运行确认失败** `.venv/bin/python -m pytest tests/test_imagegen_openai.py -q` → FAIL（NotImplementedError / save 不存在）

- [ ] **Step 3: 建 `app/services/imagegen/save.py`**
```python
"""外部生图产物落盘：字节 → static_dir，内容 hash 命名（确定性），返回 /static/images/ 相对 URL。"""
import hashlib
import os


def save_image_bytes(raw: bytes, static_dir: str, *, prefix: str = "gen") -> str:
    os.makedirs(static_dir, exist_ok=True)
    h = hashlib.sha1(raw).hexdigest()[:12]
    fname = f"{prefix}_{h}.png"
    with open(os.path.join(static_dir, fname), "wb") as f:
        f.write(raw)
    return f"/static/images/{fname}"
```

- [ ] **Step 4: 改 `app/services/imagegen/openai_compat.py`**（整体替换）
```python
"""OpenAICompatImageProvider：标准 OpenAI 图像接口(images/generations)文生图。默认适配千问万相等 OpenAI 兼容端点。"""
import base64
import httpx
from app.services.imagegen.base import ImageResult
from app.services.imagegen.save import save_image_bytes
from app.services.imagegen.factory import DEFAULT_STATIC_DIR


class OpenAICompatImageProvider:
    name = "openai_compat"

    def __init__(self, base_url: str, api_key: str, model: str,
                 static_dir: str = DEFAULT_STATIC_DIR, timeout: float = 30.0, transport=None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.static_dir = static_dir
        self.timeout = timeout
        self.transport = transport

    def _client(self) -> httpx.AsyncClient:
        kw = {"timeout": self.timeout}
        if self.transport is not None:
            kw["transport"] = self.transport
        return httpx.AsyncClient(**kw)

    async def process(self, *, image: bytes, op: str, params: dict) -> ImageResult:
        prompt = params.get("prompt") or ""
        body = {"model": self.model, "prompt": prompt, "n": 1,
                "size": params.get("size", "1024x1024"), "response_format": "url"}
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        last = None
        for _ in range(3):
            try:
                async with self._client() as c:
                    r = await c.post(f"{self.base_url}/images/generations", json=body, headers=headers)
                    r.raise_for_status()
                    item = (r.json().get("data") or [{}])[0]
                    if item.get("url"):
                        ir = await c.get(item["url"])
                        ir.raise_for_status()
                        raw = ir.content
                    elif item.get("b64_json"):
                        raw = base64.b64decode(item["b64_json"])
                    else:
                        raise RuntimeError("生图响应缺 url/b64_json")
                url = save_image_bytes(raw, self.static_dir)
                return ImageResult(url=url, provider="openai_compat", meta={"op": "gen", "model": self.model})
            except Exception as exc:  # noqa: BLE001  重试；耗尽抛
                last = exc
        raise RuntimeError(f"OpenAICompat 生图失败: {last}")
```

- [ ] **Step 5: 运行测试通过 + 回归** `.venv/bin/python -m pytest tests/test_imagegen_openai.py -q && .venv/bin/python -m pytest tests -q` → 全绿 0 warnings。

- [ ] **Step 6: 提交**
```bash
git add app/services/imagegen/save.py app/services/imagegen/openai_compat.py tests/test_imagegen_openai.py
git commit -m "feat(imagegen): OpenAICompatImageProvider(标准 images/generations 文生图)+共享 save_image_bytes"
```

---

### Task 2: HttpImageProvider（可配请求模板 + 响应路径）

**Files:**
- Modify: `app/services/imagegen/http.py`（实现 process）
- Test: `tests/test_imagegen_http.py`

**Interfaces:**
- Produces: `HttpImageProvider(base_url, api_key, model, request_template, response_path, static_dir=DEFAULT_STATIC_DIR, timeout=30.0, transport=None)` with `process(*, image, op, params) -> ImageResult`。

- [ ] **Step 1: 写失败测试** `tests/test_imagegen_http.py`
```python
import base64, io, json, pytest, httpx
from PIL import Image
from app.services.imagegen.http import HttpImageProvider


def _png(): b = io.BytesIO(); Image.new("RGB", (8, 8), (9, 9, 9)).save(b, format="PNG"); return b.getvalue()


@pytest.mark.asyncio
async def test_http_gen_url_path(tmp_path):
    png = _png()
    def handler(req):
        if req.url.host == "gen.test":
            body = json.loads(req.content)
            assert body["prompt"] == "电商主图" and body["model"] == "m1"   # 模板替换生效
            return httpx.Response(200, json={"output": {"image_url": "https://cdn.test/y.png"}})
        return httpx.Response(200, content=png)
    prov = HttpImageProvider("https://gen.test/api", "k", "m1",
                             request_template='{"prompt":"{prompt}","model":"{model}"}',
                             response_path="output.image_url", static_dir=str(tmp_path),
                             transport=httpx.MockTransport(handler))
    res = await prov.process(image=b"", op="gen", params={"prompt": "电商主图"})
    assert res.provider == "http" and res.url.startswith("/static/images/")


@pytest.mark.asyncio
async def test_http_gen_b64_path(tmp_path):
    b64 = base64.b64encode(_png()).decode()
    def handler(req):
        return httpx.Response(200, json={"data": [{"b64": b64}]})
    prov = HttpImageProvider("https://gen.test/api", "k", "m1",
                             request_template='{"prompt":"{prompt}"}',
                             response_path="data.0.b64", static_dir=str(tmp_path),
                             transport=httpx.MockTransport(handler))
    res = await prov.process(image=b"", op="gen", params={"prompt": "x"})
    assert res.url.startswith("/static/images/")


@pytest.mark.asyncio
async def test_http_missing_path_raises(tmp_path):
    def handler(req): return httpx.Response(200, json={"nope": 1})
    prov = HttpImageProvider("https://gen.test/api", "", "m", '{"p":"{prompt}"}', "output.image_url",
                             static_dir=str(tmp_path), transport=httpx.MockTransport(handler))
    with pytest.raises(Exception):
        await prov.process(image=b"", op="gen", params={"prompt": "x"})
```

- [ ] **Step 2: 运行确认失败** → FAIL（NotImplementedError）

- [ ] **Step 3: 改 `app/services/imagegen/http.py`**（整体替换）
```python
"""HttpImageProvider：通用 HTTP 生图适配器。请求体模板({prompt}/{model} 占位)+响应取图路径(点路径)可配，接非 OpenAI 格式服务。"""
import base64
import json
import httpx
from app.services.imagegen.base import ImageResult
from app.services.imagegen.save import save_image_bytes
from app.services.imagegen.factory import DEFAULT_STATIC_DIR


def _dig(obj, path: str):
    """点路径提取：'data.0.url' → obj['data'][0]['url']；缺失返回 None。"""
    cur = obj
    for part in path.split("."):
        if isinstance(cur, list):
            try:
                cur = cur[int(part)]
            except (ValueError, IndexError):
                return None
        elif isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
        if cur is None:
            return None
    return cur


class HttpImageProvider:
    name = "http"

    def __init__(self, base_url: str, api_key: str, model: str, request_template: str, response_path: str,
                 static_dir: str = DEFAULT_STATIC_DIR, timeout: float = 30.0, transport=None):
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self.request_template = request_template
        self.response_path = response_path
        self.static_dir = static_dir
        self.timeout = timeout
        self.transport = transport

    def _client(self):
        kw = {"timeout": self.timeout}
        if self.transport is not None:
            kw["transport"] = self.transport
        return httpx.AsyncClient(**kw)

    async def process(self, *, image: bytes, op: str, params: dict) -> ImageResult:
        prompt = params.get("prompt") or ""
        # 模板占位替换（JSON 安全：用 json.dumps 转义后去掉外层引号）
        body_str = (self.request_template
                    .replace("{prompt}", json.dumps(prompt)[1:-1])
                    .replace("{model}", json.dumps(self.model)[1:-1]))
        body = json.loads(body_str)
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        async with self._client() as c:
            r = await c.post(self.base_url, json=body, headers=headers)
            r.raise_for_status()
            val = _dig(r.json(), self.response_path)
            if not val:
                raise RuntimeError(f"生图响应按路径 {self.response_path} 取图为空")
            if isinstance(val, str) and val.startswith("http"):
                ir = await c.get(val)
                ir.raise_for_status()
                raw = ir.content
            else:
                raw = base64.b64decode(val)
        url = save_image_bytes(raw, self.static_dir)
        return ImageResult(url=url, provider="http", meta={"op": "gen", "path": self.response_path})
```

- [ ] **Step 4: 运行测试通过 + 回归** → 全绿 0 warnings。

- [ ] **Step 5: 提交**
```bash
git add app/services/imagegen/http.py tests/test_imagegen_http.py
git commit -m "feat(imagegen): HttpImageProvider(可配请求模板+响应点路径, 接任意 HTTP 生图服务)"
```

---

### Task 3: 配置扩展 + get_configured_gen_provider + process_op/imager 接线

**Files:**
- Modify: `app/schemas/imagegen.py`（加 img_request_template/img_response_path）
- Modify: `app/api/imagegen.py`（read/write 带上）
- Create: `app/services/imagegen/config.py`（get_configured_gen_provider）
- Modify: `app/services/imagegen/factory.py`（process_op 加 gen_provider_obj）
- Modify: `app/workers/imager.py`（run_image_process_core 加 gen_provider_obj 透传；run_image_process 读配置）
- Test: `tests/test_imagegen_config.py`

**Interfaces:**
- Produces: `/settings/imagegen` 增 img_request_template/img_response_path；`async def get_configured_gen_provider(session, *, static_dir) -> ImageProvider`；`process_op(..., gen_provider_obj=None)`；`run_image_process_core(..., gen_provider_obj=None)`。

- [ ] **Step 1: 写失败测试** `tests/test_imagegen_config.py`
```python
import pytest
from app.core.security import hash_password
from app.models import User


async def _admin(client, db_session):
    db_session.add(User(username="a", password_hash=hash_password("p"), role="admin"))
    await db_session.commit()
    tok = (await client.post("/auth/login", data={"username": "a", "password": "p"})).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


@pytest.mark.asyncio
async def test_imagegen_settings_new_fields(client, db_session):
    h = await _admin(client, db_session)
    await client.put("/settings/imagegen", headers=h, json={
        "provider": "http", "img_base_url": "https://g/api", "img_api_key": "k", "img_model": "m",
        "fallback": "", "img_request_template": '{"p":"{prompt}"}', "img_response_path": "data.0.url"})
    g = (await client.get("/settings/imagegen", headers=h)).json()
    assert g["provider"] == "http" and g["img_request_template"] == '{"p":"{prompt}"}'
    assert g["img_response_path"] == "data.0.url" and g["img_api_key"] in ("***", None)


@pytest.mark.asyncio
async def test_get_configured_gen_provider(db_session, tmp_path):
    from app.services.imagegen.config import get_configured_gen_provider
    from app.services.imagegen.mock import MockImageProvider
    # 无配置 → mock
    assert isinstance(await get_configured_gen_provider(db_session, static_dir=str(tmp_path)), MockImageProvider)
    from app.services.settings_store import set_value
    await set_value(db_session, "imagegen", "provider", "openai_compat", is_secret=False)
    await set_value(db_session, "imagegen", "img_base_url", "https://a/v1", is_secret=False)
    await set_value(db_session, "imagegen", "img_api_key", "sk", is_secret=True)
    await set_value(db_session, "imagegen", "img_model", "wanx", is_secret=False)
    await db_session.commit()
    from app.services.imagegen.openai_compat import OpenAICompatImageProvider
    prov = await get_configured_gen_provider(db_session, static_dir=str(tmp_path))
    assert isinstance(prov, OpenAICompatImageProvider) and prov.model == "wanx"


@pytest.mark.asyncio
async def test_process_op_uses_gen_provider_obj(tmp_path):
    from app.services.imagegen.factory import process_op
    from app.services.imagegen.mock import MockImageProvider
    res = await process_op("gen", image=b"x", params={}, static_dir=str(tmp_path),
                           gen_provider_obj=MockImageProvider())
    assert res.provider == "mock"
```

- [ ] **Step 2: 运行确认失败** → FAIL

- [ ] **Step 3: 改 `app/schemas/imagegen.py`** —— 两类各加两字段：
```python
class ImagegenIn(BaseModel):
    provider: str = "mock"
    img_base_url: str = ""
    img_api_key: str = ""
    img_model: str = ""
    fallback: str = ""
    img_request_template: str = ""
    img_response_path: str = ""

class ImagegenOut(BaseModel):
    provider: str = "mock"
    img_base_url: str = ""
    img_api_key: str | None = None
    img_model: str = ""
    fallback: str = ""
    img_request_template: str = ""
    img_response_path: str = ""
```

- [ ] **Step 4: 改 `app/api/imagegen.py`** —— read 返回加两字段；write 加两次 `set_value`（非 secret），返回带上。读现有文件，在 GET 的 ImagegenOut 构造加 `img_request_template=masked.get("img_request_template",""), img_response_path=masked.get("img_response_path","")`；PUT 加 `await store.set_value(s,_CAT,"img_request_template",body.img_request_template,is_secret=False,updated_by=u.id)` 与 img_response_path 同理，返回的 ImagegenOut 带上两字段。（api_key 留空不覆盖逻辑不变。）

- [ ] **Step 5: 建 `app/services/imagegen/config.py`**
```python
"""按 /settings/imagegen 配置构造 gen ImageProvider：openai_compat/http 真实, 否则 mock；无 key/无配回退 mock。"""
from app.services.settings_store import get_category
from app.services.imagegen.mock import MockImageProvider


async def get_configured_gen_provider(session, *, static_dir):
    conf = await get_category(session, "imagegen")
    provider = conf.get("provider", "mock")
    key = conf.get("img_api_key") or ""
    base = conf.get("img_base_url") or ""
    model = conf.get("img_model") or ""
    if provider == "openai_compat" and key and base:
        from app.services.imagegen.openai_compat import OpenAICompatImageProvider
        return OpenAICompatImageProvider(base, key, model, static_dir=static_dir)
    if provider == "http" and base and conf.get("img_request_template") and conf.get("img_response_path"):
        from app.services.imagegen.http import HttpImageProvider
        return HttpImageProvider(base, key, model, conf["img_request_template"], conf["img_response_path"],
                                 static_dir=static_dir)
    return MockImageProvider()
```

- [ ] **Step 6: 改 `app/services/imagegen/factory.py`** —— process_op 加 gen_provider_obj：
```python
async def process_op(op: str, *, image: bytes, params: dict, static_dir: str = DEFAULT_STATIC_DIR,
                     gen_provider: str = "mock", gen_provider_obj=None) -> ImageResult:
    if op in LOCAL_OPS:
        return await LocalProvider(static_dir).process(image=image, op=op, params=params)
    if op in GEN_OPS:
        prov = gen_provider_obj or get_image_provider(gen_provider, static_dir=static_dir)
        return await prov.process(image=image, op=op, params=params)
    raise ValueError(f"未知 op: {op}")
```

- [ ] **Step 7: 改 `app/workers/imager.py`** —— run_image_process_core 加 gen_provider_obj 透传；run_image_process 读配置构造。
`run_image_process_core(..., gen_provider="mock", gen_provider_obj=None, fetch=None)`；`process_op(op, image=img_bytes, params={}, static_dir=static_dir, gen_provider=gen_provider, gen_provider_obj=gen_provider_obj)`。
`run_image_process`（ARQ）：
```python
async def run_image_process(ctx, task_id: int) -> dict:
    from app.core.db import async_session
    from app.services.imagegen.factory import DEFAULT_STATIC_DIR
    from app.services.imagegen.config import get_configured_gen_provider
    async with async_session() as s:
        gen_obj = await get_configured_gen_provider(s, static_dir=DEFAULT_STATIC_DIR)
    return await run_image_process_core(async_session, task_id, gen_provider_obj=gen_obj)
```
（sync `/images/process` API 走 run_image_process_core 不传 gen_provider_obj → mock，不变。）

- [ ] **Step 8: 运行测试通过 + 回归** `.venv/bin/python -m pytest tests/test_imagegen_config.py -q && .venv/bin/python -m pytest tests -q` → 全绿 0 warnings。

- [ ] **Step 9: 提交**
```bash
git add app/schemas/imagegen.py app/api/imagegen.py app/services/imagegen/config.py app/services/imagegen/factory.py app/workers/imager.py tests/test_imagegen_config.py
git commit -m "feat(imagegen): /settings/imagegen 扩展 http 映射 + get_configured_gen_provider + process_op/imager 接线"
```

---

### Task 4: 前端 ImagegenSettings 扩展 + @live + 文档 + 回归

**Files:**
- Modify: `web/src/pages/settings/ImagegenSettings.tsx`（加 request_template/response_path 字段）
- Modify: `web/src/pages/settings/ImagegenSettings.test.tsx`（若断言字段）
- Create: `server/tests/test_live_imagegen.py`（@live）
- Modify: `README.md`、`docs/去mock化-真实集成总规划.md`（标 C 完成）
- Test: 全量回归

- [ ] **Step 1: 读现有** `web/src/pages/settings/ImagegenSettings.tsx` + 其 test + `web/src/api/imagegen.ts`。

- [ ] **Step 2: 改 ImagegenSettings.tsx** —— 加 `img_request_template`（Input.TextArea）+ `img_response_path`（Input）字段，随现有表单一同 putImagegen；提示"仅 http provider 用：请求体 JSON 模板(含 {prompt}/{model}) + 响应取图点路径(如 data.0.url)"。（可选：仅当 provider=http 时显示，用 shouldUpdate；不做也可，字段常显但注明 http 用。）

- [ ] **Step 3: 建 `server/tests/test_live_imagegen.py`**（@live 默认跳过）
```python
"""真实生图冒烟(@live 默认跳过)。先在 /settings/imagegen 配好, 或设 IMG_BASE_URL/IMG_API_KEY/IMG_MODEL 后:
  IMG_API_KEY=... .venv/bin/python -m pytest tests/test_live_imagegen.py -m live -v"""
import os, pytest


@pytest.mark.live
@pytest.mark.asyncio
async def test_live_openai_gen(tmp_path):
    key = os.environ.get("IMG_API_KEY")
    if not key:
        pytest.skip("需设置 IMG_API_KEY")
    from app.services.imagegen.openai_compat import OpenAICompatImageProvider
    prov = OpenAICompatImageProvider(os.environ.get("IMG_BASE_URL", ""), key,
                                     os.environ.get("IMG_MODEL", "wanx-v1"), static_dir=str(tmp_path))
    res = await prov.process(image=b"", op="gen", params={"prompt": "电商风格 蓝色童鞋 白底主图"})
    assert res.url.startswith("/static/images/")
```

- [ ] **Step 4: 文档** —— README 加「外部生图」小节（/settings/imagegen 配 openai_compat 或 http；http 配 request_template/response_path；gen opt-in；@live 跑法）；总规划标 C 完成。

- [ ] **Step 5: 全量回归**
```bash
cd server && .venv/bin/python -m pytest tests -q
cd ../web && source ~/.nvm/nvm.sh && nvm use 20 >/dev/null && npx vitest run && npm run build
```
Expected: 后端全绿 0 warnings（live +1 deselected）；前端通过 + build。

- [ ] **Step 6: 提交**
```bash
git add web/src/pages/settings/ImagegenSettings.tsx server/tests/test_live_imagegen.py README.md docs/去mock化-真实集成总规划.md
git commit -m "feat(imagegen): 前端 http 映射字段 + @live 生图冒烟 + README/总规划标 C 完成"
```

---

## Self-Review

- **Spec 覆盖**：§2.1 save_image_bytes→Task 1；§2.2 OpenAICompat→Task 1；§2.3 Http→Task 2；§2.4 配置+get_configured_gen_provider→Task 3；§2.5 接线→Task 3；§3 测试贯穿；前端+@live→Task 4。全覆盖。
- **占位符扫描**：无 TBD；后端含完整代码；前端 Task 4 以结构给出并要求先读现有 ImagegenSettings。
- **名称一致**：`save_image_bytes`(Task 1 定义、Task 2 复用)；`OpenAICompatImageProvider(base_url,api_key,model,static_dir,timeout,transport)`；`HttpImageProvider(...request_template,response_path...)`；`get_configured_gen_provider(session,*,static_dir)`(Task 3 定义、imager 用)；`process_op(...,gen_provider_obj=None)`；`img_request_template/img_response_path`(schema/api/前端/config 一致)。
- **落地注意**：openai_compat/http 从 factory import DEFAULT_STATIC_DIR（避免循环 import：factory 顶部已 import 这两个 provider？—— factory 是惰性 import provider，provider import factory 的常量。确认无循环：factory 模块级 import mock/local，provider 惰性被 factory import；provider 顶部 import factory 只取常量 DEFAULT_STATIC_DIR，factory 顶部不 import openai_compat/http（惰性），故无循环）。测试用 httpx.MockTransport（handler 需同时应答生成 POST 与图片 GET）。sync /images/process 仍 mock（不传 gen_provider_obj）。

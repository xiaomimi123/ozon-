# 子项 A 真实 LLM 接入 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** LLM 从 mock 切真实（默认通义千问，OpenAI 兼容），凭据走 `/settings/llm` 配置页；评分 worker/类目建议/自建译标题走真实 LLM，sync=true 批量路径仍 mock。

**Architecture:** 复用 `OpenAICompatLLM`(已完整) + 配置中心(Fernet)。新增 `/settings/llm` 页 + `get_configured_llm(session)`(读配置→openai 有 key 则真实, 否则 mock, 回退 env)，替换三处 `get_llm` 调用。

**Tech Stack:** FastAPI / settings_store(Fernet) / React+Ant Design / Vitest / pytest。

## Global Constraints

- Python 3.11；`.venv/bin/python -m pytest`（从 `server/`）。不用系统 python3。
- **pytest 0 warnings**；非 live 全 mock；真实调用 `@pytest.mark.live`（默认跳过）。
- api_key Fernet 加密、GET 脱敏 `***`、PUT 留空不覆盖（同 imagegen）。
- `/settings/llm` 路由**须先于** `/settings/{category}` 注册。
- 角色门：`/settings/llm` → admin。
- sync=true 批量路径（`/score?sync=true`）保持 mock，不改。

---

### Task 1: 后端 —— /settings/llm + get_configured_llm + 接线

**Files:**
- Create: `app/schemas/llm.py`, `app/api/llm.py`, `app/services/llm/config.py`
- Modify: `app/main.py`（注册 llm_router，先于 settings_router）
- Modify: `app/workers/scorer.py`、`app/api/category.py`、`app/api/listing.py`（接线）
- Test: `tests/test_llm_config.py`

**Interfaces:**
- Produces: `GET/PUT /settings/llm`；`async def get_configured_llm(session) -> LLMProvider`。

- [ ] **Step 1: 写失败测试** `tests/test_llm_config.py`

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
async def test_llm_settings_mask_and_keep_blank(client, db_session):
    h = await _admin(client, db_session)
    await client.put("/settings/llm", headers=h, json={
        "llm_provider": "openai", "llm_base_url": "https://x/v1", "llm_api_key": "sk-secret", "llm_model": "qwen-plus"})
    g = (await client.get("/settings/llm", headers=h)).json()
    assert g["llm_api_key"] in ("***", None) and "sk-secret" not in str(g)
    assert g["llm_provider"] == "openai" and g["llm_model"] == "qwen-plus"
    # 留空不覆盖 api_key
    await client.put("/settings/llm", headers=h, json={
        "llm_provider": "openai", "llm_base_url": "https://y/v1", "llm_api_key": "", "llm_model": "qwen-max"})
    from app.services.settings_store import get_value
    assert await get_value(db_session, "llm", "llm_api_key") == "sk-secret"     # 密钥保留
    from app.services.settings_store import get_category
    assert (await get_category(db_session, "llm"))["llm_base_url"] == "https://y/v1"  # 其他字段更新


@pytest.mark.asyncio
async def test_get_configured_llm_selects_by_config(db_session, monkeypatch):
    from app.services.llm.config import get_configured_llm
    from app.services.llm.mock import MockLLM
    from app.services.llm.openai_compat import OpenAICompatLLM
    # 无配置 → 回退 env（默认 mock）
    llm = await get_configured_llm(db_session)
    assert isinstance(llm, MockLLM)
    # 配 openai + key → 真实
    from app.services.settings_store import set_value
    await set_value(db_session, "llm", "llm_provider", "openai", is_secret=False)
    await set_value(db_session, "llm", "llm_api_key", "sk-x", is_secret=True)
    await set_value(db_session, "llm", "llm_base_url", "https://x/v1", is_secret=False)
    await set_value(db_session, "llm", "llm_model", "qwen-plus", is_secret=False)
    await db_session.commit()
    llm2 = await get_configured_llm(db_session)
    assert isinstance(llm2, OpenAICompatLLM) and llm2.model == "qwen-plus"
    # openai 但无 key → 回退 mock
    await set_value(db_session, "llm", "llm_api_key", "", is_secret=True)   # 覆盖为空
    await db_session.commit()
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/python -m pytest tests/test_llm_config.py -q`
Expected: FAIL（路由/模块不存在）

- [ ] **Step 3: 建 `app/schemas/llm.py`**

```python
from pydantic import BaseModel

class LlmIn(BaseModel):
    llm_provider: str = "mock"      # mock | openai
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""

class LlmOut(BaseModel):
    llm_provider: str = "mock"
    llm_base_url: str = ""
    llm_api_key: str | None = None   # 脱敏
    llm_model: str = ""
```

- [ ] **Step 4: 建 `app/api/llm.py`**（仿 imagegen；api_key 留空不覆盖）

```python
"""LLM provider 配置 API(admin)：provider/base_url/api_key/model，Fernet 加密脱敏、留空不覆盖。"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.db import get_session
from app.api.deps import require_role
from app.models import User
from app.schemas.llm import LlmIn, LlmOut
from app.services import settings_store as store

router = APIRouter(prefix="/settings/llm", tags=["settings"])
_CAT = "llm"


@router.get("", response_model=LlmOut)
async def read(s: AsyncSession = Depends(get_session), _: User = Depends(require_role("admin"))):
    m = await store.get_category_masked(s, _CAT)
    return LlmOut(llm_provider=m.get("llm_provider", "mock"), llm_base_url=m.get("llm_base_url", ""),
                  llm_api_key=m.get("llm_api_key"), llm_model=m.get("llm_model", ""))


@router.put("", response_model=LlmOut)
async def write(body: LlmIn, s: AsyncSession = Depends(get_session), u: User = Depends(require_role("admin"))):
    await store.set_value(s, _CAT, "llm_provider", body.llm_provider, is_secret=False, updated_by=u.id)
    await store.set_value(s, _CAT, "llm_base_url", body.llm_base_url, is_secret=False, updated_by=u.id)
    if body.llm_api_key:
        await store.set_value(s, _CAT, "llm_api_key", body.llm_api_key, is_secret=True, updated_by=u.id)
    await store.set_value(s, _CAT, "llm_model", body.llm_model, is_secret=False, updated_by=u.id)
    await s.commit()
    return LlmOut(llm_provider=body.llm_provider, llm_base_url=body.llm_base_url,
                  llm_api_key="***" if body.llm_api_key else None, llm_model=body.llm_model)
```

- [ ] **Step 5: 建 `app/services/llm/config.py`**

```python
"""按 /settings/llm 配置构造 LLMProvider：openai 有 key 则真实, 否则 mock；配置空回退 env。"""
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.services.settings_store import get_category
from app.services.llm.factory import get_llm


async def get_configured_llm(session: AsyncSession):
    conf = await get_category(session, "llm")
    provider = conf.get("llm_provider") or settings.llm_provider
    if provider == "openai":
        base = conf.get("llm_base_url") or settings.llm_base_url
        key = conf.get("llm_api_key") or settings.llm_api_key
        model = conf.get("llm_model") or settings.llm_model
        if key:
            from app.services.llm.openai_compat import OpenAICompatLLM
            return OpenAICompatLLM(base, key, model)
    return get_llm("mock")
```

- [ ] **Step 6: 改 `app/main.py`** —— 注册 llm_router，放在 imagegen/crawler/system 一组、`settings_router` 之前。
import 区加 `from app.api.llm import router as llm_router`；在 `app.include_router(system_router)` 后、`settings_router` 前加 `app.include_router(llm_router)`。

- [ ] **Step 7: 接线三处**
- `app/workers/scorer.py` 的 `run_score`：把
  ```python
      return await run_score_core(async_session, task_id,
                                  embedder=get_embedder(settings.embedder),
                                  llm=get_llm(settings.llm_provider))
  ```
  改为（用配置驱动 llm）：
  ```python
      from app.services.llm.config import get_configured_llm
      async with async_session() as s:
          llm = await get_configured_llm(s)
      return await run_score_core(async_session, task_id,
                                  embedder=get_embedder(settings.embedder), llm=llm)
  ```
- `app/api/category.py::suggest`：`llm=get_llm("mock")` → `llm=await get_configured_llm(s)`（import `from app.services.llm.config import get_configured_llm`；去掉不再用的 `get_llm` import 若无其他用）。
- `app/api/listing.py` 的 `listing_build`：给 `build_create_drafts(s, task_id, params=params, shop_id=shop_id, llm=await get_configured_llm(s))`（import get_configured_llm）。
- `app/api/score.py` sync 分支：**不改**。

- [ ] **Step 8: 运行测试通过 + 回归**

Run: `.venv/bin/python -m pytest tests/test_llm_config.py -q && .venv/bin/python -m pytest tests -q`
Expected: 全绿 0 warnings。

- [ ] **Step 9: 提交**

```bash
git add app/schemas/llm.py app/api/llm.py app/services/llm/config.py app/main.py app/workers/scorer.py app/api/category.py app/api/listing.py tests/test_llm_config.py
git commit -m "feat(llm): /settings/llm 配置页 + get_configured_llm + 接线(scorer/类目建议/自建译标题走真实, sync 仍 mock)"
```

---

### Task 2: 前端 LLM 配置页

**Files:**
- Create: `web/src/api/llm.ts`, `web/src/pages/settings/LlmSettings.tsx`
- Modify: `web/src/App.tsx`(路由)、`web/src/pages/Layout.tsx`(菜单)
- Test: `web/src/pages/settings/LlmSettings.test.tsx`

- [ ] **Step 1: 读现有** `web/src/api/client.ts`（`import { api } from "./client"`）、`web/src/pages/settings/ImagegenSettings.tsx` 与其 `.test.tsx`、`App.tsx`/`Layout.tsx`。

- [ ] **Step 2: 建 `web/src/api/llm.ts`**
```typescript
import { api } from "./client";
export const getLlm = () => api.get("/settings/llm").then(r => r.data);
export const putLlm = (body: any) => api.put("/settings/llm", body).then(r => r.data);
```

- [ ] **Step 3: 建 `LlmSettings.tsx`**（仿 ImagegenSettings）：Form —— llm_provider(Select mock/openai)、llm_base_url、llm_api_key(Password)、llm_model → putLlm；加载时 api_key 强制清空（脱敏不回填，留空不覆盖）；提示"默认通义千问 DashScope；api_key 留空不修改"。

- [ ] **Step 4: 路由 + 菜单** —— `App.tsx` 加 `/settings/llm`；`Layout.tsx` 菜单加"LLM 配置"（归系统设置组）。

- [ ] **Step 5: 写测试** `LlmSettings.test.tsx`（仿 ImagegenSettings.test.tsx）：mock `../../api/llm`，渲染断言控件 + getLlm 调用，触发保存断言 putLlm 调用。

- [ ] **Step 6: 前端测试 + 构建**
Run（从 `web/`）: `source ~/.nvm/nvm.sh && nvm use 20 >/dev/null && npx vitest run && npm run build`
Expected: 通过 + build 成功。

- [ ] **Step 7: 提交**
```bash
git add web/src/api/llm.ts web/src/pages/settings/LlmSettings.tsx web/src/App.tsx web/src/pages/Layout.tsx web/src/pages/settings/LlmSettings.test.tsx
git commit -m "feat(llm): 前端 LLM 配置页(provider/base_url/api_key/model)"
```

---

### Task 3: @live 测试 + 文档 + 回归

**Files:**
- Create: `server/tests/test_live_llm.py`（@pytest.mark.live）
- Modify: `README.md`
- Modify: `docs/去mock化-真实集成总规划.md`（标 A 完成）
- Test: 全量回归

- [ ] **Step 1: 建 `server/tests/test_live_llm.py`**
```python
"""真实 LLM 冒烟(@live 默认跳过)。跑法：
先在 /settings/llm 配好，或设 LLM_BASE_URL/LLM_API_KEY/LLM_MODEL 环境变量后：
  LLM_API_KEY=sk-... .venv/bin/python -m pytest tests/test_live_llm.py -m live -v"""
import os
import pytest
from app.services.llm.openai_compat import OpenAICompatLLM


@pytest.mark.live
@pytest.mark.asyncio
async def test_live_translate_and_extract():
    key = os.environ.get("LLM_API_KEY")
    if not key:
        pytest.skip("需设置 LLM_API_KEY 环境变量")
    base = os.environ.get("LLM_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    model = os.environ.get("LLM_MODEL", "qwen-plus")
    llm = OpenAICompatLLM(base, key, model)
    out = await llm.chat([{"role": "user", "content": "把'蓝色童鞋'翻成俄语，只回译文"}])
    assert out and isinstance(out, str)
```

- [ ] **Step 2: 更新 `README.md`** —— 加/改「真实 LLM」说明：后台 `/settings/llm` 填 base_url/api_key/model + 切 openai；评分/类目建议/自建译标题即走真实；sync=true 批量仍 mock；`@live` 跑法。

- [ ] **Step 3: 更新 `docs/去mock化-真实集成总规划.md`** —— 在子项 A 标注「已完成（配置页 + 接线 + @live）」。

- [ ] **Step 4: 全量回归**
Run:
```bash
cd server && .venv/bin/python -m pytest tests -q
cd ../web && source ~/.nvm/nvm.sh && nvm use 20 >/dev/null && npx vitest run && npm run build
```
Expected: 后端全绿 0 warnings（live 测试 deselected，deselected 数 +1）；前端通过 + build。

- [ ] **Step 5: 提交**
```bash
git add server/tests/test_live_llm.py README.md docs/去mock化-真实集成总规划.md
git commit -m "docs(llm): @live LLM 冒烟测试 + README + 总规划标 A 完成"
```

---

## Self-Review

- **Spec 覆盖**：§2.1 配置页→Task 1；§2.2 get_configured_llm→Task 1；§2.3 接线→Task 1；§3.1 前端→Task 2；§3.2 测试贯穿；§3.3 验收→全量；@live→Task 3。全覆盖。
- **占位符扫描**：无 TBD；后端含完整代码；前端 Task 2 以结构+关键调用给出并要求先读 imagegen 范式。
- **名称一致**：`get_configured_llm(session)`（Task 1 定义、scorer/category/listing 使用一致）；`/settings/llm`（Task 1 建、Task 2 前端调、Task 3 文档）；`LlmIn/LlmOut`。
- **落地注意**：`/settings/llm` 先于通用 settings 注册（Task 1 Step 6，同 imagegen 陷阱）；`run_score` 无开 session，需 `async with async_session() as s`（Task 1 Step 7 已写）；settings 值 str 存，get_configured_llm 直接用字符串无需数值解析。

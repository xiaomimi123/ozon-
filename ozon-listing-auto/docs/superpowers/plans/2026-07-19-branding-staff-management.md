# 品牌换新 + 登录页 + 员工管理 + 角色菜单 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`).

**Goal:** 品牌化「智选万物」(logo+名称) + 登录页 2:1 分栏+移动端 + 员工管理(后端 /users API + 前端页) + 菜单按角色隐藏 + 登出。

**Architecture:** 后端加 `/users` CRUD(admin, 防锁死安全); 前端 Login 重做 + Layout 品牌/角色菜单/登出 + StaffSettings 页。User 模型已有 role/is_active(无迁移)。

**Tech Stack:** FastAPI / React+AntD / pytest / Vitest。

## Global Constraints

- Python 3.11; `.venv/bin/python -m pytest`(从 `server/`); 不用系统 python3。
- **pytest 0 warnings**; 前端 build 通过。
- 用户管理仅 admin(`require_role("admin")`); UserOut 绝不含 password_hash。
- 防锁死: 不能删/停/降最后一个可用 admin, 不能删/停自己。
- 前端菜单隐藏只是可见性, 后端 require_role 仍为真权限。

---

### Task 1: 后端用户管理 API(/users, admin, 防锁死)

**Files:**
- Create: `app/schemas/user.py`, `app/api/users.py`
- Modify: `app/main.py`(注册 users_router)
- Test: `tests/test_users_api.py`

**Interfaces:** `GET/POST /users`、`PUT /users/{id}`、`POST /users/{id}/password`、`DELETE /users/{id}`(均 admin)。

- [ ] **Step 1: 写失败测试** `tests/test_users_api.py`
```python
import pytest
from app.core.security import hash_password
from app.models import User


async def _login(client, db_session, username="admin", pw="p", role="admin"):
    db_session.add(User(username=username, password_hash=hash_password(pw), role=role))
    await db_session.commit()
    tok = (await client.post("/auth/login", data={"username": username, "password": pw})).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


@pytest.mark.asyncio
async def test_user_crud_and_no_password_leak(client, db_session):
    h = await _login(client, db_session)
    r = await client.post("/users", headers=h, json={"username": "op1", "password": "pw123", "role": "operator"})
    assert r.status_code == 200 and "password_hash" not in r.json() and r.json()["role"] == "operator"
    uid = r.json()["id"]
    lst = (await client.get("/users", headers=h)).json()
    assert any(u["username"] == "op1" for u in lst) and all("password_hash" not in u for u in lst)
    # 改角色/停用
    assert (await client.put(f"/users/{uid}", headers=h, json={"role": "reviewer", "is_active": False})).json()["role"] == "reviewer"
    # 重置密码 → 新密码可登录
    await client.post(f"/users/{uid}/password", headers=h, json={"password": "newpw"})
    await client.put(f"/users/{uid}", headers=h, json={"is_active": True})
    assert (await client.post("/auth/login", data={"username": "op1", "password": "newpw"})).status_code == 200
    # 删
    assert (await client.delete(f"/users/{uid}", headers=h)).status_code == 200


@pytest.mark.asyncio
async def test_duplicate_username_400(client, db_session):
    h = await _login(client, db_session)
    await client.post("/users", headers=h, json={"username": "dup", "password": "x", "role": "operator"})
    assert (await client.post("/users", headers=h, json={"username": "dup", "password": "y", "role": "operator"})).status_code == 400


@pytest.mark.asyncio
async def test_cannot_lock_out_last_admin(client, db_session):
    h = await _login(client, db_session)   # 唯一 admin
    me = (await client.get("/auth/me", headers=h)).json()
    # 停用自己 / 删自己 / 降级自己 → 400
    assert (await client.put(f"/users/{me['id']}", headers=h, json={"is_active": False})).status_code == 400
    assert (await client.put(f"/users/{me['id']}", headers=h, json={"role": "operator"})).status_code == 400
    assert (await client.delete(f"/users/{me['id']}", headers=h)).status_code == 400


@pytest.mark.asyncio
async def test_non_admin_403(client, db_session):
    h = await _login(client, db_session, username="op", pw="p", role="operator")
    assert (await client.get("/users", headers=h)).status_code == 403
```

- [ ] **Step 2: 运行确认失败** `.venv/bin/python -m pytest tests/test_users_api.py -q` → FAIL。

- [ ] **Step 3: 建 `app/schemas/user.py`**
```python
from datetime import datetime
from pydantic import BaseModel

class UserCreate(BaseModel):
    username: str
    password: str
    role: str = "operator"

class UserUpdate(BaseModel):
    role: str | None = None
    is_active: bool | None = None

class PasswordReset(BaseModel):
    password: str

class UserOut(BaseModel):
    model_config = {"from_attributes": True}
    id: int
    username: str
    role: str
    is_active: bool
    created_at: datetime
```

- [ ] **Step 4: 建 `app/api/users.py`**
```python
"""员工/用户管理 API(admin)：建/列/改角色·启停/重置密码/删；防锁死(保留可用 admin, 不操作自己)。"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.db import get_session
from app.core.security import hash_password
from app.api.deps import require_role
from app.models import User
from app.schemas.user import UserCreate, UserUpdate, PasswordReset, UserOut

router = APIRouter(prefix="/users", tags=["users"])
_ROLES = {"admin", "operator", "reviewer", "publisher"}


async def _active_admin_count(s: AsyncSession) -> int:
    return (await s.execute(select(func.count()).select_from(User).where(
        User.role == "admin", User.is_active == True))).scalar_one()   # noqa: E712


async def _get(s: AsyncSession, uid: int) -> User:
    u = (await s.execute(select(User).where(User.id == uid))).scalar_one_or_none()
    if not u:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "用户不存在")
    return u


@router.get("", response_model=list[UserOut])
async def list_users(s: AsyncSession = Depends(get_session), _: User = Depends(require_role("admin"))):
    return (await s.execute(select(User).order_by(User.id))).scalars().all()


@router.post("", response_model=UserOut)
async def create_user(body: UserCreate, s: AsyncSession = Depends(get_session), _: User = Depends(require_role("admin"))):
    if body.role not in _ROLES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"非法角色: {body.role}")
    exists = (await s.execute(select(User.id).where(User.username == body.username))).scalar_one_or_none()
    if exists:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "用户名已存在")
    u = User(username=body.username, password_hash=hash_password(body.password), role=body.role)
    s.add(u); await s.commit(); await s.refresh(u)
    return u


@router.put("/{uid}", response_model=UserOut)
async def update_user(uid: int, body: UserUpdate, s: AsyncSession = Depends(get_session),
                      cur: User = Depends(require_role("admin"))):
    u = await _get(s, uid)
    disabling = body.is_active is False
    demoting = body.role is not None and body.role != "admin"
    if (disabling or demoting) and u.role == "admin" and u.is_active:
        if uid == cur.id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "不能停用/降级当前登录的自己")
        if await _active_admin_count(s) <= 1:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "至少保留一个可用管理员")
    if body.role is not None:
        if body.role not in _ROLES:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"非法角色: {body.role}")
        u.role = body.role
    if body.is_active is not None:
        u.is_active = body.is_active
    await s.commit(); await s.refresh(u)
    return u


@router.post("/{uid}/password")
async def reset_password(uid: int, body: PasswordReset, s: AsyncSession = Depends(get_session),
                         _: User = Depends(require_role("admin"))):
    u = await _get(s, uid)
    u.password_hash = hash_password(body.password)
    await s.commit()
    return {"id": uid, "ok": True}


@router.delete("/{uid}")
async def delete_user(uid: int, s: AsyncSession = Depends(get_session), cur: User = Depends(require_role("admin"))):
    u = await _get(s, uid)
    if uid == cur.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "不能删除当前登录的自己")
    if u.role == "admin" and u.is_active and await _active_admin_count(s) <= 1:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "至少保留一个可用管理员")
    await s.delete(u); await s.commit()
    return {"id": uid, "ok": True}
```

- [ ] **Step 5: 改 `app/main.py`** —— 注册 users_router。import `from app.api.users import router as users_router`; include_router 区加 `app.include_router(users_router)`（放 auth_router 附近即可，`/users` 与 `/settings/{category}` 无冲突）。

- [ ] **Step 6: 运行测试通过 + 回归** `.venv/bin/python -m pytest tests/test_users_api.py -q && .venv/bin/python -m pytest tests -q` → 全绿 0 warnings。

- [ ] **Step 7: 提交**
```bash
git add app/schemas/user.py app/api/users.py app/main.py tests/test_users_api.py
git commit -m "feat(users): 员工/用户管理 API(/users admin, 建/改角色·启停/重置密码/删, 防锁死, UserOut 无密码)"
```

---

### Task 2: 前端品牌 + 登录页重做 + 角色菜单 + 登出

**Files:**
- Create: `web/src/brand.ts`
- Modify: `web/src/pages/Login.tsx`（2:1 分栏 + 移动端）
- Modify: `web/src/pages/Layout.tsx`（品牌头 + 角色菜单 + 登出）
- Test: `web/src/pages/Login.test.tsx`（若无则建）

- [ ] **Step 1: 读现有** `web/src/store/auth.ts`（有 `auth.role`）、`Login.tsx`、`Layout.tsx`、一个现有 `*.test.tsx`。

- [ ] **Step 2: 建 `web/src/brand.ts`**
```typescript
import logo from "./assets/logo.jpg";
export const APP_NAME = "智选万物";
export const APP_SUBTITLE = "Ozon 跟卖·铺货 自动化平台";
export const LOGO = logo;
```

- [ ] **Step 3: 重做 `web/src/pages/Login.tsx`** —— 2:1 分栏 + 移动端单列。用 antd `Grid.useBreakpoint()` 判断 `md`；桌面 flex row(左品牌 flex:2 渐变背景 logo+APP_NAME+APP_SUBTITLE, 右表单 flex:1 白底居中卡)，移动端单列(顶部品牌条 + 下方表单)。表单同现有(username/password/登录, `login()`→nav `/tasks`)。关键结构：
```tsx
import { Form, Input, Button, message, Grid } from "antd";
import { useNavigate } from "react-router-dom";
import { login } from "../api/client";
import { APP_NAME, APP_SUBTITLE, LOGO } from "../brand";
export default function Login() {
  const nav = useNavigate();
  const screens = Grid.useBreakpoint();
  const isMobile = !screens.md;
  const onFinish = async (v:{username:string;password:string}) => {
    try { await login(v.username, v.password); nav("/tasks"); }
    catch { message.error("登录失败：用户名或密码错误"); }
  };
  const Brand = (
    <div style={{ background:"linear-gradient(135deg,#173a5e,#2ec4a6)", color:"#fff",
      display:"flex", flexDirection:"column", alignItems:"center", justifyContent:"center",
      padding: isMobile?"32px 16px":48, textAlign:"center" }}>
      <img src={LOGO} alt="logo" style={{ width: isMobile?96:160, borderRadius:16, background:"#fff", padding:8 }} />
      <h1 style={{ color:"#fff", margin:"16px 0 4px", fontSize: isMobile?24:32 }}>{APP_NAME}</h1>
      <div style={{ opacity:.85 }}>{APP_SUBTITLE}</div>
    </div>
  );
  const FormCard = (
    <div style={{ display:"flex", alignItems:"center", justifyContent:"center", padding:24, background:"#fff" }}>
      <div style={{ width: 320, maxWidth:"100%" }}>
        <h2 style={{ marginBottom:16 }}>登录</h2>
        <Form onFinish={onFinish} layout="vertical">
          <Form.Item name="username" label="用户名" rules={[{required:true}]}><Input size="large" /></Form.Item>
          <Form.Item name="password" label="密码" rules={[{required:true}]}><Input.Password size="large" /></Form.Item>
          <Button type="primary" htmlType="submit" size="large" block>登录</Button>
        </Form>
      </div>
    </div>
  );
  if (isMobile) return <div style={{ minHeight:"100vh", display:"flex", flexDirection:"column" }}>{Brand}{FormCard}</div>;
  return <div style={{ minHeight:"100vh", display:"flex" }}>
    <div style={{ flex:2 }}>{Brand}</div><div style={{ flex:1 }}>{FormCard}</div>
  </div>;
}
```

- [ ] **Step 4: 改 `web/src/pages/Layout.tsx`** —— 品牌头(logo+APP_NAME)、菜单按角色过滤、登出。
- 侧栏头：`<img src={LOGO} .../> {APP_NAME}`。
- 菜单：定义 `const items = [...]`（业务页无 adminOnly；管理页 `adminOnly:true`，含新增 `{key:"staff", label:"员工管理", adminOnly:true}`）；`const role = auth.role`；`items.filter(i => !i.adminOnly || role === "admin")`。
- 业务页 keys：tasks/products/review/listing/image-studio/monitor。管理页 keys：shops/pricing/settings/imagegen/settings/crawler/settings/llm/settings/sources/settings/system/staff。
- 登出：侧栏底或头部加「退出登录」按钮 → `auth.clear(); nav("/login")`。

- [ ] **Step 5: 建/改 `web/src/pages/Login.test.tsx`** —— 渲染断言 APP_NAME「智选万物」+ 用户名/密码/登录控件出现（Vitest；mock `../api/client` login）。

- [ ] **Step 6: 前端测试 + 构建** `source ~/.nvm/nvm.sh && nvm use 20 >/dev/null && npx vitest run && npm run build` → 通过 + build。

- [ ] **Step 7: 提交**
```bash
git add web/src/brand.ts web/src/pages/Login.tsx web/src/pages/Layout.tsx web/src/pages/Login.test.tsx
git commit -m "feat(brand): 智选万物 品牌 + 登录页 2:1 分栏+移动端 + 菜单按角色隐藏 + 登出"
```

---

### Task 3: 前端员工管理页 + 路由 + 回归

**Files:**
- Create: `web/src/api/users.ts`, `web/src/pages/settings/StaffSettings.tsx`, `web/src/pages/settings/StaffSettings.test.tsx`
- Modify: `web/src/App.tsx`（route `/staff`）
- Modify: `README.md`
- Test: 全量回归

- [ ] **Step 1: `web/src/api/users.ts`**
```typescript
import { api } from "./client";
export const listUsers = () => api.get("/users").then(r => r.data);
export const createUser = (b:any) => api.post("/users", b).then(r => r.data);
export const updateUser = (id:number, b:any) => api.put(`/users/${id}`, b).then(r => r.data);
export const resetPassword = (id:number, password:string) => api.post(`/users/${id}/password`, { password }).then(r => r.data);
export const deleteUser = (id:number) => api.delete(`/users/${id}`).then(r => r.data);
```

- [ ] **Step 2: `StaffSettings.tsx`** —— 表格(用户名/角色 Tag[管理员·操作员·审核员·发布员]/状态[启用·停用]/创建时间/操作) + 新增员工(用户名·密码·角色 Select) + 行操作(改角色 Select→updateUser、启停→updateUser is_active、重置密码 Modal→resetPassword、删除 Popconfirm→deleteUser)；操作后刷新列表；失败 message.error(后端消息)。角色中文映射常量 `ROLE_LABEL={admin:"管理员",operator:"操作员",reviewer:"审核员",publisher:"发布员"}`。

- [ ] **Step 3: 路由 `App.tsx`** —— 加 `<Route path="/staff" element={<StaffSettings />} />`（菜单项已在 Task 2 Layout 加）。

- [ ] **Step 4: `StaffSettings.test.tsx`** —— mock `../../api/users`，渲染断言表格 + listUsers 调用；新增交互断言 createUser 调用（Vitest，仿 ImagegenSettings.test.tsx）。

- [ ] **Step 5: 文档** —— README 加「员工管理/权限」小节（/users API + 员工管理页 + 4 角色 + 菜单按角色隐藏 + 防锁死）。

- [ ] **Step 6: 全量回归**
```bash
cd server && .venv/bin/python -m pytest tests -q
cd ../web && source ~/.nvm/nvm.sh && nvm use 20 >/dev/null && npx vitest run && npm run build
```
Expected: 后端全绿 0 warnings；前端通过 + build。

- [ ] **Step 7: 提交**
```bash
git add web/src/api/users.ts web/src/pages/settings/StaffSettings.tsx web/src/pages/settings/StaffSettings.test.tsx web/src/App.tsx README.md
git commit -m "feat(users): 前端员工管理页(建/改角色·启停/重置密码/删) + 路由 + README"
```

---

## Self-Review

- **Spec 覆盖**：§2 后端 users API→Task 1；§3.1/3.2 品牌+登录→Task 2；§3.3 角色菜单+登出→Task 2；§3.4 员工管理页→Task 3；§4 测试贯穿。全覆盖。
- **占位符扫描**：无 TBD；后端含完整代码；登录页含完整 tsx；员工管理页以结构+关键调用给出并要求仿 ImagegenSettings。
- **名称/契约一致**：`/users`(GET/POST/PUT/{id}/password/DELETE)，UserOut 无 password_hash；`auth.role` 驱动菜单；`APP_NAME="智选万物"`、`LOGO`；ROLE_LABEL 4 角色。
- **落地注意**：防锁死(最后一个可用 admin + 不操作自己)后端硬校验；UserOut from_attributes 不含 hash；前端菜单隐藏≠真权限(后端为准)；登录页 Grid.useBreakpoint 移动端单列；/users 非 /settings 无路由冲突。

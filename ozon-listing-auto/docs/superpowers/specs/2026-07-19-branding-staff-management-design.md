# 设计文档：品牌换新 + 登录页重做 + 员工管理 + 角色菜单

> 日期：2026-07-19。用户需求：logo（智选万物）、登录页 2:1 分栏+移动端、员工登入权限管理、管理页加员工管理页、菜单按角色隐藏。

## 1. 目标与范围

**目标** = 把系统品牌化为「智选万物」，重做登录页（分栏+移动端），补齐员工账号/权限管理（后端 API + 前端页），菜单按角色隐藏。

**范围：**
1. 品牌：侧栏头 + 登录页用 `web/src/assets/logo.jpg` + 名称「智选万物」。
2. 登录页 2:1 分栏（左品牌区 + 右表单）+ 移动端单列堆叠。
3. 后端用户管理 API `/users`（仅 admin）：列表/建/改角色·启停/重置密码/删。防锁死安全。
4. 前端员工管理页（仅 admin）：表格 + 增删改/启停/重置密码。
5. 菜单按角色过滤：业务页所有角色可见；配置/管理页仅 admin。

**不做**：细粒度页面级权限编辑（按 4 种固定角色）；SSO/双因子。

## 2. 后端 —— 用户管理 API（`schemas/user.py` + `api/users.py`）

`User` 模型已有 `id/username/password_hash/role/is_active/created_at`（无需迁移）。角色 ∈ admin/operator/reviewer/publisher。

- `GET /users`（admin）→ `[{id, username, role, is_active, created_at}]`（不含 password_hash）。
- `POST /users`（admin）body `{username, password, role}` → 建用户（username 唯一，冲突 400；password `hash_password`；role 校验白名单）→ 返回 UserOut。
- `PUT /users/{id}`（admin）body `{role?, is_active?}` → 改角色/启停。
- `POST /users/{id}/password`（admin）body `{password}` → 重置密码（hash 存）。
- `DELETE /users/{id}`（admin）→ 删。
- **防锁死安全**（关键）：
  - 不能删除/停用/降级**最后一个可用 admin**（`is_active=true and role="admin"` 计数为 1 时拒，返回 400 "至少保留一个可用管理员"）。
  - 不能删除/停用自己（当前登录用户）→ 400。
- `UserOut`：id/username/role/is_active/created_at（**绝不含 password_hash**）。

角色门 `require_role("admin")`（admin 超级通过）。

## 3. 前端

### 3.1 品牌资源与常量
- `web/src/assets/logo.jpg`（已放）；`web/src/brand.ts` 导出 `APP_NAME = "智选万物"`、`APP_SUBTITLE = "Ozon 跟卖·铺货 自动化平台"` + logo import，供 Login/Layout 复用。

### 3.2 登录页重做（`Login.tsx`）
- 桌面（≥768px）：flex row，左品牌区 flex 2（深蓝→青渐变 `linear-gradient(135deg,#173a5e,#2ec4a6)`，居中放 logo + 智选万物 + 副标题），右表单区 flex 1（白底，居中登录卡：用户名/密码/登录，回车提交）。
- 移动端（<768px，CSS `@media` 或 antd `Grid.useBreakpoint`）：单列 —— 顶部品牌条（logo 缩小 + 名称）+ 下方表单占满。`max-width:100%`、`min-height:100vh`。
- 登录逻辑不变（`login()` → nav `/tasks`）。

### 3.3 布局品牌 + 角色菜单（`Layout.tsx`）
- 侧栏头：logo（小） + 智选万物。
- **菜单按角色过滤**：定义 `MENU`（每项含 `key/label/adminOnly?`）；`const role = auth.role`；`adminOnly` 项仅 `role==="admin"` 显示。
  - 业务页（所有角色）：tasks 任务中心、products 商品列表、review 审核台、listing 上架审核、image-studio 图片工作室、monitor 上架监控。
  - 管理页（adminOnly）：shops 店铺管理、pricing 定价设置、settings/imagegen AI 生图配置、settings/crawler 爬虫配置、settings/llm LLM 配置、settings/sources 货源配置、settings/system 系统设置、**staff 员工管理**。
- 加「退出登录」入口（`auth.clear()` → `/login`）（顺带补，现无登出）。

### 3.4 员工管理页（`web/src/pages/settings/StaffSettings.tsx`，route `/staff`）
- `web/src/api/users.ts`：listUsers/createUser/updateUser/resetPassword/deleteUser。
- 表格：用户名 / 角色（Tag，中文 管理员·操作员·审核员·发布员）/ 状态（启用·停用）/ 创建时间 / 操作（改角色 Select、启用停用、重置密码、删除）。
- 顶部「新增员工」：用户名 + 密码 + 角色 → createUser。
- 删除/停用/降级触发后端安全校验，失败 toast 后端消息。

## 4. 测试 + 验收 + 风险

### 4.1 测试
- 后端：`/users` CRUD（admin）；建重名 400；重置密码后可登录（新密码）；**防锁死**（删/停/降最后一个 admin → 400；删自己 → 400）；UserOut 不含 password_hash；非 admin 调 `/users` → 403。
- 前端：Login 渲染（品牌 + 表单，桌面/移动断点）；Layout 菜单按角色过滤（admin 见管理页，operator 不见）；StaffSettings 渲染 + 新增/改/删调 API（Vitest + mock）。
- 0 warnings；前端 build。

### 4.2 验收标准
1. 登录页：桌面 2:1 分栏（品牌+表单）、移动端单列，logo+「智选万物」显示。
2. 侧栏头 logo+智选万物；菜单按角色隐藏（非 admin 看不到配置/管理页）；有登出。
3. 员工管理页（admin）：建员工/分配角色/启停/重置密码/删；防锁死生效。
4. 非 admin 调 /users 403；password_hash 不泄漏。
5. 后端 0 warnings + 前端 build + README/docs。

### 4.3 风险与降级
| 风险 | 应对 |
|---|---|
| 误删/停最后一个 admin 致锁死 | 后端硬校验拒绝（至少保留一个可用 admin + 不能操作自己）|
| 密码泄漏 | UserOut 不含 hash；重置只收明文入参 hash 存 |
| 移动端布局错乱 | media query 单列兜底 + max-width:100% |
| 前端菜单隐藏≠真权限 | 后端 require_role 仍为准（菜单只是可见性）|

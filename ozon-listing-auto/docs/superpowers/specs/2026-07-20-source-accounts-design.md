# 设计文档：货源账号池管理页（1688 + 拼多多）

> 日期：2026-07-20。子项目②（三件事：①自动上品✅ → ②货源账号池 → ③配置页小白化）。
> 用户决策：1688+拼多多共用一个「货源账号」页；凭证只放 Cookie 一个字段；保留「手动恢复（清冷却）」。

## 1. 背景与现状（已核对代码）

- **后端 `/accounts` CRUD 已就绪**（`server/app/api/accounts.py`，均 `require_role("admin")`）：
  - `POST /accounts` body `AccountCreate{platform, label?, credentials: dict, daily_limit=200, min_interval_sec=6}` → 平台仅允许 `ali1688|pinduoduo`（否则 422），credentials `json.dumps` 后 Fernet 加密存。
  - `GET /accounts?platform=` → `list[AccountOut]`（按 id desc）。
  - `PUT /accounts/{id}` body `AccountUpdate{label?, daily_limit?, min_interval_sec?, status?, credentials?}` → 逐字段更新；credentials 给了才覆盖。
  - `DELETE /accounts/{id}` → 204。
- **`AccountOut`**（`server/app/schemas/account.py`）：`id, platform, label, status, daily_limit, min_interval_sec, daily_used_count, cooldown_until, risk_hits, created_at`（**不含 credentials**，脱敏）。
- **`SourceAccount` 模型**：`platform, label, credentials_encrypted, status(active|cooldown|disabled), last_used_at, daily_used_date, daily_used_count, daily_limit, min_interval_sec, cooldown_until, risk_hits, created_at`。
- **账号池**（`server/app/services/account_pool.py`）：`acquire()` 选非 disabled、不在冷却（`cooldown_until>now` 跳过）、满足最小间隔、当日未超限的账号；`report_risk()` 风控时 `status="cooldown"` + `cooldown_until=now+30min`；凭证 `get_session_credentials()` = `json.loads(decrypt(...))`，1688/拼多多 provider 取 `credentials["cookie"]`。
- **前端**：**无**货源账号页；`accounts` 无 api 封装。菜单/路由在 `web/src/pages/Layout.tsx` + 路由表。参照已有 `web/src/pages/settings/StaffSettings.tsx`（员工管理）的表格+表单+行操作+Modal 模式。

## 2. 目标与范围

**目标**：给运营一个可视化「货源账号」管理页，增删改查 1688/拼多多的 Cookie 账号、管理状态与限速、对冷却账号一键恢复。后端已备，主要补前端 + 一处小后端补丁。

**范围**
1. 前端页 `SourceAccounts.tsx`（route `/source-accounts`，菜单 adminOnly「货源账号」）。
2. `web/src/api/sourceAccounts.ts` 封装 `/accounts`。
3. 后端补丁：`update_account` 中 `status` 改为 `active` 时同时清 `cooldown_until`（支持手动恢复）。

**不做（YAGNI）**：Cookie 在线有效性校验；批量导入；1688/拼多多真实采集打通（需真实接口，另议）；credentials 除 cookie 外的字段。

## 3. 后端补丁（`server/app/api/accounts.py`）

`update_account` 现有循环 `for f in ("label","daily_limit","min_interval_sec","status")` 之后、`credentials` 之前，加：
```python
if body.status == "active":
    acc.cooldown_until = None   # 手动恢复：清冷却，acquire 才能立即选中
```
（其余不动。`report_risk` 置冷却逻辑不变；冷却仍会自动到期恢复。）

## 4. 前端

### 4.1 api 封装（`web/src/api/sourceAccounts.ts`）
```ts
import { api } from "./client";
export const listAccounts = (platform?: string) =>
  api.get("/accounts", { params: platform ? { platform } : {} }).then(r => r.data);
export const createAccount = (body: { platform: string; label?: string; credentials: any; daily_limit?: number; min_interval_sec?: number }) =>
  api.post("/accounts", body).then(r => r.data);
export const updateAccount = (id: number, body: any) => api.put(`/accounts/${id}`, body).then(r => r.data);
export const deleteAccount = (id: number) => api.delete(`/accounts/${id}`).then(r => r.data);
```

### 4.2 页面（`web/src/pages/settings/SourceAccounts.tsx`）
- 常量：`PLATFORM_LABEL = {ali1688:"1688", pinduoduo:"拼多多"}`；`STATUS_LABEL = {active:"可用", cooldown:"冷却中", disabled:"停用"}`；`STATUS_COLOR = {active:"success", cooldown:"orange", disabled:"default"}`。
- **表格**（`scroll={{x:"max-content"}}` 移动端可横滑）列：平台(Tag)、标签、状态(Tag)、`用量`=`{daily_used_count}/{daily_limit}`、最小间隔(秒)、风控次数、冷却至（格式化，空→"-"）、创建时间（格式化）、操作。
- **新增账号**（Card 内 Form）：平台 Select(1688/拼多多)、标签 Input、**Cookie** `Input.TextArea`（必填）、日上限 InputNumber(默认 200)、最小间隔秒 InputNumber(默认 6) → `createAccount({platform, label, credentials:{cookie}, daily_limit, min_interval_sec})` → 成功 toast + 刷新 + 重置表单。
- **行操作**（Space）：
  - 启用/停用：`updateAccount(id, {status: active?"disabled":"active"})`。
  - **手动恢复**：仅 `status==="cooldown"` 显示，`updateAccount(id, {status:"active"})`（后端会清冷却）。
  - **更新 Cookie**：Modal（TextArea），`updateAccount(id, {credentials:{cookie}})`；不显示旧 Cookie（脱敏），留空不提交。
  - 删除：Popconfirm → `deleteAccount(id)`。
- 错误 toast 走 `err?.response?.data?.detail`（仿 StaffSettings 的 `errMsg`）。

### 4.3 菜单 + 路由
- `Layout.tsx` `menuItems` 加 `{ key: "source-accounts", label: "货源账号", adminOnly: true }`（放在「货源配置」附近的管理区）。
- 路由表（`App.tsx` 或路由定义处）加 `/source-accounts` → `SourceAccounts`。

## 5. 测试

- **后端**：`update_account` 传 `status="active"` 时 `cooldown_until` 被清空（先造一个 cooldown 账号）；平台非法 422（已有则不重复）；回归 `tests/test_accounts_api.py`。
- **前端**（Vitest + mock `../api/sourceAccounts`，仿 `StaffSettings.test.tsx`）：页面渲染表格 + 新增表单；新增/停用/恢复/更新 Cookie/删除各调对应 API；菜单项对 admin 可见。
- 后端 0 warnings；前端 `npm run build` + vitest 通过。

## 6. 验收标准
1. admin 菜单见「货源账号」；页面列出账号，平台/状态中文显示。
2. 新增 1688 或 拼多多 账号（填 Cookie）→ 列表出现，Cookie 不回显。
3. 停用/启用、删除生效；冷却中账号点「手动恢复」→ 状态回可用且 `cooldown_until` 清空（`acquire` 可再选中）。
4. 更新 Cookie 生效（PUT credentials，脱敏）。
5. 后端 0 warnings + 前端 build + vitest 通过。

## 7. 风险与降级
| 风险 | 应对 |
|---|---|
| Cookie 是密文，误显示泄漏 | AccountOut 不含 credentials；表格不显示；更新 Cookie 留空不覆盖 |
| 手动恢复清冷却绕过风控 | 属运营主动操作（换了好 Cookie）；仅清 cooldown_until，不动 risk_hits 计数 |
| 平台字段非法 | 后端已 422 校验；前端下拉限定两项 |
| 移动端表格溢出 | `scroll={{x:"max-content"}}`（与本项目其它表格一致）|

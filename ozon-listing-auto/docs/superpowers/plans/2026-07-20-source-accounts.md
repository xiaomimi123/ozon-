# 货源账号池管理页 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给运营一个「货源账号」管理页，增删改查 1688/拼多多 的 Cookie 账号、管理状态/限速、对冷却账号一键恢复。

**Architecture:** 后端 `/accounts` CRUD 已就绪，仅补一处「手动恢复清冷却」补丁；主要新增前端页 `SourceAccounts.tsx` + api 封装 + 菜单/路由，复用 `StaffSettings.tsx` 的表格+表单+行操作+Modal 模式。

**Tech Stack:** Python 3.11 / FastAPI / SQLAlchemy async；React 18 + TS + Ant Design 5 + Vitest。

## Global Constraints

- 后端测试 **0 warnings**；前端每步 `npm run build` + 相关 vitest 通过。
- 平台仅 `ali1688`/`拼多多(pinduoduo)`；凭证只用 Cookie 字段，提交为 `credentials={"cookie": <值>}`。
- `AccountOut` 不含 credentials（脱敏）；更新 Cookie 留空不覆盖；表格不回显 Cookie。
- 前端沿用 `import { api } from "./client"`；配置/管理页仅 admin。
- 中文标签：平台 `{ali1688:"1688", pinduoduo:"拼多多"}`；状态 `{active:"可用", cooldown:"冷却中", disabled:"停用"}`。
- 后端补丁只在 `update_account` 内、`status=="active"` 时清 `cooldown_until`，不动 `report_risk`/`risk_hits`/其它字段。

---

### Task 1: 后端补丁——手动恢复清冷却

**Files:**
- Modify: `server/app/api/accounts.py`（`update_account`）
- Test: `server/tests/test_accounts_api.py`（追加）

**Interfaces:**
- Produces: `PUT /accounts/{id}` body `{status:"active"}` 时，除设 `status=active` 外还把 `cooldown_until` 置 `None`。

- [ ] **Step 1: 写失败测试**

```python
# 追加到 server/tests/test_accounts_api.py
# 参照本文件既有 auth/建账号方式；核心断言：cooldown 账号 PUT status=active 后 cooldown_until 被清空
import json
from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from app.core.security import hash_password
from app.core.crypto import encrypt
from app.models import User, SourceAccount

async def _admin_headers(client, db_session):
    db_session.add(User(username="adm", password_hash=hash_password("p"), role="admin"))
    await db_session.commit()
    tok = (await client.post("/auth/login", data={"username": "adm", "password": "p"})).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}

@pytest.mark.asyncio
async def test_put_status_active_clears_cooldown(client, db_session):
    h = await _admin_headers(client, db_session)
    acc = SourceAccount(platform="ali1688", label="a",
                        credentials_encrypted=encrypt(json.dumps({"cookie": "c"})),
                        status="cooldown", cooldown_until=datetime.now(timezone.utc) + timedelta(minutes=30))
    db_session.add(acc); await db_session.commit()
    r = await client.put(f"/accounts/{acc.id}", json={"status": "active"}, headers=h)
    assert r.status_code == 200 and r.json()["status"] == "active"
    await db_session.refresh(acc)
    assert acc.cooldown_until is None
```
> 若文件已有 `import pytest` / auth helper，复用，勿重复定义。

- [ ] **Step 2: 运行确认失败**

Run: `cd server && .venv/bin/python -m pytest tests/test_accounts_api.py::test_put_status_active_clears_cooldown -q`
Expected: FAIL（cooldown_until 仍非空）

- [ ] **Step 3: 实现**

`update_account` 内，现有 `for f in ("label","daily_limit","min_interval_sec","status"): ...` 循环之后、`if body.credentials is not None:` 之前，插入：
```python
    if body.status == "active":
        acc.cooldown_until = None   # 手动恢复：清冷却, acquire 方可立即选中
```

- [ ] **Step 4: 运行确认通过 + 回归**

Run: `cd server && .venv/bin/python -m pytest tests/test_accounts_api.py -q && .venv/bin/python -m pytest -q`
Expected: PASS，全套 0 warnings

- [ ] **Step 5: 提交**

```bash
git add server/app/api/accounts.py server/tests/test_accounts_api.py
git commit -m "feat(accounts): 手动恢复——status=active 时清 cooldown_until"
```

---

### Task 2: 前端货源账号管理页 + api 封装 + 菜单/路由

**Files:**
- Create: `web/src/api/sourceAccounts.ts`
- Create: `web/src/pages/settings/SourceAccounts.tsx`
- Create: `web/src/pages/settings/SourceAccounts.test.tsx`
- Modify: `web/src/pages/Layout.tsx`（菜单加「货源账号」）
- Modify: `web/src/App.tsx`（加路由 `/source-accounts`）

**Interfaces:**
- Consumes: `/accounts` CRUD（Task 1 后端）。`AccountOut` 字段：`id, platform, label, status, daily_limit, min_interval_sec, daily_used_count, cooldown_until, risk_hits, created_at`。

- [ ] **Step 1: 写失败测试**

```tsx
// web/src/pages/settings/SourceAccounts.test.tsx
import { render, screen } from "@testing-library/react";
import { vi } from "vitest";
vi.mock("../../api/sourceAccounts", () => ({
  listAccounts: vi.fn(() => Promise.resolve([
    { id: 1, platform: "ali1688", label: "号1", status: "cooldown", daily_limit: 200,
      min_interval_sec: 6, daily_used_count: 3, cooldown_until: "2026-07-20T10:00:00Z", risk_hits: 1,
      created_at: "2026-07-20T09:00:00Z" },
  ])),
  createAccount: vi.fn(), updateAccount: vi.fn(), deleteAccount: vi.fn(),
}));
import SourceAccounts from "./SourceAccounts";

test("渲染货源账号表格与新增表单", async () => {
  render(<SourceAccounts />);
  expect(await screen.findByText("新增账号")).toBeInTheDocument();
  expect(await screen.findByText("号1")).toBeInTheDocument();
  expect(await screen.findByText("1688")).toBeInTheDocument();   // 平台中文
  expect(await screen.findByText("冷却中")).toBeInTheDocument();  // 状态中文
});
```

- [ ] **Step 2: 运行确认失败**

Run: `cd web && npx vitest run src/pages/settings/SourceAccounts -q`
Expected: FAIL（组件不存在）

- [ ] **Step 3: 实现 api 封装**

`web/src/api/sourceAccounts.ts`：
```ts
import { api } from "./client";
export const listAccounts = (platform?: string) =>
  api.get("/accounts", { params: platform ? { platform } : {} }).then((r) => r.data);
export const createAccount = (body: { platform: string; label?: string; credentials: any; daily_limit?: number; min_interval_sec?: number }) =>
  api.post("/accounts", body).then((r) => r.data);
export const updateAccount = (id: number, body: any) => api.put(`/accounts/${id}`, body).then((r) => r.data);
export const deleteAccount = (id: number) => api.delete(`/accounts/${id}`).then((r) => r.data);
```

- [ ] **Step 4: 实现页面**

`web/src/pages/settings/SourceAccounts.tsx`（仿 `StaffSettings.tsx` 结构）：
```tsx
import { useEffect, useState } from "react";
import { Card, Form, Input, InputNumber, Select, Button, Table, Space, Tag, Modal, Popconfirm, message } from "antd";
import { listAccounts, createAccount, updateAccount, deleteAccount } from "../../api/sourceAccounts";

const PLATFORM_LABEL: Record<string, string> = { ali1688: "1688", pinduoduo: "拼多多" };
const PLATFORM_OPTIONS = Object.entries(PLATFORM_LABEL).map(([value, label]) => ({ value, label }));
const STATUS_LABEL: Record<string, string> = { active: "可用", cooldown: "冷却中", disabled: "停用" };
const STATUS_COLOR: Record<string, string> = { active: "success", cooldown: "orange", disabled: "default" };

function errMsg(err: any, fallback: string) {
  return err?.response?.data?.detail || fallback;
}
const fmt = (v?: string) => (v ? String(v).replace("T", " ").slice(0, 19) : "-");

export default function SourceAccounts() {
  const [rows, setRows] = useState<any[]>([]);
  const [form] = Form.useForm();
  const [ckAccount, setCkAccount] = useState<any>(null);
  const [ckForm] = Form.useForm();

  const load = () => listAccounts().then(setRows);
  useEffect(() => { load(); }, []);

  const onCreate = async (v: any) => {
    try {
      await createAccount({ platform: v.platform, label: v.label, credentials: { cookie: v.cookie },
        daily_limit: v.daily_limit, min_interval_sec: v.min_interval_sec });
      message.success("已添加账号"); form.resetFields(); load();
    } catch (err) { message.error(errMsg(err, "添加失败")); }
  };
  const onToggle = async (r: any) => {
    try { await updateAccount(r.id, { status: r.status === "disabled" ? "active" : "disabled" });
      message.success("已更新"); load(); } catch (err) { message.error(errMsg(err, "操作失败")); }
  };
  const onRestore = async (r: any) => {
    try { await updateAccount(r.id, { status: "active" }); message.success("已恢复为可用"); load(); }
    catch (err) { message.error(errMsg(err, "操作失败")); }
  };
  const onDelete = async (id: number) => {
    try { await deleteAccount(id); message.success("已删除"); load(); }
    catch (err) { message.error(errMsg(err, "操作失败")); }
  };
  const onUpdateCookie = async (v: any) => {
    try { await updateAccount(ckAccount.id, { credentials: { cookie: v.cookie } });
      message.success("Cookie 已更新"); setCkAccount(null); ckForm.resetFields(); }
    catch (err) { message.error(errMsg(err, "更新失败")); }
  };

  return (
    <Space direction="vertical" style={{ width: "100%" }} size="large">
      <Card title="新增账号">
        <Form form={form} layout="vertical" onFinish={onCreate}
          initialValues={{ platform: "ali1688", daily_limit: 200, min_interval_sec: 6 }} style={{ maxWidth: 560 }}>
          <Form.Item name="platform" label="平台" rules={[{ required: true }]}>
            <Select options={PLATFORM_OPTIONS} style={{ width: 160 }} />
          </Form.Item>
          <Form.Item name="label" label="标签"><Input placeholder="便于识别，如 号1" /></Form.Item>
          <Form.Item name="cookie" label="Cookie" rules={[{ required: true, message: "请粘贴登录 Cookie" }]}>
            <Input.TextArea rows={3} placeholder="登录后从浏览器复制整条 Cookie" />
          </Form.Item>
          <Space>
            <Form.Item name="daily_limit" label="日上限"><InputNumber min={1} /></Form.Item>
            <Form.Item name="min_interval_sec" label="最小间隔(秒)"><InputNumber min={0} /></Form.Item>
          </Space>
          <Form.Item><Button type="primary" htmlType="submit">新增账号</Button></Form.Item>
        </Form>
      </Card>
      <Card title="货源账号列表">
        <Table rowKey="id" dataSource={rows} pagination={false} scroll={{ x: "max-content" }}
          columns={[
            { title: "平台", dataIndex: "platform", width: 90, render: (p) => <Tag>{PLATFORM_LABEL[p] || p}</Tag> },
            { title: "标签", dataIndex: "label", width: 120 },
            { title: "状态", dataIndex: "status", width: 90,
              render: (s) => <Tag color={STATUS_COLOR[s]}>{STATUS_LABEL[s] || s}</Tag> },
            { title: "用量", width: 90, render: (_, r) => `${r.daily_used_count}/${r.daily_limit}` },
            { title: "最小间隔", dataIndex: "min_interval_sec", width: 90 },
            { title: "风控次数", dataIndex: "risk_hits", width: 90 },
            { title: "冷却至", dataIndex: "cooldown_until", width: 170, render: fmt },
            { title: "创建时间", dataIndex: "created_at", width: 170, render: fmt },
            { title: "操作", width: 300, render: (_, r) => (
              <Space>
                <Button size="small" onClick={() => onToggle(r)}>{r.status === "disabled" ? "启用" : "停用"}</Button>
                {r.status === "cooldown" && <Button size="small" onClick={() => onRestore(r)}>手动恢复</Button>}
                <Button size="small" onClick={() => setCkAccount(r)}>更新 Cookie</Button>
                <Popconfirm title="删除该账号?" onConfirm={() => onDelete(r.id)}>
                  <Button size="small" danger>删除</Button>
                </Popconfirm>
              </Space>
            ) },
          ]} />
      </Card>
      <Modal title={`更新 Cookie - ${ckAccount?.label ?? ckAccount?.id ?? ""}`} open={!!ckAccount}
        onCancel={() => { setCkAccount(null); ckForm.resetFields(); }} onOk={() => ckForm.submit()} destroyOnClose>
        <Form form={ckForm} layout="vertical" onFinish={onUpdateCookie}>
          <Form.Item name="cookie" label="新 Cookie" rules={[{ required: true, message: "请粘贴新 Cookie" }]}>
            <Input.TextArea rows={3} placeholder="粘贴新的登录 Cookie（不显示旧值）" />
          </Form.Item>
        </Form>
      </Modal>
    </Space>
  );
}
```

- [ ] **Step 5: 挂菜单 + 路由**

`web/src/pages/Layout.tsx` `menuItems` 加一项（放管理区，如「货源配置」附近）：
```tsx
  { key: "source-accounts", label: "货源账号", adminOnly: true },
```
`web/src/App.tsx`：顶部 `import SourceAccounts from "./pages/settings/SourceAccounts";`，路由区加：
```tsx
          <Route path="/source-accounts" element={<SourceAccounts />} />
```

- [ ] **Step 6: 运行测试 + build**

Run: `cd web && npx vitest run src/pages/settings/SourceAccounts -q && npm run build`
Expected: PASS + build 成功

- [ ] **Step 7: 提交**

```bash
git add web/src/api/sourceAccounts.ts web/src/pages/settings/SourceAccounts.tsx web/src/pages/settings/SourceAccounts.test.tsx web/src/pages/Layout.tsx web/src/App.tsx
git commit -m "feat(web): 货源账号管理页(1688/拼多多)+api封装+菜单路由"
```

---

## 收尾（全部任务后）
- 更新 `README.md`：把「1688 Cookie 账号需调 API 添加（无前端页）」的说法更新为「货源账号页（`/source-accounts`）可视化增删改查」；`docs/功能测试清单-真实集成准备.md` §5 里「添加 1688 Cookie 账号：目前无前端页面，需调后端 API」同步更正为用货源账号页。
- 后端 `pytest -q` 0 warnings + 前端 `npm run build` + `vitest run` 通过。
- 重建 docker 验证：`WEB_PORT=18080 DB_PORT=15432 REDIS_PORT=16379 API_PORT=18000 docker compose up -d --build web`。

## 自查
- 覆盖 spec：后端补丁(T1)、api 封装+页面+菜单+路由(T2)、测试(两任务各含)、收尾文档 —— 全覆盖。
- 类型一致：`listAccounts/createAccount/updateAccount/deleteAccount` 命名、`AccountOut` 字段名、平台/状态常量在计划内一致。
- 无占位符：各步含实际代码/命令。
- 安全：credentials 只送 `{cookie}`；表格不回显；更新 Cookie 留空不覆盖；AccountOut 脱敏。

# Excel 导入货源 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在「导入商品」页上传 1688 采购助手导出的 .xlsx → 解析入库 → 列表可见。复用现有表，无需迁移。

**Architecture:** 后端加 `openpyxl` + 表头名映射解析器 `parse_1688_excel` + `POST /import/excel`（上传，admin 登录鉴权）→ 存 ImportCapture + 去重入 ImportedProduct。前端「导入商品」页加上传按钮。

**Tech Stack:** Python 3.11 / FastAPI / openpyxl；React 18 + TS + Ant Design 5 + Vitest。

## Global Constraints

- 后端 0 warnings；用合成 .xlsx fixture 做 TDD。复用 `ImportCapture`/`ImportedProduct`（无迁移）。
- 列映射用真实导出表头固定默认（`标题/产品ID/产品链接/图片链接/价格/店铺名称/月销件数`）；解析器接受 cols 参数便于测试，端点用默认（配置化 override 属未来，本次不做）。
- offer_id 取「产品ID」；缺失时从「产品链接」提取 `offer/(\d+)`；仍无则跳过该行。去重 (platform, offer_id)。
- raw 存该行 表头→值 dict，值须 JSON 安全（datetime 等转 str）。
- 上传走 JWT（`require_role("admin")`），非 import_token。前端沿用 `import { api } from "./client"`。

---

### Task 1: openpyxl + 解析器 + 上传接口（后端）

**Files:**
- Modify: `server/pyproject.toml`（加 `openpyxl>=3.1`）
- Create: `server/app/services/sources/parser_excel.py`
- Modify: `server/app/api/importer.py`（加 `POST /excel`）
- Test: `server/tests/test_parser_excel.py`、`server/tests/test_import_excel_api.py`

**Interfaces:**
- Produces: `DEFAULT_EXCEL_COLS: dict`；`parse_1688_excel(rows: list[list], cols: dict | None = None) -> list[dict]`（每项 offer_id/title/price/image_url/shop_name/detail_url/sales/raw）；`POST /import/excel`（UploadFile file）→ `{capture_id, captured, parsed, skipped}`。

- [ ] **Step 1: 装依赖**

在 `server/pyproject.toml` 的 `dependencies=[...]` 内加一行 `"openpyxl>=3.1",`，然后 `cd server && .venv/bin/pip install -e .` (或 `.venv/bin/pip install openpyxl`)。

- [ ] **Step 2: 写失败测试（解析器）**

```python
# server/tests/test_parser_excel.py
from app.services.sources.parser_excel import parse_1688_excel, DEFAULT_EXCEL_COLS

HEADER = ["标题", "产品ID", "产品链接", "图片链接", "价格", "是否包邮", "月销件数", "店铺名称"]
def _rows():
    return [
        HEADER,
        ["连衣裙", 891053144236, "https://detail.1688.com/offer/891053144236.html", "http://i/a.jpg", 0.56, "不包邮", 12, "义乌某厂"],
        ["缺ID但有链接", None, "https://detail.1688.com/offer/222.html", "http://i/b.jpg", "3.6", "包邮", "-", "广州店"],
        ["彻底缺ID", None, None, None, None, None, None, None],  # 跳过
    ]

def test_maps_real_headers():
    out = parse_1688_excel(_rows())
    assert len(out) == 2
    a = out[0]
    assert a["offer_id"] == "891053144236" and a["title"] == "连衣裙" and a["price"] == 0.56
    assert a["image_url"] == "http://i/a.jpg" and a["shop_name"] == "义乌某厂" and a["sales"] == 12
    assert a["detail_url"].endswith("891053144236.html")

def test_offer_id_from_link_when_missing():
    out = parse_1688_excel(_rows())
    assert out[1]["offer_id"] == "222" and out[1]["price"] == 3.6 and out[1]["sales"] is None

def test_custom_cols():
    rows = [["名称", "货号"], ["T", "9"]]
    out = parse_1688_excel(rows, {**DEFAULT_EXCEL_COLS, "title": "名称", "offer_id": "货号"})
    assert out[0]["offer_id"] == "9" and out[0]["title"] == "T"
```

- [ ] **Step 3: 运行确认失败**

Run: `cd server && .venv/bin/python -m pytest tests/test_parser_excel.py -q`
Expected: FAIL（模块不存在）

- [ ] **Step 4: 实现解析器**

```python
# server/app/services/sources/parser_excel.py
"""1688 采购助手导出 Excel → 导入商品 dict（表头名映射, 容错）。
默认列名按真实导出文件表头。cols 可覆盖(便于测试/未来插件改版)。"""
import re
from datetime import datetime, date

DEFAULT_EXCEL_COLS = {
    "title": "标题", "offer_id": "产品ID", "detail_url": "产品链接",
    "image_url": "图片链接", "price": "价格", "shop_name": "店铺名称", "sales": "月销件数",
}
_OFFER_RE = re.compile(r"offer/(\d+)")

def _price(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    m = re.search(r"[\d.]+", str(v))
    return float(m.group()) if m else None

def _int(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return int(v)
    m = re.search(r"\d+", str(v))
    return int(m.group()) if m else None

def _safe(v):
    if isinstance(v, (str, int, float, bool)) or v is None:
        return v
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    return str(v)

def _str(v):
    return None if v is None else str(v)

def parse_1688_excel(rows, cols=None):
    c = {**DEFAULT_EXCEL_COLS, **(cols or {})}
    if not rows:
        return []
    header = rows[0]
    idx = {str(h).strip(): i for i, h in enumerate(header) if h is not None}
    def cell(row, field):
        i = idx.get(c.get(field))
        return row[i] if (i is not None and i < len(row)) else None
    out = []
    for row in rows[1:]:
        if not any(v is not None for v in row):
            continue
        raw_oid = cell(row, "offer_id")
        detail = cell(row, "detail_url")
        oid = str(raw_oid).strip() if raw_oid not in (None, "") else None
        if oid and oid.endswith(".0"):  # openpyxl 可能把大整数读成 float
            oid = oid[:-2]
        if not oid and detail:
            m = _OFFER_RE.search(str(detail))
            oid = m.group(1) if m else None
        if not oid:
            continue
        raw = {h: _safe(row[i]) for h, i in idx.items() if i < len(row)}
        out.append({
            "offer_id": oid, "title": _str(cell(row, "title")), "price": _price(cell(row, "price")),
            "image_url": _str(cell(row, "image_url")), "shop_name": _str(cell(row, "shop_name")),
            "detail_url": _str(detail), "sales": _int(cell(row, "sales")), "raw": raw,
        })
    return out
```

- [ ] **Step 5: 运行确认通过（解析器）**

Run: `cd server && .venv/bin/python -m pytest tests/test_parser_excel.py -q`
Expected: PASS

- [ ] **Step 6: 写失败测试（上传接口）**

```python
# server/tests/test_import_excel_api.py —— 合成 xlsx 上传, 入库+去重; 非xlsx 400; 非admin 403
import io, pytest, openpyxl
from sqlalchemy import select, func
from app.core.security import hash_password
from app.models import User, ImportedProduct, ImportCapture

def _xlsx_bytes():
    wb = openpyxl.Workbook(); ws = wb.active
    ws.append(["标题", "产品ID", "产品链接", "图片链接", "价格", "月销件数", "店铺名称"])
    ws.append(["裙子", 891053144236, "https://detail.1688.com/offer/891053144236.html", "http://i/a.jpg", 0.56, 12, "义乌厂"])
    ws.append(["鞋", 777, "https://detail.1688.com/offer/777.html", "http://i/b.jpg", 9.9, 5, "温州店"])
    b = io.BytesIO(); wb.save(b); return b.getvalue()

async def _admin_headers(client, db_session):
    db_session.add(User(username="adm", password_hash=hash_password("p"), role="admin")); await db_session.commit()
    tok = (await client.post("/auth/login", data={"username": "adm", "password": "p"})).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}

async def _operator_headers(client, db_session):
    db_session.add(User(username="op", password_hash=hash_password("p"), role="operator")); await db_session.commit()
    tok = (await client.post("/auth/login", data={"username": "op", "password": "p"})).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}

@pytest.mark.asyncio
async def test_upload_excel(client, db_session):
    h = await _admin_headers(client, db_session)
    files = {"file": ("ALL-ExportProduct.xlsx", _xlsx_bytes(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    r = await client.post("/import/excel", files=files, headers=h)
    assert r.status_code == 200 and r.json()["parsed"] == 2
    # 再传一次 → 去重
    await client.post("/import/excel", files={"file": ("x.xlsx", _xlsx_bytes(), "application/octet-stream")}, headers=h)
    n = (await db_session.execute(select(func.count()).select_from(ImportedProduct))).scalar_one()
    assert n == 2
    caps = (await db_session.execute(select(func.count()).select_from(ImportCapture))).scalar_one()
    assert caps == 2

@pytest.mark.asyncio
async def test_reject_non_xlsx(client, db_session):
    h = await _admin_headers(client, db_session)
    r = await client.post("/import/excel", files={"file": ("a.txt", b"x", "text/plain")}, headers=h)
    assert r.status_code == 400

@pytest.mark.asyncio
async def test_operator_forbidden(client, db_session):
    h = await _operator_headers(client, db_session)
    r = await client.post("/import/excel", files={"file": ("a.xlsx", _xlsx_bytes(), "application/octet-stream")}, headers=h)
    assert r.status_code == 403
```

- [ ] **Step 7: 运行确认失败（接口）**

Run: `cd server && .venv/bin/python -m pytest tests/test_import_excel_api.py -q`
Expected: FAIL（404）

- [ ] **Step 8: 实现接口（扩 importer.py）**

顶部加：
```python
import io
from fastapi import UploadFile, File
from app.services.sources.parser_excel import parse_1688_excel, DEFAULT_EXCEL_COLS
```
加端点：
```python
@router.post("/excel")
async def ingest_excel(file: UploadFile = File(...), s: AsyncSession = Depends(get_session), _: User = Depends(require_role("admin"))):
    if not (file.filename or "").lower().endswith(".xlsx"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "仅支持 .xlsx 文件")
    data = await file.read()
    try:
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        ws = wb.active
        rows = [list(r) for r in ws.iter_rows(values_only=True)]
        wb.close()
    except Exception:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "无法解析 Excel 文件")
    parsed_rows = parse_1688_excel(rows, DEFAULT_EXCEL_COLS)
    headers = [str(h) for h in (rows[0] if rows else []) if h is not None]
    cap = ImportCapture(platform="ali1688", keyword=file.filename,
                        raw={"headers": headers, "row_count": max(0, len(rows) - 1)}, item_count=len(parsed_rows))
    s.add(cap); await s.flush()
    parsed = 0
    for r in parsed_rows:
        exists = (await s.execute(select(ImportedProduct).where(
            ImportedProduct.platform == "ali1688", ImportedProduct.offer_id == r["offer_id"]))).scalar_one_or_none()
        if exists:
            continue
        s.add(ImportedProduct(platform="ali1688", offer_id=r["offer_id"], title=r["title"], price=r["price"],
                              image_url=r["image_url"], shop_name=r["shop_name"], detail_url=r["detail_url"],
                              sales=r["sales"], raw=r["raw"], capture_id=cap.id))
        parsed += 1
    await s.commit()
    return {"capture_id": cap.id, "captured": len(parsed_rows), "parsed": parsed, "skipped": len(parsed_rows) - parsed}
```

- [ ] **Step 9: 运行确认通过 + 回归**

Run: `cd server && .venv/bin/python -m pytest tests/test_parser_excel.py tests/test_import_excel_api.py -q && .venv/bin/python -m pytest -q`
Expected: PASS，0 warnings

- [ ] **Step 10: 提交**

```bash
git add server/pyproject.toml server/app/services/sources/parser_excel.py server/app/api/importer.py server/tests/test_parser_excel.py server/tests/test_import_excel_api.py
git commit -m "feat(import): openpyxl + Excel 解析器 + POST /import/excel 上传接口"
```

---

### Task 2: 前端上传按钮 + nginx 上传大小

**Files:**
- Modify: `web/src/api/importer.ts`（`uploadExcel`）
- Modify: `web/src/pages/ImportedProducts.tsx`（上传按钮）
- Modify: `web/nginx.conf`（`client_max_body_size`）
- Test: `web/src/pages/ImportedProducts.test.tsx`（追加）

**Interfaces:**
- Consumes: `POST /import/excel`（Task 1）。

- [ ] **Step 1: 写失败测试**

```tsx
// 追加到 ImportedProducts.test.tsx —— 上传按钮存在
test("显示上传 Excel 按钮", async () => {
  render(<ImportedProducts />);
  expect(await screen.findByText(/上传 Excel/)).toBeInTheDocument();
});
```
> 该文件已 `vi.mock("../api/importer", ...)`；给 mock 补上 `uploadExcel: vi.fn()`。

- [ ] **Step 2: 运行确认失败**

Run: `cd web && npx vitest run src/pages/ImportedProducts`
Expected: FAIL

- [ ] **Step 3: 实现 api**

`web/src/api/importer.ts` 加：
```ts
export const uploadExcel = (file: File) => {
  const fd = new FormData();
  fd.append("file", file);
  return api.post("/import/excel", fd).then((r) => r.data);
};
```

- [ ] **Step 4: 实现上传按钮**

`ImportedProducts.tsx`：import `Upload` from antd、`uploadExcel` from api；`Card` 的 `extra` 改为并排的上传 + 刷新：
```tsx
import { Card, Table, Image, Typography, Button, message, Upload, Space } from "antd";
import { listImported, uploadExcel } from "../api/importer";
// ...
const onUpload = async (file: File) => {
  try { const r = await uploadExcel(file); message.success(`导入 ${r.parsed} 条(去重跳过 ${r.captured - r.parsed})`); load(); }
  catch (e: any) { message.error(e?.response?.data?.detail || "导入失败"); }
  return false; // 阻止 antd 默认上传
};
// Card extra:
extra={
  <Space>
    <Upload accept=".xlsx" showUploadList={false} beforeUpload={onUpload}>
      <Button type="primary">上传 Excel（1688 采购助手导出）</Button>
    </Upload>
    <Button onClick={load}>刷新</Button>
  </Space>
}
```

- [ ] **Step 5: nginx 上传大小**

`web/nginx.conf`：给 `/api/` location 加 `client_max_body_size 20m;`：
```
location /api/ { client_max_body_size 20m; proxy_pass http://api:8000/; proxy_set_header X-Real-IP $remote_addr; }
```

- [ ] **Step 6: 运行测试 + build**

Run: `cd web && npx vitest run src/pages/ImportedProducts && npm run build`
Expected: PASS + build 成功

- [ ] **Step 7: 提交**

```bash
git add web/src/api/importer.ts web/src/pages/ImportedProducts.tsx web/src/pages/ImportedProducts.test.tsx web/nginx.conf
git commit -m "feat(web): 导入商品页上传 Excel 按钮 + nginx 上传大小放宽"
```

---

## 收尾（全部任务后）
- 后端 `pytest -q` 0 warnings + 前端 build/vitest。
- 重建 docker（api 装 openpyxl + web 更新 nginx）：`WEB_PORT=18080 DB_PORT=15432 REDIS_PORT=16379 API_PORT=18000 docker compose up -d --build api web`。
- 交给用户：上传 `ALL-ExportProduct-2026_7_20 23_28_27.xlsx` → 「导入商品」应出现 60 个商品。

## 自查
- 覆盖 spec：依赖+解析器+接口(T1)、前端上传+nginx(T2)。
- 类型/命名一致：`parse_1688_excel`/`DEFAULT_EXCEL_COLS`、`/import/excel`、`uploadExcel` 一致。
- 复用现有表无迁移；raw JSON 安全(datetime→str)；去重 (platform, offer_id)。
- 无占位符。

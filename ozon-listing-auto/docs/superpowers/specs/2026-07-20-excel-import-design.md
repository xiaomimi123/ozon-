# 设计文档：Excel 导入货源（1688 采购助手导出 → 上传入库）

> 日期：2026-07-20。用户决策：用官方免费「1688 采购助手」插件抓取+导出 Excel（免 AdsPower/socks5/自建扩展），我们做「上传 Excel」入库。列映射按真实导出文件配准。

## 1. 背景

- 官方插件是第三方、不可改，无法主动回传；唯一出口是**导出 Excel**。桥接 = 导出 → 上传 → 入库。
- 已拿到真实导出样本 `ALL-ExportProduct-2026_7_20 23_28_27.xlsx`（Sheet1，61 行=1 表头+60 商品，17 列，表头中文）。
- 复用已建的 `ImportCapture`/`ImportedProduct` 表（1688 采集 PoC），**无需迁移**。

## 2. 真实表头 → 字段映射（配准）

17 列表头：标题 / 产品ID / 产品链接 / 图片链接 / 价格 / 是否包邮 / 销售额 / 起批量 / 起批量运费 / 月销件数 / 累计销售件数 / 复购率 / 48h发货率 / 最早上架时间 / 最新更新时间 / 店铺名称 / 店铺资质。

默认映射（按**表头名**匹配）：
| 字段 | Excel 列名 |
|---|---|
| title | 标题 |
| offer_id | 产品ID |
| detail_url | 产品链接 |
| image_url | 图片链接 |
| price | 价格 |
| shop_name | 店铺名称 |
| sales | 月销件数 |

其余列不单独建字段，整行原文存 `ImportCapture.raw`/`ImportedProduct.raw`，以后要用再加。

## 3. 范围

**目标**：「导入商品」页上传 1688 采购助手导出的 .xlsx → 解析入库 → 列表展示。

**范围**
1. 加依赖 `openpyxl`（读 .xlsx，只读模式）。
2. 后端 `POST /import/excel`（`UploadFile`，`require_role("admin")`）：读首行表头 → 按表头名映射（默认见 §2，可经 sources 配置覆盖）→ 逐行解析 → 存 `ImportCapture`(platform=ali1688, keyword=文件名, raw={headers, rows}) + 逐行 upsert `ImportedProduct`（按 (platform, offer_id) 去重）→ 返回 `{captured, parsed, skipped}`。
3. 前端「导入商品」页加「上传 Excel（1688 采购助手导出）」按钮（antd `Upload`，`beforeUpload` 手动 POST multipart）→ 成功 toast + 刷新。

**不做（YAGNI）**：Ozon 产品导出（同法可扩，记为后续）；多 sheet；尺寸/包邮/复购率等附加字段建列；AdsPower/自建扩展（已建，搁置）。

## 4. 解析器 `parse_1688_excel`

`server/app/services/sources/parser_excel.py`：
```
DEFAULT_EXCEL_COLS = {
  "title": "标题", "offer_id": "产品ID", "detail_url": "产品链接",
  "image_url": "图片链接", "price": "价格", "shop_name": "店铺名称", "sales": "月销件数",
}
def parse_1688_excel(rows: list[list], cols: dict) -> list[dict]:
    # rows[0]=表头; 建 表头名→列索引; 逐数据行按 cols 映射取值(缺列→None);
    # price→float(容错), sales→int(容错), offer_id→str;
    # offer_id 缺失时从 detail_url 提取 offer/(\d+); 仍无则跳过该行; 返回 {offer_id,title,price,image_url,shop_name,detail_url,sales,raw(该行 header→值 dict)}
```
- 复用/仿 parser_import 的 `_price`/`_int`。列映射可经 sources 配置 `import_excel_*_col` 覆盖（防插件改版），默认 §2；同"路径可配+存原始"理念。

## 5. 后端 API（扩 `app/api/importer.py`）

`POST /import/excel`：
- `file: UploadFile`；`require_role("admin")`（登录态，非 import_token——这是页面内上传、走 JWT）。
- 校验扩展名 `.xlsx`；`openpyxl.load_workbook(BytesIO(await file.read()), read_only=True, data_only=True)`；取 active sheet 全部行。
- 读 sources 配置的列覆盖 → `parse_1688_excel(rows, cols)` → 存 capture + 去重入库 → 返回统计。
- 大小：nginx 若默认 1MB 需放宽 `client_max_body_size 10m`（Excel 一般小；在 web/nginx.conf 加）。

## 6. 前端

- `web/src/api/importer.ts` 加 `uploadExcel(file: File)`：`FormData` + `api.post("/import/excel", fd)`（axios 自动 multipart）。
- `ImportedProducts.tsx`：标题栏加 antd `Upload`（`accept=".xlsx"`, `showUploadList=false`, `beforeUpload`→`uploadExcel`→toast「导入 N 条」+`load()`，return false 阻止默认上传）。按钮文案「上传 Excel（1688 采购助手导出）」。

## 7. 测试
- 后端 TDD：用**合成 .xlsx**（openpyxl 写一个含 §2 表头 + 2 行 + 1 行缺产品ID 的临时文件）测 `parse_1688_excel`（映射正确、缺产品ID 从链接提取、price/sales 类型）；`POST /import/excel` 上传 → capture+去重入库；非 .xlsx → 400；非 admin → 403。
- （可选）用真实样本文件路径做一个 `@pytest.mark.live` 或跳过的健壮性测试——不入 CI（文件在用户机器）。
- 前端 Vitest：上传按钮渲染 + `beforeUpload` 调 `uploadExcel`（mock）。
- 后端 0 warnings；前端 build + vitest。

## 8. 验收
1. admin 在「导入商品」页上传该 .xlsx → 60 个商品入库、列表可见（标题/价/图/店铺/销量/链接对）。
2. 重复上传同文件 → 按产品ID 去重、不翻倍。
3. 缺产品ID 的行从产品链接提取 ID，提不到才跳过。
4. 原始行存 `ImportCapture.raw` 供校准/追溯。
5. 后端 0 warnings + 前端 build/vitest。

## 9. 风险
| 风险 | 应对 |
|---|---|
| 插件改版换表头 | 表头名映射 + 可配 override + 存原始行，改配置即适配 |
| Excel 较大/nginx 限制 | `client_max_body_size` 放宽；openpyxl read_only 省内存 |
| 价格/销量含非数字(如"运费3.6元起"/"-") | `_price`/`_int` 正则容错→None |
| 产品ID 缺失 | 从产品链接 offer/(\d+) 提取；仍无跳过 |

# 设计文档：图搜采集核心（浏览器截流 → supply_candidates）

> 日期：2026-07-21。全自动图搜闭环（B 路：浏览器截流）子项目①。用户已定：走 B、甲方提供 AdsPower/socks5/CapSolver。
> 目标：让"Ozon 主图 → 1688 拍立淘图搜 → 候选入 supply_candidates → 现有五维评分/上架"这条**产品说明书主线**跑起来，绕开图搜签名逆向。

## 1. 背景与复用（已核对代码）

现有链路（`app/workers/matcher.py`）：每个 Ozon 商品 → `provider.image_search(main_image_url)` → `parse_offers` → `dedup_and_upsert(session, task_id, product_id, dtos, embedder)` 写 `supply_candidates`（CLIP 聚簇去重 + 幂等 upsert，唯一约束 task/product/platform/offer）。`parse_offers`（`parser_ali.py`）已按 Zhui-CN 字段把图搜响应解析成 `SupplyCandidateDTO`（offerId/价/阶梯价/起批量/供应商信用/评分等）。

**B 路只替换"如何拿到图搜响应"**：不再由 `Ali1688Provider` 自己发签名请求（需逆向），而是**浏览器(AdsPower+Playwright)真实触发拍立淘、截获返回 JSON → POST 给后端 → 后端 `parse_offers + dedup_and_upsert`**。后端解析与入库**全部复用**，无需新解析器/新表。

## 2. 目标与范围

**目标**：跑通"给定 Ozon 商品主图 → 浏览器图搜 → 候选写入该商品的 supply_candidates → 进现有评分/上架"。

**范围**
1. 后端 `POST /import/image-search`（X-Import-Token 鉴权）：body `{task_id, ozon_product_id, payload}` → `parse_offers`(路径用 sources 配置 `ali1688_offer_list_path`) → `dedup_and_upsert` → 存一条 `ImportCapture`(可追溯/校准) → 返回 `{inserted, skipped, clusters, captured}`。
2. 编排脚本 `scripts/collect_1688_image_search.py`（Playwright + AdsPower）：下载 Ozon 主图 → 开 1688 拍立淘 → 上传图 → Playwright `page.on("response")` 截获图搜响应 → POST 上述端点。**用户 live 验证。**

**不做（YAGNI）**：自动调度（子项目②）、CapSolver/session 刷新（子项目③）、拼多多、关键词图搜以外的入口、前端页面（候选已有审核台/评分台展示）。

## 3. 后端 `POST /import/image-search`（扩 `app/api/importer.py`）

```
body ImageSearchIn { task_id: int, ozon_product_id: int, payload: dict }
```
- `X-Import-Token` 头校验（复用 `sources.import_token`，fail-closed；同 /import/offers）。
- 校验 `ozon_product_id` 存在且属于 `task_id`（否则 404）。
- `conf = get_source_conf(s)`；`dtos = parse_offers(payload, conf["ali1688_offer_list_path"])`。
- `embedder = get_embedder(settings.embedder)`（mock/clip，同 matcher）。
- `result = await dedup_and_upsert(s, task_id, ozon_product_id, dtos, embedder)`。
- 存 `ImportCapture(platform="ali1688", keyword=f"图搜:product={ozon_product_id}", raw=payload, item_count=len(dtos))`（追溯/校准原始响应）。
- `await s.commit()`；返回 `{**result, "captured": len(dtos)}`。
- 复用：`parse_offers`(parser_ali)、`dedup_and_upsert`(candidate_ingest)、`get_embedder`(embedding.factory)、`get_source_conf`(sources.conf)、`OzonProduct`/`SupplyCandidate`/`ImportCapture` 模型。

## 4. 编排脚本 `scripts/collect_1688_image_search.py`

- 参数：`--api`(AdsPower Local API)、`--user-id`(AdsPower 环境)、`--backend`(后端 base，如 http://host/api)、`--token`(import_token)、`--task-id`、`--product-id`、`--image-url`（Ozon 主图，脚本下载）或 `--image-file`、`--dwell`。
- 流程：下载主图到临时文件 → AdsPower `browser/start` 取 CDP → Playwright `connect_over_cdp` → 打开 1688 拍立淘上传页 → **定位文件 input，`set_input_files` 上传主图** → 等待 → 期间 `page.on("response")` 命中图搜接口(URL 含可配子串)时缓存其 JSON → `browser/stop` → 把缓存的响应 `POST {backend}/import/image-search` body `{task_id, ozon_product_id: product_id, payload}` 头 `X-Import-Token`。
- 附 `scripts/README-image-search.md`：AdsPower 建环境/挂 socks5/登录 1688、拍立淘上传页 URL 与文件 input 选择器（**随 1688 页面变，需按实际调**）、遇滑块人工处理、合规见选型报告 §8。**此脚本 live 由用户验证；拍立淘上传 UI 自动化是最靠真实环境的一步。**
- **不含任何验证码绕过/反检测代码**（红线）。

## 5. 测试

- **后端（TDD，fixture）**：seed CollectTask + OzonProduct；用一份 Zhui-CN 结构的图搜响应 fixture（`data.offerList` 含 2 个 offer）POST `/import/image-search`（正确 token）→ 断言 `inserted==2` 且 `supply_candidates` 有 2 条、`ozon_product_id`/`task_id` 关联正确；重复 POST → 幂等去重（inserted 0/skipped 2）；token 错 → 401；product 不属于 task → 404；每次存 ImportCapture。用 mock embedder（`settings.embedder` 默认 mock）。
- **不自动化**：Playwright 脚本（README 手动验证）。
- 后端 0 warnings。

## 6. 验收
1. POST 图搜响应 → 该 Ozon 商品的 supply_candidates 入库、可进现有评分（`/score`）/审核台。
2. 幂等（重复不翻倍）；token 鉴权；product/task 关联校验；原始响应存 ImportCapture。
3. 脚本能驱动 AdsPower 拍立淘上传主图并截获响应回传（用户 live 验证）。
4. 后端 0 warnings + 复用 parse_offers/dedup_and_upsert 无重复造轮子。

## 7. 风险
| 风险 | 应对 |
|---|---|
| 图搜响应结构与默认路径不符 | `ali1688_offer_list_path` 可配 + 存 ImportCapture 原始响应，按实际校准 |
| 拍立淘上传 UI 自动化随页面变 | 选择器/URL 参数化写 README；用户按实际调；脚本 live 验证 |
| Claude 无法 live 验证图搜 | 后端 fixture TDD；图搜 live 由用户验证并回传首个 raw 校准路径 |
| 触发滑块 | 本子项目不解验证码；人工/后续 CapSolver（子项目③）|
| product 不属于 task 误写 | 端点校验 ozon_product 属于 task |

# 设计文档：1688 关键词搜索采集 PoC（自建扩展 + AdsPower + 路径可配解析）

> 日期：2026-07-20。子项目：1688/拼多多采集的第一步 PoC。用户已定：AdsPower 无头自动 + 关键词搜索列表 + 先落独立「导入商品」表。
> 关键约束：**Claude 造全部代码 + 用 fixture 做离线 TDD；AdsPower/socks5/真号 live 链路由用户在自己环境验证。** Claude 不亲自跑绕检测抓取、不解验证码。

## 1. 背景与思路

- 采集内部接口响应结构**无法从文档钉死**（onebound `items.item[]`：title/price/num_iid/pic_url/seller_nick；官方 API `result.products[]`：productId/subject/price；扩展拦截的 h5api/mtop 内部响应是第三种）。
- 因此：**解析器路径可配 + 每次存原始 payload**，首次真跑后按真实响应在配置里校准字段路径（不改代码），复用项目既有 `ali1688_offer_list_path` 可配模式。
- 扩展 content-script 跑在**真实登录页面**里、拦截**页面自身发出的搜索接口响应**（天然带合法签名/anti_content）→ 绕开签名逆向与大部分机器人检测。

## 2. 目标与范围

**目标**：跑通「AdsPower 无头开 1688 搜索页 → 自建扩展拦截搜索接口 JSON → 回传后端 → 路径可配解析 → 入『导入商品』表 → 前端列表可见」，并存原始 payload 供校准。

**范围**
1. **扩展**（MV3，新 `extension/` 目录）：拦截 1688 搜索接口响应 → POST 到后端（可配后端地址 + token）。
2. **后端**：`ImportedProduct` + `ImportCapture` 两表；路径可配解析器 `parse_1688_search`；`POST /import/offers`（token 鉴权，存 raw + 解析入库）；`GET /import/offers`、`GET /import/captures`（admin）。
3. **前端**：「导入商品」页（表格）+ 菜单 adminOnly + 路由。
4. **AdsPower 编排脚本**：Local API 启动带 socks5+扩展+登录态环境 → Playwright(CDP) 导航到关键词搜索页。交付但由用户 live 验证。

**不做（YAGNI）**：拼多多、图搜/详情、CapSolver 打码（触发验证码先人工）、接入现有 SupplyCandidate/匹配评分流（先独立表看效果）、扩展自动上架。

## 3. 扩展（MV3，`extension/`）

- `manifest.json`：`manifest_version:3`；`content_scripts` 匹配 `*://*.1688.com/*`（`run_at: document_start`）；`host_permissions` 含后端地址；`web_accessible_resources` 暴露注入脚本；`permissions:["storage","scripting"]`；options 页。
- `interceptor.js`（**主世界 MAIN**）：monkeypatch `window.fetch` 与 `XMLHttpRequest.prototype.open/send`；命中搜索接口（URL 含可配子串，默认匹配 1688 搜索关键字如 `offer/search` / `h5api` / `pcSearch`，PoC 用宽松包含匹配 + 后端二次校验）→ 克隆响应 JSON → `window.postMessage({source:"ozon-collector", payload})`。
- content script（隔离世界）：`document_start` 时用 `<script src=chrome.runtime.getURL('interceptor.js')>` 注入主世界；监听 `window.postMessage` → 转发给 background。
- background service worker：收到 payload → `fetch(backendUrl + '/import/offers', {method:POST, headers:{'X-Import-Token': token}, body: JSON})`。
- options 页：填**后端地址** + **导入 token**（存 `chrome.storage`）。
- 附 `extension/README.md`：如何在 Chrome/AdsPower 加载未打包扩展、填 options、验证。

> 扩展 JS 不纳入本项目 Python/Vitest 自动化测试（浏览器内运行）；逻辑写清 + README 手动验证说明。

## 4. 后端

### 4.1 模型（Alembic 迁移 0008）
- `ImportCapture`：`id, platform("ali1688"), keyword(nullable), raw(JSONB), item_count(int), created_at`。**每次 ingest 都存**（含解析 0 条的，供校准）。
- `ImportedProduct`：`id, platform, offer_id(str), title(nullable), price(Numeric nullable), image_url(nullable), shop_name(nullable), detail_url(nullable), sales(int nullable), raw(JSONB, 该商品项原文), capture_id(FK), created_at`；唯一约束 `(platform, offer_id)`（重复 offer_id 跳过/更新）。

### 4.2 路径可配解析器 `app/services/sources/parser_import.py`
```
DEFAULT_PATHS = {
  "list": "data.data.offerList",        # 内部 h5api 常见；首跑后按真实响应校准
  "offer_id": "offerId",
  "title": "information.name",
  "price": "tradePrice",
  "image": "image.imgUrl",
  "shop": "company.name",
  "detail_url": "detailUrl",
  "sales": "sale",
}
def parse_1688_search(payload: dict, paths: dict) -> list[dict]:
    # 按 paths["list"] 点路径取列表(缺失→[]); 逐项按各字段点路径取值(缺失→None); offer_id 缺失的项跳过
```
- 点路径工具支持 `a.b.c` 与数字下标 `a.0.b`（复用/仿 `parse_offers` 的取值方式）。
- paths 从 `sources` 配置类覆盖（键 `import_1688_list_path` 等），缺省用 DEFAULT_PATHS → **校准=改配置**。
- 参考：onebound 结构 `items.item[]`(title/price/num_iid/pic_url/seller_nick)、官方 `result.products[]`(productId/subject/price) 记入注释，便于对不同响应快速改路径。

### 4.3 API `app/api/importer.py`（prefix `/import`）
- `POST /import/offers`：header `X-Import-Token` 校验（与 `sources` 配置 `import_token` 比对，不匹配 401）；body=原始搜索响应 JSON（+可选 keyword）→ 存 `ImportCapture` → `parse_1688_search` → 逐 offer upsert `ImportedProduct`（按 (platform,offer_id) 去重）→ 返回 `{capture_id, captured, parsed}`。**无需登录态**（扩展用 token），但仅接受配置了 token 时。
- `GET /import/offers?platform=&limit=`（`require_role("operator")`）→ 列表。
- `GET /import/captures?limit=` 与 `GET /import/captures/{id}`（`require_role("admin")`）→ 看原始 payload（校准用）。

## 5. 前端「导入商品」页
- `web/src/api/importer.ts`：`listImported()`、`listCaptures()`、`getCapture(id)`。
- `web/src/pages/ImportedProducts.tsx`（route `/imported`，菜单 adminOnly「导入商品」）：表格列 平台/图/标题/价/店铺/销量/detail 链接/创建时间（`scroll={{x:"max-content"}}`）。顶部说明「数据来自采集扩展；若列表空但有采集记录，去『采集原始记录』核对字段路径并在货源配置调整」。
- （可选轻量）原始记录入口：一个按钮弹 Modal 显示最近 capture 的 item_count 与 raw 预览，供校准。

## 6. AdsPower 编排脚本 `scripts/collect_1688_adspower.py`
- 读环境变量/参数：AdsPower Local API 地址（默认 `http://local.adspower.net:50325`）、`user_id`（AdsPower 环境 ID）、关键词、页数。
- 流程：调 AdsPower `GET /api/v1/browser/start?user_id=...` 取 `ws.puppeteer`(CDP 端点) → Playwright `connect_over_cdp` → 打开 `https://s.1688.com/selloffer/offer_search.htm?keywords=<kw>`（或 h5 搜索页）→ 等待若干秒让扩展拦截回传 → 翻页 → `GET /api/v1/browser/stop`。
- 注：socks5、登录态 Cookie、扩展加载均在 **AdsPower 环境内配置**（脚本不管），脚本只负责启动+驱动导航。
- 附 `scripts/README-collect.md`：AdsPower 里如何建环境、挂 socks5、装扩展、导入 1688 登录 Cookie、跑脚本、遇滑块人工处理。**此脚本由用户 live 验证。**

## 7. 测试

- **后端（TDD，fixture）**：
  - `parse_1688_search`：用一份**符合 DEFAULT_PATHS 结构的合成 fixture** 断言解析出 offer 列表与各字段；另用**不同结构 fixture + 覆盖 paths** 断言路径可配生效；list 路径缺失→[]；offer_id 缺失项跳过。
  - `POST /import/offers`：token 正确→存 capture + 解析入库 + 去重（同 offer_id 不重复）；token 错→401；解析 0 条也存 capture。
  - `GET /import/offers`、`captures`：鉴权 + 返回。
  - 迁移 0008 建表。
- **前端（Vitest）**：ImportedProducts 页渲染表格（mock `../api/importer`）。
- **不自动化**：扩展 JS、AdsPower 脚本（README 手动验证）。
- 后端 0 warnings；前端 build + vitest 通过。

## 8. 验收标准
1. 扩展可在 Chrome/AdsPower 加载，填后端地址+token 后，浏览 1688 搜索页时把搜索响应 POST 到后端（用户手动验证一次）。
2. 后端存下 `ImportCapture`（原始 payload）+ 按配置路径解析出 `ImportedProduct`；解析 0 条时 capture 仍在、可查。
3. 「导入商品」页能看到抓到的商品；「采集原始记录」可查 raw 供校准。
4. AdsPower 脚本能启动环境并导航到关键词搜索页（用户 live 验证）。
5. 后端 0 warnings + 前端 build/vitest 通过；解析器路径可配（改配置即适配真实响应）。

## 9. 风险与降级
| 风险 | 应对 |
|---|---|
| 真实响应结构未知 | 路径可配 + 每次存 raw；首跑后改配置校准，不改代码 |
| 扩展没抓到/抓错接口 | 宽松 URL 包含匹配 + 后端存所有 capture；核对 raw 调匹配子串与路径 |
| Claude 无法 live 验证 | 明确分工：离线管道 fixture TDD；live 由用户验证并回传首个 raw |
| 触发滑块验证码 | 本 PoC 不解验证码；人工处理；后续再评估 CapSolver |
| ingest 无登录态被滥用 | X-Import-Token 校验；仅内网/自用；token 存加密配置 |
| ToS/合规 | 独立小号 + 限速 + 换号；勿主力号；见采集选型报告 §8 |

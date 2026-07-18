# 设计文档：真实爬虫接入（composer-api）+ 爬虫/Seller 配置页

> Ozon 跟卖/铺货自动化系统 v3.0，M1-M7 完成后的**去 mock 化第一步**。
> 版本：v1 ｜ 日期：2026-07-18 ｜ 依据：`开发文档v3-*.md` §5.1(采集/反爬)、现有 OzonComposerProvider/parser/collector/settings 代码、用户确认。

## 1. 目标与范围

**目标** = 让系统能用真实 Ozon 前台数据采集（去 mock 化第一步），爬虫凭据（cookie/代理）与 Ozon Seller provider 切换都做进后台配置页。

**四块工作：**
1. **爬虫配置页**：`GET/PUT /settings/crawler`（admin，Fernet 加密）填 cookie + proxy（+ 超时/间隔/重试）；前端配置页。
2. **provider 配置驱动接入**：collector 读 `settings/crawler` 构造 `OzonComposerProvider(cookie, proxy)`（现为空构造，接不上真实凭据）。
3. **反爬硬化**：307/3xx 反爬识别 + cookie 头注入 + 错误分类（cookie 失效/被拦→可操作提示），退避重试，collector 不静默。
4. **Seller provider 切换搬进配置页**：`/settings/system` 存 `ozon_seller_provider`(mock|real)，`run_publish`/`run_publish_tick` 读配置而非 env；配合现有 Shops 凭据页，UI 即可切真实上架。
5. **parser 对齐真实响应**（用用户提供的真实样本夹具）+ `@pytest.mark.live` 真实抓取测试（默认跳过）。

**明确不做**：登录态自动获取 cookie（手动从浏览器复制，业界常规）；验证码/CF 挑战自动破解（靠有效 cookie + 代理规避）；类目树真实化（M6 mock 够跑，仅留复用口）。

**范围外/后置**：多 cookie/代理轮换池（先单套够用）；1688/拼多多真实货源（另开）；RealCategoryTree/RealOzonSeller 端点最终 live 校正。

## 2. 配置存储与接口

### 2.1 爬虫配置（`/settings/crawler`，admin，仿 M6 imagegen 范式）
- 字段：`cookie`(str, Fernet secret, 浏览器 Cookie 头原文)、`proxy`(str, secret, 如 `http://user:pass@host:port`)、`timeout`(float, 默认 20)、`min_delay`/`max_delay`(请求间隔抖动秒, 默认 0.3/1.0)、`max_retries`(int, 默认 4)。
- GET 时 cookie/proxy 脱敏 `***`，其余明文；PUT 时 cookie/proxy `is_secret=True`；**cookie/proxy 留空不覆盖已存值**（同 imagegen 修复）。存 `app_settings.crawler`。缺省 `DEFAULT_CRAWLER`。

### 2.2 系统/Provider 配置（`/settings/system`，admin）
- 字段：`ozon_seller_provider`(`mock`|`real`, 默认 `mock`)。非 secret，明文存取。存 `app_settings.system`。
- `run_publish`/`run_publish_tick`：先读 `settings/system.ozon_seller_provider`，读不到回退 env `settings.ozon_seller_provider`（向后兼容）。

> per-task 采集 provider（mock/composer/apify）仍建任务时选（现有 UI）；`/settings/system` 只管全局 Seller real/mock。

## 3. provider 接入 + 反爬硬化

### 3.1 配置驱动构造（`services/ozon_market/factory.py` + collector）
- 新增 `async def build_ozon_provider(session, name) -> OzonMarketProvider`：`composer` 读 `settings/crawler`（cookie/proxy/timeout/delay/retries）构造 `OzonComposerProvider(...)`；`mock`/`apify` 不变。
- 抽 `async def get_crawler_conf(session) -> dict`（cookie/proxy/timeout/…）供 build 及后续 RealCategoryTree 复用。
- `collector.run_collect_core`：`get_provider(task.provider)` → `await build_ozon_provider(s, task.provider)`（已有 session）。`get_provider`（同步）保留给 mock/测试。

### 3.2 `OzonComposerProvider` 硬化（`composer.py`）
- **cookie 注入**：接受原始 Cookie 头字符串（用户直接复制，无需拆 dict）→ 请求头 `Cookie: <原文>`；同时兼容 dict。构造签名扩展 `cookie: str|dict|None`、`proxy`、`timeout`、`min_delay`/`max_delay`、`max_retries`。
- **307/3xx 反爬识别**：`follow_redirects=False`；`307/301/302` 与 `429/403` 统一视为反爬信号 → 指数退避重试；耗尽抛 `CrawlerBlockedError("疑似反爬/cookie 失效，请在爬虫配置更新 cookie 或代理")`。
- **UA/间隔**：沿用 UA 轮换 + 抖动（间隔从配置读）。
- **错误分类**：网络异常/超时→重试；4xx(非 403/429)/解析失败→明确错误不无限重试。
- collector 捕获 `CrawlerBlockedError` → 任务 `status=failed` + `stats.error` 记可操作提示，不静默。

### 3.3 复用口
`get_crawler_conf` 抽为公共函数，为后续 `RealCategoryTree`（composer `categoryChildV3`）复用 cookie/proxy 留口。本次不做类目树真实化。

## 4. parser 对齐真实响应

### 4.1 现状
`parse_search_widgets` 遍历 `payload["widgetStates"]`，对每 widget 尝试 `json.loads`，从 item 取 `sku/title/price` —— 盲写猜测。真实商品数据在特定 widget（`searchResultsV2*`/`tileGrid*`/`skuGrid*` 等），字段名/嵌套需按真实响应校准。

### 4.2 对齐方案（用真实样本）
- 真实响应存夹具 `tests/fixtures/composer_search.json`（+ 类目/卖家各一份，覆盖三入口）。
- 按样本重写 parser：按 key 前缀容错定位商品 widget；抽取 SKU、标题、price(含 `cardPrice`/`price`)、月销、评分、评论数、主图/图集、product_url、变体(parent_sku) → `OzonProductDTO`。
- 只改 `parser.py`（解析/请求层已分离）。单测喂夹具断言条数与字段（真实数据驱动）。

### 4.3 样本暂缺兜底
先按公开结构 + 样本覆盖部分写；`@pytest.mark.live` 真实抓取（cookie 从配置/env）默认跳过，用户带 cookie 本地跑按报错迭代。

## 5. 前端 + 测试 + 验收 + 风险

### 5.1 前端
- **爬虫配置页** `web/src/pages/settings/CrawlerSettings.tsx`：cookie(多行 Password/TextArea 脱敏)、proxy、timeout/min_delay/max_delay/max_retries → PUT `/settings/crawler`；提示"cookie 从浏览器 devtools 复制"。
- **系统设置**：Seller provider mock/real 单选 → PUT `/settings/system`。
- `api/crawler.ts` `api/system.ts`；路由 + 菜单。

### 5.2 测试（可测部分 + live）
- crawler/system 配置：Fernet 脱敏、留空不覆盖、save/read（集成测）。
- `build_ozon_provider`：composer 读配置构造，cookie/proxy 传入（monkeypatch httpx 断言 `Cookie` 头 + 代理）。
- 硬化：307/403/429 → 退避重试 → 耗尽抛 `CrawlerBlockedError`；collector 捕获置 failed + 提示（mock httpx，无真实网络/无真实 sleep：注入/monkeypatch）。
- **parser 夹具测试（核心）**：真实样本 → 抽出预期商品/字段。
- seller 切换：`run_publish` 读 `settings/system` 选 real/mock。
- `@pytest.mark.live`（默认跳过）：真实 composer 抓取。
- 前端：CrawlerSettings + 系统设置渲染（Vitest+mock）。
- pytest 0 warnings；非 live 全 mock。

### 5.3 验收标准
1. 后台爬虫配置页填 cookie+proxy（Fernet/脱敏/留空不覆盖）。
2. 建 composer 任务 → collector 读配置带 cookie/proxy 真实请求 → parser 抽出真实商品入库（样本夹具验证解析；真实网络走 live）。
3. 反爬（307/403/429）退避重试 + cookie 失效可操作提示 + 任务 failed 不静默。
4. Seller real/mock 配置页切换生效（`run_publish` 按配置选）。
5. 非 live 0 warnings + README/docs + 前端 build；`@live` 真实抓取用例齐备。

### 5.4 风险与降级
| 风险 | 应对 |
|---|---|
| 真实 widget 结构与盲写差异大 | 优先用真实样本夹具对齐；解析层独立可快速改；live 迭代 |
| cookie 时效短/频繁失效 | 配置页随时更新；失效给可操作提示；后续 cookie 池轮换 |
| Ozon 地域限制/CF 拦截 | 配代理(RU 出口)；307/403 退避；耗尽明确报错不假装成功 |
| 代理不稳/慢 | 超时+重试可配；失败任务可续跑(现有断点续传) |
| composer 端点非官方失效 | 请求层版本化(_ENDPOINT 常量)；解析层分离；live 校正 |

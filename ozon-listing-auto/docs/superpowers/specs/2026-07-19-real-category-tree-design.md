# 设计文档：子项 B — RealCategoryTree（类目树真实化）

> 去 mock 化子项 B（见《去mock化-真实集成总规划.md》）。日期：2026-07-19。
> 依据：现有 `MockCategoryTree`/`category_map`、`OzonComposerProvider`(请求层)、`get_crawler_conf`、`/settings/system`、开发文档 §5.1(categoryChildV3)。

## 1. 目标与范围

**目标** = 自建分支类目树从 M6 mock 固定小树切到真实 Ozon 全量类目树（`composer-api categoryChildV3`）。

**范围：**
1. `RealCategoryTree`（`services/ozon_market/category_tree_real.py`）：`list_children(*, parent_id)` 调 `categoryChildV3?categoryId=<parent_id 或根>`，复用 composer 请求层（cookie 头/UA/退避/CrawlerBlockedError），解析 `[{id,name,path,leaf}]`；结构**实现时浏览器实抓对齐**。
2. `/settings/system` 加 `category_tree_provider`(mock|real)；`build_category_tree(session,name)` 配置驱动（real 读 `get_crawler_conf` 的 cookie/proxy）。
3. 接线 `/categories`、`/category/suggest`、`build_create_drafts` → 读配置。前端 TreeSelect 无需改。
4. @live 测试 + 真实样本夹具。

**不做**：类目缓存/持久化（先实时查）；完整类目属性字典（先类目树，属性沿用 LLM 建议）。

**依赖你**：有效 Ozon cookie/proxy（同爬虫；抓样本时你过一次验证）；最终 @live 你跑。

## 2. 模块与接口

### 2.1 共享请求层（抽取，消重且不破坏现有爬虫）
把 `OzonComposerProvider._fetch` 的请求逻辑（cookie 头注入、UA 轮换、间隔抖动、`_BLOCK_CODES` 退避、`CrawlerBlockedError`、transport 可注入）抽为 `services/ozon_market/composer_http.py::composer_fetch(url_or_action, *, cookie, proxy, timeout, min_delay, max_delay, max_retries, transport) -> dict`。`OzonComposerProvider` 改为委托它（保持现有行为，回归测试须绿）。

### 2.2 RealCategoryTree（`services/ozon_market/category_tree_real.py`）
```python
class RealCategoryTree:
    name = "real"
    def __init__(self, cookie=None, proxy=None, timeout=20.0, max_retries=4, transport=None): ...
    async def list_children(self, *, parent_id: int | None) -> list[dict]:
        # categoryChildV3?categoryId=<parent_id 或根>；composer_fetch 取 JSON → 解析 → [{id,name,path,leaf}]
    def all_leaves(self) -> list[dict]:
        return []   # 真实树巨大；suggest_category 对非 mock 树用 list_children(parent_id=None) 作候选(M6 现状)
```
- 解析层独立；`categoryChildV3` 真实响应结构**实现时实抓对齐**（同真实爬虫；缺样本 BLOCKED）。
- 反爬/cookie 失效 → `CrawlerBlockedError`。

### 2.3 配置驱动切换
- `schemas/system.py` + `api/system.py`：加 `category_tree_provider`(mock|real，默认 mock，非 secret)。
- `services/category_tree.py` 加 `async def build_category_tree(session, name)`：real → `get_crawler_conf` → `RealCategoryTree(cookie,proxy,...)`；mock → `MockCategoryTree`。同步 `get_category_tree` 保留给 mock/测试。

### 2.4 接线
- `api/category.py::categories`（`/categories`）：`get_category_tree("mock").list_children` → `(await build_category_tree(s, 配置)).list_children`。
- `api/category.py::suggest`、`api/listing.py::listing_build`(build_create_drafts)：`tree=await build_category_tree(s, 配置)`。
- 配置读取：`/settings/system.category_tree_provider`（回退 "mock"）。

## 3. 测试 + 验收 + 风险

### 3.1 测试（非 live 全 mock，0 warnings）
- `RealCategoryTree.list_children` 单测：`httpx.MockTransport` + **真实 categoryChildV3 夹具** → 抽 `[{id,name,path,leaf}]`；反爬码 → `CrawlerBlockedError`（monkeypatch sleep）。
- `composer_fetch` 抽取回归：现有 composer 硬化测试仍绿。
- `build_category_tree`：real 读配置构造（cookie/proxy 传入）；mock 默认。
- `/settings/system` category_tree_provider round-trip；`/categories` 按配置走 mock/real。
- `@pytest.mark.live`（默认跳过）：真实 categoryChildV3。
- 前端类目浏览器测试不回归。

### 3.2 验收标准
1. `/settings/system` 可切 category_tree_provider mock/real。
2. real + 有效 cookie：`/categories` 返回真实类目、前端 TreeSelect 逐层下钻真实全量；类目建议基于真实根类目。
3. 反爬/cookie 失效 → CrawlerBlockedError 可操作提示。
4. 非 live 0 warnings + README/docs + 前端 build；@live 齐备。

### 3.3 风险与降级
| 风险 | 应对 |
|---|---|
| categoryChildV3 真实结构与猜测不同 | 实抓真实响应对齐；解析层独立 |
| cookie 失效/反爬 | 复用 CrawlerBlockedError 可操作提示；配置页更新 |
| 抽 composer_fetch 破坏现有爬虫 | 抽取后跑现有 composer 硬化测试回归 |
| 真实树巨大 | 惰性 list_children（前端逐层）；不一次拉全 |

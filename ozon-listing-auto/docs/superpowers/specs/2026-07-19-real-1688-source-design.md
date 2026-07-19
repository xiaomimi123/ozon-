# 设计文档：子项 F1 — 1688 真实货源（配置驱动图搜）

> 去 mock 化子项 F1（见《去mock化-真实集成总规划.md》；拼多多 F2 后置）。日期：2026-07-19。
> 依据：现有 `Ali1688Provider`(占位端点)/`parser_ali`/账号池/matcher、用户确认（结构硬化 + 端点/请求可配 + parser 对齐 + @live；拍立淘签名由用户抓包填配置，本轮不复现）。

## 1. 目标与范围

**目标** = 1688 货源从占位切到可用真实（图搜为主）：`Ali1688Provider` 配置驱动（端点/方法/额外请求参数·头/响应路径可配），cookie 走账号池，parser 容错，@live 用户跑。

**诚实边界**：拍立淘图搜是 1688 mtop **签名 API**；签名算法脆弱/易失效/触 ToS，**本轮不复现**。本项把请求做成可配 —— **真实端点/sign 参数由用户抓包填 `/settings/sources`**；若签名太复杂，文档指引走付费聚合 API（另配）。现有占位端点 `s.1688.com/youyuan/index.htm` 实为网页搜索页（非 JSON API），占位。

**范围：**
1. `/settings/sources`(admin) 配置：`ali1688_image_search_url`/`ali1688_keyword_search_url`/`ali1688_method`(GET|POST)/`ali1688_extra_params`(JSON)/`ali1688_extra_headers`(JSON)/`ali1688_offer_list_path`(默认 `data.offerList`)。存 `app_settings.sources`。
2. `Ali1688Provider(conf, timeout, transport)` 配置驱动重写；`build_source_provider(session, platform)` 读配置构造。
3. `parse_offers(payload, offer_list_path)` 配置化路径 + 容错。
4. matcher 用 `build_source_provider`（mock/pinduoduo 不变）。
5. `@pytest.mark.live` + 前端 SourcesSettings 配置页 + 文档。

**依赖你**：1688 有效 cookie（账号池）+ 真实图搜端点/sign 参数（抓包填配置）；@live 你跑迭代。拼多多 F2 后置。

## 2. 模块与接口

### 2.1 `/settings/sources`（`schemas/sources.py` + `api/sources.py`，仿 crawler）
- 字段均非 secret（cookie 才是敏感项、在账号池）：`ali1688_image_search_url`、`ali1688_keyword_search_url`、`ali1688_method`(默认 "GET")、`ali1688_extra_params`(JSON 串，默认 "")、`ali1688_extra_headers`(JSON 串，默认 "")、`ali1688_offer_list_path`(默认 "data.offerList")。存 `app_settings.sources`。
- `async def get_source_conf(session) -> dict`（合并默认 + JSON 串解析为 dict/list；解析失败回默认）。

### 2.2 `build_source_provider(session, platform)`（`sources/factory.py`）
- `ali1688` → `Ali1688Provider(conf)`（读 get_source_conf）；`mock`/`pinduoduo` → 现有 `get_source_provider`（不变）。

### 2.3 `Ali1688Provider(conf, timeout=20.0, transport=None)` 重写
- `_client(session)`：UA + `conf["extra_headers"]`；cookie 从 session 注入；transport 可注入测试。
- `image_search(image_url, *, session)`：GET → `params={"imageAddress": image_url, **conf["extra_params"]}`；POST → `json={"imageAddress": image_url, **conf["extra_params"]}`。请求 `conf["image_search_url"]`；`raise_for_status`；→ `parse_offers(r.json(), conf["offer_list_path"])`。
- `keyword_search(kw, *, session)`：同理用 `keyword_search_url`，`{"keywords": kw, **extra_params}`。
- `fetch_detail`：保持占位。

### 2.4 parser（`parser_ali.py`）
- `parse_offers(payload, offer_list_path="data.offerList") -> list[SupplyCandidateDTO]`：按点路径取列表（`_dig`），逐条映射（沿用现字段：offerId/subject/priceInfo.price/quantityBegin/imageUrl/detailUrl/company）→ DTO；非 dict/缺字段/空 → 跳过/[]，不崩。保留旧 `parse_image_search` 作 `parse_offers(payload)` 的薄封装（向后兼容）。

### 2.5 matcher 接线
`get_source_provider(platform)` → `await build_source_provider(s, platform)`（worker 有 session）。mock 路径不变。

## 3. 测试 + 验收 + 风险

### 3.1 测试（非 live 全 mock，httpx.MockTransport，0 warnings）
- `/settings/sources` round-trip（各字段）。
- `get_source_conf` 默认 + JSON 解析（含坏 JSON 回默认）。
- `build_source_provider`：ali1688 读配置构造；mock 不变。
- `Ali1688Provider.image_search`：MockTransport 断言请求走**配置端点+方法+额外参数**、cookie 注入；`{data:{offerList:[{offerId,...}]}}` → 解析出候选。
- `parse_offers`：配置路径 + 容错（非 dict/空/缺字段）。
- `@pytest.mark.live`（默认跳过）：真实 1688 图搜（账号池 cookie + 配置端点，env 兜底）。
- 现有 mock 匹配/账号池测试不回归。

### 3.2 验收标准
1. `/settings/sources` 可配 1688 图搜端点/方法/额外参数·头/响应路径。
2. `Ali1688Provider` 配置驱动 + cookie 账号池注入；`parse_offers` 按配置路径容错解析。
3. matcher 用真实 provider（mock 不变）。
4. 非 live 0 warnings + README/docs（诚实：签名由用户抓包填配置，本轮不复现；付费聚合备选）+ 前端 SourcesSettings + `@live` 齐备。

### 3.3 风险与降级
| 风险 | 应对 |
|---|---|
| 拍立淘签名脆弱/易失效 | 端点/请求可配, 用户抓包填; 文档诚实; 端点常量化便于改 |
| 无真实响应样本对齐 parser | offerList 路径可配 + 容错; @live 用户迭代 |
| cookie 失效/反爬 | 账号池限速/冷却/换号(现有); 按平台隔离失败(现有) |
| 1688 ToS/风控 | 账号池 + 限速; 文档提示合规/付费聚合备选 |

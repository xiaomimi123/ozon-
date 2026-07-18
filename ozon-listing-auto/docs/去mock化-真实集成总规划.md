# 去 mock 化 · 真实集成总规划

> Ozon 跟卖/铺货自动化系统 v3.0 ｜ 日期：2026-07-18
> M1-M7 全部完成 + 真实爬虫(composer-api)已接入。本规划覆盖**剩余 6 项去 mock 化**：把已抽象好的 provider 从 mock 切到真实服务。
> 每一项是**独立子项目**，各自走 spec→plan→实现(SDD) 一个完整周期。本文只做规划与排序，不写实现代码。

## 0. 统一约定（所有子项通用）

- **mock-first→real 范式**：provider 抽象已在 M1-M6 建好，本轮只补真实实现 + 配置 + @live 校验。默认仍全 mock，配置切真实。
- **凭据走配置页**：所有 key/cookie/proxy 经后台配置页填入，Fernet 加密、GET 脱敏、留空不覆盖（复用 crawler/imagegen 范式）。
- **@live 测试**：真实网络调用一律 `@pytest.mark.live`（默认跳过）。非 live 测试全 mock、0 warnings。
- **诚实边界（关键）**：配置/请求/响应层 + @live 脚手架我都能无人值守写好；**能用浏览器抓到真实数据的（B 类目树）我对齐真实结构**。但**对接付费/需登录/需官方 API 文档的真实服务并确认跑通，需要你的 key/凭据/cookie，最终由你运行 @live 确认**——通义千问、生图服务、Ozon Seller 沙箱、1688/拼多多 cookie，我都无法在无人值守下替你调真实付费接口。
- **验证责任矩阵**见 §4。

---

## 1. 子项 A — 真实 LLM（译标题 / 抽属性 / 类目建议）✅ 已完成（配置页 + 接线 + @live）

**目标**：把 LLM 从 mock 切到真实（默认通义千问 DashScope，OpenAI 兼容），译标题/抽属性/类目建议走真实模型。

**现状**：`OpenAICompatLLM`（`services/llm/openai_compat.py`）**已完整实现**——`chat`(Bearer + 重试3次)、`translate`、`extract_json`(容错 JSON 解析、去代码围栏)。`get_llm("openai")` 从 **env**(`settings.llm_base_url/api_key/model`)构造。**缺**：后台配置页（现在只能改 env）。

**要建**：
- `/settings/llm`(admin) 配置页：`llm_provider`(mock|openai)、`llm_base_url`、`llm_api_key`(Fernet 脱敏留空不覆盖)、`llm_model`。
- `get_llm` / 各调用点（scorer 评分、category_map 类目建议、listing_builder 译标题）改为**读配置页 provider/凭据**，回退 env（向后兼容）。
- 前端 LLM 配置页 + @live 测试（真实 chat/translate/extract_json，`LLM_API_KEY` env 或配置页）。

**依赖你**：通义千问（或任意 OpenAI 兼容服务）的 `api_key`（你填进配置页）。

**能做到**：✅ **可相对完整交付**——你填 key 后即真跑；@live 由你确认一次。

**工量**：小（约 2-3 SDD 任务）。**风险**：低（实现已就绪，主要是配置化 + 接线）。

---

## 2. 子项 B — RealCategoryTree（类目树真实化）

**目标**：自建分支的类目建议从 M6 mock 固定小树切到真实 Ozon 全量类目树（`composer-api categoryChildV3`）。

**现状**：`services/category_tree.py` 有 `MockCategoryTree`；`get_category_tree("real")` 惰性 import 一个**尚未创建**的 `ozon_market/category_tree_real.py`。

**要建**：
- `RealCategoryTree`：调 `composer-api.bx/_action/v2/categoryChildV3?categoryId=<id>`，**复用爬虫 cookie/proxy 配置**(`get_crawler_conf`)，解析层独立。
- 解析对齐**真实 categoryChildV3 响应**——**我用浏览器抓真实响应对齐结构**（同真实爬虫做法）。
- `get_category_tree` 接入 real（按 system 配置或 crawler 配置切换）；前端类目浏览器（M7 已建 TreeSelect）自动变真实全量，无需改前端。
- @live 测试 + 真实样本夹具。

**依赖你**：有效 Ozon cookie/proxy（同真实爬虫，你已需为采集准备；抓样本时我用你浏览器过一次验证）。

**能做到**：✅ **可较完整交付**——我抓真实数据对齐 parser；@live 由你带 cookie 跑。

**工量**：小-中（约 2-3 任务）。**风险**：低-中（结构我可实抓对齐；cookie 时效同爬虫）。

---

## 3. 子项 C — 外部生图（openai_compat / http）

**目标**：自建分支的 `gen`（AI 营销图）从 mock 切到真实生图服务（千问万相 OpenAI 兼容端点 / GRSAI / 云舞AI 等 HTTP）。

**现状**：`OpenAICompatImageProvider`、`HttpImageProvider` 两者都 `raise NotImplementedError` 占位；`/settings/imagegen` 配置页已有(M6, provider/base_url/api_key/model/fallback)；`process_op` 的 gen 分支已按配置选 provider。

**要建**：
- `OpenAICompatImageProvider.process`：真实调 `{img_base_url}/images/generations`（OpenAI 图像接口格式），Bearer 鉴权，返回图 URL/base64 → 落 static → `ImageResult`；重试/超时/错误分类。
- `HttpImageProvider.process`：通用 HTTP 适配器 + **可配字段映射**（请求体/响应路径），接非 OpenAI 格式（GRSAI/云舞AI）。
- imager worker 的 gen op 默认接入（M6 遗留：`run_image_process` 目前硬编码 `gen_provider=mock`、默认 ops 无 gen）——把配置的 provider 透传。
- @live 测试 + 文档。

**依赖你**：真实生图服务的 `base_url/api_key/model`（+ 若用 HttpImageProvider，字段映射规则/样例响应）。

**能做到**：✅ 请求/响应层可建；**你提供服务+key**，@live 由你确认。HttpImageProvider 的字段映射需你给目标服务的请求/响应样例才能对准。

**工量**：中（约 3 任务）。**风险**：中（各家生图 API 格式不一；HttpImageProvider 需样例对齐）。

---

## 4. 子项 D — 真实 CLIP（跨平台去重向量）

**目标**：货源匹配的图片向量从 mock 切到真实中文 CLIP（`cn_clip ViT-B/16` CPU 推理）。

**现状**：`ChineseClipEmbedder`（`services/embedding/clip.py`）**已完整实现**（懒加载 torch/cn_clip，图 URL→512 维）。`EMBEDDER=clip` + worker `INSTALL_ML=true` 构建即启用。属**构建/部署 + 冒烟**层面，非写新逻辑。

**要建**：
- 验证 `INSTALL_ML=true` 构建路径（worker 镜像装 torch/cn_clip，体积数 GB）在目标环境可跑；`EMBEDDER=clip` 端到端向量化 + 去重生效。
- `@pytest.mark.live` 向量冒烟（真实图 URL → 512 维，需已装 [ml]）。
- 文档：启用步骤、资源占用（内存/首次下模型）、注意事项。

**依赖你**：目标服务器有足够资源（内存 + 首次下载模型）；`INSTALL_ML=true` 重建 worker。

**能做到**：✅ 代码已就绪；我可写冒烟 + 文档 + 验证构建路径。**注意**：本地开发环境不一定能装 torch（数 GB），真实向量冒烟可能得在你服务器/装了 [ml] 的环境跑。

**工量**：小（约 2 任务）。**风险**：低-中（依赖重、环境相关；逻辑无新增）。

---

## 5. 子项 E — RealOzonSeller 端点校正（跟卖 / 自建 / 状态）· 最硬

**目标**：真实上架——跟卖 `create_follow_offer`、自建 `create_product`、审核轮询 `get_product_status` 对接真实 Ozon Seller API。

**现状**：`services/ozon_seller/real.py`——`create_follow_offer`/`get_product_status` 有 httpx 实现但**端点是占位猜测**（跟卖误用 `/v2/product/import`，而 Ozon 跟卖是"在已有商品卡上按 SKU/条码建 offer"的另一套机制）；`create_product` 是占位（返回"未联调"）。凭据已可在**店铺管理页**填（Fernet）；`OZON_SELLER_PROVIDER=real`（或 M7 的 `/settings/system`）切换。

**要建**：
- **我联网查 Ozon Seller 官方 API 文档**（api-seller.ozon.ru：商品 import `/v3/product/import`、import 状态 `/v1/product/import/info`、价格库存 `/v1/product/import/prices` `/v2/products/stocks`、跟卖/关联机制等），对齐真实**端点 + 请求体字段 + 鉴权(Client-Id/Api-Key 头) + 分页 + 错误码**。
- 重写 `create_follow_offer`(真实跟卖机制)、`create_product`(`/v3/product/import` + 属性/图/类目)、`get_product_status`(import/info 或商品状态)。
- 错误码归类（品牌/类目受限等按码提示，不硬试，对齐开发文档 §10）。
- @live 测试（**沙箱店优先**）+ 文档。

**依赖你**：真实/**沙箱** Ozon 店铺 `Client-Id`/`Api-Key`（你在店铺管理页填）+ 一个可上架的目标（跟卖需真实目标商品卡）。**最终 live 校验必须你来跑**。

**能做到**：⚠️ 我可联网查官方文档**尽力对齐真实端点/请求体**，但真实 Ozon 行为（尤其"跟卖"关联的确切机制、审核回执）**只有你用真实/沙箱凭据跑 @live 才能最终确认**。可能需按你的实测报错迭代。

**工量**：大（约 4-5 任务）。**风险**：高（跟卖机制文档不一定清晰；需沙箱迭代）。

---

## 6. 子项 F — 1688 / 拼多多真实货源 · 最难（拼多多后置）

**目标**：货源匹配从 mock 切到真实 1688（图搜为主）+ 拼多多。

**现状**：`Ali1688Provider.image_search` 有 httpx+cookie 实现（拍立淘图搜）；账号池 `source_accounts`+`account_pool`(限速/冷却/换号) 已建(M2)；matcher 已接 `get_source_provider` + `acquire`。**拼多多** `PinduoduoProvider` 两方法都 `NotImplementedError`（图搜需签名、关键词需 selenium+代理）。

**要建（分两段，拼多多后置）**：
- **F1 · 1688 真实化**：校验/对齐 1688 拍立淘图搜 endpoint + 请求体 + cookie 会话（账号池已就绪）；解析真实响应；@live（你提供 1688 cookie）。**能相对完整交付。**
- **F2 · 拼多多（后置单列）**：图搜签名逆向 / 关键词 selenium+代理**重基建**——单独一个子项目，需专门环境；本轮先不做，标为后续。

**依赖你**：1688 有效 cookie（填账号池）；拼多多需 selenium/代理基建（后续）。

**能做到**：⚠️ F1(1688) 可校验交付（你提供 cookie 跑 @live）；F2(拼多多) 最难、后置。

**工量**：F1 中（约 3 任务）；F2 大（后续独立）。**风险**：高（反爬/签名/账号）。

---

## 7. 依赖关系与推荐顺序

- 各子项**相互独立**，无强代码依赖（B/E 复用已有 crawler cookie 配置与 ozon_seller 抽象）。
- **推荐顺序（易→难、高杠杆优先）：A → B → D → C → E → F1 →（F2 后续）**
  - 先交付**能相对完整落地**的：A(LLM，基本就绪)、B(类目树，我可实抓对齐)、D(CLIP，就绪)。
  - 再做需你提供服务的 C(生图)。
  - 最后啃最硬的 E(Ozon Seller，我查文档对齐+你沙箱校验)、F1(1688)；F2(拼多多) 后续单列。
- 每个子项交付后合入 main、更新记忆，再开下一个（同 M1-M7 节奏）。

## 8. 交付形态与验证责任矩阵

| 子项 | 我交付（无人值守） | 你负责（live 验证） | 能否本轮相对完整 |
|---|---|---|---|
| A LLM ✅ 已完成 | 配置页+接线+@live 脚手架+文档 | 填通义千问 key，跑一次 @live | ✅ 是 |
| B 类目树 | RealCategoryTree+**实抓对齐**+@live+文档 | 提供 cookie，跑 @live | ✅ 是 |
| C 生图 | 两 provider 请求/响应层+字段映射+@live+文档 | 提供服务+key(+HTTP 样例)，跑 @live | ✅ 是（HttpImageProvider 需你样例） |
| D CLIP | 冒烟+文档+构建路径验证 | 服务器装 [ml] 重建 worker，跑向量冒烟 | ✅ 是（重跑在你环境） |
| E Ozon Seller | **联网查文档对齐**端点/请求体+@live+文档 | 沙箱凭据跑 @live，按报错迭代 | ⚠️ 尽力，需你沙箱迭代 |
| F1 1688 | endpoint 校验+账号池接入+@live+文档 | 提供 1688 cookie，跑 @live | ⚠️ 尽力，需你 cookie |
| F2 拼多多 | （后续独立子项目） | selenium/代理基建 | ❌ 本轮不做 |

---

**下一步**：你定**先做哪个 / 是否按推荐顺序 A→B→D→C→E→F1**。定了之后，我对选定子项走完整 brainstorm→spec→plan→SDD 一个周期（合入后再开下一个）。

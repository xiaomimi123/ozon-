# 设计文档：M6 — 自建分支（改图 + 类目属性映射 + 自建上架）

> Ozon 跟卖/铺货自动化系统 v3.0，第六个里程碑。建立在已合入 main 的 M1-M5 之上。
> 版本：v1 ｜ 日期：2026-07-18 ｜ 依据：`开发文档v3-*.md` §5.5.5(AI 接口抽象)、§5.6(生图改图)、§5.7(类目属性映射)、§5.9(自建上架分支)、里程碑表 M6、M4/M5 代码。

## 1. 目标与范围

**M6 交付** = 自建（create）分支：改图流水线（本地真实 + provider 抽象）+ 类目属性映射（LLM 建议 + 记忆表复用 + 人工补齐）+ 自建上架（`/v2/product/import`）+ 图片工作室/自建草稿审核前端。验收「自建 listing 成功上架」。
把 M1-M5 的跟卖主线补齐为**跟卖 + 自建双分支**。自建管线：…→审核采用(M3) → **改图 → 类目属性映射 → 定价 → 生成自建草稿 → 人工确认 → 按节奏上架(M6，复用 M5 节奏调度)**。

**四个已确认决策：**
- **改图轻量真实 + 重的 mock**：whitebg/watermark/crop_norm 用 Pillow 真实实现（轻，测试可验产物）；rmbg 去背景走 `rembg`（`INSTALL_ML` 开关，默认 mock，与 M2 CLIP 一致）；gen AI 营销图走外部 provider（默认 mock）。
- **图片本地 static + API 静态服务**：产物存 docker volume 下 static 目录，返回相对 URL；真实公网 URL/对象存储 mock-first 后置。
- **自建上架复用 M4 ozon_seller 抽象**：加 `create_product`，MockOzonSeller 确定性返回，RealOzonSeller 占位（live 校正），走 `OZON_SELLER_PROVIDER` 切换。
- **类目映射全做**：LLM 建议 + 记忆表复用 + 人工补齐；类目树用 `CategoryTreeProvider`（mock 固定小树，real composer-api 后置）。

**范围外（后续里程碑）**：竞品/类目采集入口、OpenClaw 入口、公网部署 Nginx+HTTPS = M7。

## 2. 架构与新增文件

沿用 mock-first + 配置驱动 provider 范式（同 M2 embedder / M3 llm / M4 ozon_seller）。

```
server/app/
├── models/{product_image.py, category_map.py, listing_draft.py(+create 字段)}
├── alembic/versions/0006_m6_create_branch.py
├── schemas/{image.py, category.py, imagegen.py}
├── api/{images.py, category.py, imagegen.py, listing.py(build 扩展)}
├── services/
│   ├── imagegen/{base.py, local.py, openai_compat.py, http.py, mock.py, factory.py}
│   ├── category_map.py
│   ├── category_tree.py            # CategoryTreeProvider(mock/real)
│   ├── ozon_seller/*(加 create_product)
│   └── listing_builder.py(加 build_create_drafts)
├── workers/{imager.py, publisher.py(create 分支), arq_worker.py(+run_image_process)}
└── core/config.py(+image_provider)
web/src/pages/{ImageStudio.tsx, ListingReview.tsx(create 扩展), settings/ImagegenSettings.tsx}
web/src/api/{images.ts, category.ts, imagegen.ts}
server/static/images/                 # 改图产物(docker volume)
```

要点：
- 改图：LocalProvider(Pillow 真实) + 外部 gen provider + Mock；产物落 static，人工确认后进草稿。
- 类目映射：记忆表优先 → LLM → 人工补齐；跨任务复用。
- 自建上架：`create_product` mock-first，节奏调度(M5)两分支通用。
- 草稿状态流(create)：draft→(图确认+类目确认)→confirmed→scheduled→publishing→published|pending_review|failed。

## 3. 数据库 Schema（migration 0006）

### 3.1 `listing_drafts` 扩列（均 nullable，按 mode 使用）
```
ADD title varchar          # 译后标题(复用 M3 LLM translate)
ADD description text        # 描述
ADD category_id int         # Ozon 类目 id(自建必填, 跟卖为空)
ADD attributes jsonb        # 类目属性 {attr_id: value}
ADD images jsonb            # 已确认图片 url 列表(有序)
```
- `ozon_product_id`（M4 跟卖目标卡 fk）确认 nullable —— 自建无跟卖目标。
- status 新增值 create 分支复用 M4/M5：draft/confirmed/scheduled/publishing/published/pending_review/failed/below_min（字符串，无迁移）。

### 3.2 `product_images` 新表（改图产物 + 人工确认）
```
id, task_id(fk collect_tasks), candidate_id(fk supply_candidates, 来源货源),
source_url(varchar, 原图), op(varchar: rmbg|whitebg|watermark|crop_norm|gen),
provider(varchar: local|openai_compat|http|mock),
result_url(varchar, 产物本地相对 URL), sort(int 默认0 NOT NULL, 排序),
status(varchar16 默认 'pending' NOT NULL: pending|processing|done|failed|approved|rejected),
error(text null), meta(jsonb null), created_at, updated_at
索引 (task_id, status)、(candidate_id)
```
人工在图片工作室 approve → status=approved；approved 图按 sort 进自建草稿 `images`。

### 3.3 `category_maps` 新表（类目映射记忆表，跨任务复用）
```
id, signature(varchar, 归一化签名: 源平台类目名/标题关键词, 唯一),
source_hint(text, 原始线索), ozon_category_id(int), ozon_category_path(text),
attributes(jsonb, 建议属性模板), confirmed(bool 默认 false NOT NULL, 人工确认过),
usage_count(int 默认0 NOT NULL), created_at, updated_at
唯一约束 signature
```

### 3.4 无需建表
- 类目树：`CategoryTreeProvider`（mock 返回代码内固定小树；real composer-api `categoryChildV3` live 后置）。
- imagegen 配置：`app_settings.imagegen`（不建表；api_key Fernet 加密）。

## 4. 模块规格

### 4.1 改图（`services/imagegen/`）
```python
@dataclass
class ImageResult: url: str; provider: str; meta: dict
class ImageProvider(Protocol):
    async def process(self, *, image: bytes, op: str, params: dict) -> ImageResult: ...
```
- `LocalProvider`：Pillow 真实实现 whitebg(合成白底)/watermark(叠水印文字)/crop_norm(按目标比例居中裁剪归一化)；rmbg 去背景 **lazy import `rembg`**（`INSTALL_ML=true` 才装 onnx，缺失时回退 whitebg 并 meta 标注降级）。产物写 `static/images/`，返回相对 URL。
- `OpenAICompatImageProvider` / `HttpImageProvider`：仅 `gen`，走配置 `img_base_url/api_key/model`；请求层与解析层分离，live 后置。
- `MockImageProvider`：确定性返回占位产物 URL（默认）。
- `factory.get_image_provider(name)` + 分派器 `process_op(op, image, params, *, provider_conf)`：本地类操作(rmbg/whitebg/watermark/crop_norm) → LocalProvider；`gen` → 配置外部 provider（默认 mock）。

### 4.2 类目树（`services/category_tree.py`）
```python
class CategoryTreeProvider(Protocol):
    async def list_children(self, *, parent_id: int | None) -> list[dict]: ...  # [{id,name,path,leaf}]
```
- `MockCategoryTree`：返回代码内固定小类目树（若干层，供 LLM 候选 + 前端下拉）。
- `RealCategoryTree`：composer-api `categoryChildV3`（live 后置）。

### 4.3 类目属性映射（`services/category_map.py`）
```python
async def suggest_category(session, candidate, *, llm, tree) -> dict   # {category_id, path, attributes, source}
async def confirm_category(session, draft_id, *, category_id, attributes) -> None
def _signature(candidate) -> str
```
- suggest：先按 `_signature` 查 `category_maps`（命中且 confirmed → 复用，usage_count+1，source="memory"）；否则用 LLM（复用 M3 `llm.chat`，temperature=0，结构化 JSON `{category_id, path, attributes}`，失败重试→兜底默认类目，source="llm"/"fallback"）。
- confirm：写回草稿 category_id/attributes + upsert `category_maps`（confirmed=true）供复用。

### 4.4 Ozon 写入扩展（`services/ozon_seller/`）
```python
async def create_product(self, *, client_id, api_key, offer_id, title, description,
                         category_id, attributes, images, price, stock, barcode) -> PublishResult: ...
```
- `MockOzonSeller`：确定性 `ok=True, ozon_product_id="OZC-"+offer_id, status="imported"`。
- `RealOzonSeller`：`/v2/product/import` 占位（`_IMPORT_ENDPOINT`，live 校正）；请求层版本化封装。
- 走 `settings.ozon_seller_provider` 切换（复用 M4/M5）。

### 4.5 草稿生成扩展（`services/listing_builder.py`）
- `build_create_drafts(session, task_id, *, params, shop_id) -> dict`：对 create-mode 任务里 status∈{adopted,auto_adopted} 且无草稿的候选，建 mode='create' 草稿：title=LLM 译标题、pricing(复用 M4 `price_candidate`)、category via `suggest_category`、attributes 建议值、images=该候选已 approved 的 product_images（按 sort；无则空待补，status='draft'）。按 (task_id, candidate_id) 幂等。返回 `{built, blocked}`。
- `/listing/build` 按 `task.listing_mode` 分派：create → build_create_drafts；follow → 原 build_follow_drafts(M4)。

### 4.6 Worker
- `workers/imager.py`：`run_image_process(ctx, task_id)` —— 对 create 任务已采用候选源图，按 op 流水线（whitebg/crop_norm 等，可配）逐图 `process_op` 写 `product_images`（status done）；单图失败隔离（status failed + error）。
- `workers/publisher.py`：`tick_publish`/`run_publish_core` 按 `draft.mode` 分支 —— create → `seller.create_product(...)`；follow → 原 `create_follow_offer`。节奏调度(M5)两分支通用，无需改。

## 5. API
```
POST /images/process?task_id=&sync=      # 触发改图流水线(operator+; sync=true mock provider 落库)
GET  /images?task_id=&status=            # 改图产物列表(认证; before/after url)
POST /images/{id}/approve                # 采用产物(reviewer+)
POST /images/{id}/reject                 # 弃用(reviewer+)
POST /category/suggest?candidate_id=     # LLM 建议/记忆复用 类目+属性(operator+)
POST /listing/{draft_id}/confirm-category # 确认类目属性+写记忆表(reviewer+)
GET  /categories?parent_id=              # 类目树(CategoryTreeProvider; 前端下拉)
GET/PUT /settings/imagegen               # 生图 provider 配置(admin; api_key Fernet 加密/脱敏)
```
- `/listing/build`(M4) 扩展：listing_mode='create' 走 build_create_drafts。
- `/listing/publish`、`/publish/tick`、`/publish/monitor`(M4/M5) 自动按 draft.mode 处理 create，无新接口。
- 角色：images/category process/suggest → operator+；approve/reject/confirm-category → reviewer+；settings/imagegen → admin。

## 6. 前端
- **ImageStudio（图片工作室，仅自建）**：选任务 → 候选源图列表 → 触发改图 → 原图/产物对照网格（按 op 分组）→ 单张 采用/弃用。
- **ListingReview 扩展 create 分支**：自建草稿展示 标题/描述/类目(下拉 + LLM 建议按钮)/属性表单/已确认图片/进价售价毛利率 → 确认类目属性 → 确认草稿 → 进节奏队列(复用 M5)。
- **AI 生图配置页（settings/ImagegenSettings）**：provider(mock/local/openai_compat/http) + img_base_url/api_key/model + 降级顺序 → PUT /settings/imagegen。
- `api/images.ts` `api/category.ts` `api/imagegen.ts`；路由 + 菜单（图片工作室仅自建可见）。

## 7. 配置
- `config.py` 加 `image_provider: str = "mock"`（mock|local|openai_compat|http）；复用 `INSTALL_ML`（rembg 去背景）。
- `app_settings.imagegen`：provider/img_base_url/img_api_key(加密)/img_model/降级顺序；缺省 `DEFAULT_IMAGEGEN`。
- static：`server/static/images/`（docker volume 挂载），API `StaticFiles` 挂 `/static`。
- `.env.example` 增 `IMAGE_PROVIDER=mock`。

## 8. 测试策略（TDD, mock-first, 0 warnings）
- LocalProvider 单测（核心）：whitebg/watermark/crop_norm 用 Pillow 真实产物 —— 断言输出尺寸/格式/白底像素确定性；rmbg 缺 rembg 降级路径。
- MockImageProvider / 分派器：op 路由（本地 vs gen 走外部）；gen 默认 mock。
- category_tree 单测：MockCategoryTree list_children。
- category_map 单测：记忆表命中复用(不调 LLM)、未命中走 mock LLM 结构化建议、confirm 写 upsert。
- create_product 单测：MockOzonSeller 确定性 Ozon 商品ID；RealOzonSeller live 默认跳过。
- build_create_drafts 单测：create 任务已采用候选 → 自建草稿(标题/类目/属性/定价/已确认图)、幂等、无图留空。
- publisher 分支单测：create 草稿 → mock create_product → published + 回写；节奏 tick 两分支通用。
- imager worker：源图流水线 → product_images，单图失败隔离。
- API 集成测：images process→approve；category suggest→confirm-category；create 任务 build→confirm→publish(mock) 全链路；settings/imagegen(api_key 不泄漏)。
- 前端：ImageStudio + create ListingReview + ImagegenSettings 渲染(Vitest + mock)。
- pytest 0 warnings；测试全走 mock。

## 9. M6 验收标准（「自建 listing 成功上架」）
1. 迁移 0006：listing_drafts 扩列、product_images、category_maps。
2. 自建任务：采集→匹配→评分→采用→**改图(本地真实处理 + 人工确认)→类目属性映射(LLM 建议 + 记忆复用 + 人工补齐)→定价→生成自建草稿→确认→/publish 按节奏上架(mock create_product)→回写 Ozon 商品ID**。
3. 改图 provider 配置切换(local 真实 / mock / 外部生图 gen)；rembg 走 INSTALL_ML，live 默认跳过。
4. 类目映射记忆表跨任务复用；前端类目下拉 + 属性补齐。
5. 前端 ImageStudio + create 草稿审核 + AI 生图配置。
6. MockOzonSeller.create_product 全链路；Real live 默认跳过。
7. 非 live 0 warnings + README/docs(M6 说明) + 前端 build。

## 10. 风险与降级
| 风险 | 应对 |
|---|---|
| rembg/onnx 重依赖 | 走 INSTALL_ML 开关，缺失降级 whitebg，默认 mock；本地轻量操作(Pillow)不受影响 |
| 外部生图 API 各异/不稳 | OpenAICompat + Http 双适配器 + 降级顺序；本地能做的优先本地 |
| LLM 类目建议错/幻觉 | temperature=0 结构化 JSON + 人工确认闸门 + 记忆表复用；兜底默认类目 |
| Ozon import 端点/审核细节 | mock-first 保链路；RealOzonSeller 请求层版本化封装，live 默认跳过，沙箱先试 |
| 图片公网可达(Ozon 拉图) | 本地 static + 相对 URL mock-first；真实公网 URL/对象存储投产时接 |
| 自建草稿信息不全(缺图/缺类目)误上架 | 确认闸门校验(图确认 + 类目确认才可 confirm)；build 无图留 draft 待补 |

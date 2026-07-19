# 设计文档：子项 C — 外部生图接入（OpenAICompat + Http 通用适配器）

> 去 mock 化子项 C（见《去mock化-真实集成总规划.md》）。日期：2026-07-19。
> 依据：现有 imagegen 抽象/占位、`/settings/imagegen` 配置页、`process_op`/imager、用户确认（两适配器都建通用；gen=文生图）。

## 1. 目标与范围

**目标** = 外部生图从 mock 切真实（AI 营销图，文生图），两个通用适配器 + 配置驱动，用户后配服务/key。

**范围：**
1. `OpenAICompatImageProvider`：标准 OpenAI 图像接口 `POST {base_url}/images/generations`（文生图，prompt 来自 params）；响应 url 下载 / b64 解码 → 落 static。
2. `HttpImageProvider`：通用 HTTP 适配器，请求体模板 + 响应取图路径都从 `/settings/imagegen` 配，接非 OpenAI 格式服务。
3. 配置驱动：`/settings/imagegen` 扩展 http 映射字段；`get_configured_gen_provider(session, *, static_dir)`；`process_op`/imager 读配置选 gen provider（sync 仍 mock）。
4. 前端 ImagegenSettings 扩展 http 映射字段。
5. `@pytest.mark.live` + 文档。

**不做**：图生图（本轮文生图；后续）；gen 强制进默认改图流水线（opt-in，prompt 由调用方构造）。

**依赖你**：真实生图服务 base_url/api_key/model（配置页）；Http 适配器需请求/响应样例配映射；@live 你跑。

## 2. 模块与接口

### 2.1 共享存图 helper（`services/imagegen/save.py` 或 base）
`_save_image_bytes(raw: bytes, static_dir: str) -> str`：内容 hash 命名 `<sha1[:12]>.png` 写 static_dir，返回 `/static/images/<name>.png`（确定性，复用 LocalProvider 落盘范式）。

### 2.2 `OpenAICompatImageProvider`（`services/imagegen/openai_compat.py`）
```python
OpenAICompatImageProvider(base_url, api_key, model, static_dir=DEFAULT_STATIC_DIR, timeout=30.0, transport=None)
async def process(self, *, image, op, params) -> ImageResult
```
- `POST {base_url}/images/generations`，body `{"model":model, "prompt":params["prompt"], "n":1, "size":params.get("size","1024x1024"), "response_format":"url"}`，`Authorization: Bearer {api_key}`。
- 响应 `data[0].url` → httpx 下载字节；或 `data[0].b64_json` → base64 解码。→ `_save_image_bytes` → `ImageResult(url, "openai_compat", {"op":"gen"})`。
- 重试（3 次）/超时/错误分类；`transport` 可注入测试；文生图忽略输入 `image`。

### 2.3 `HttpImageProvider`（`services/imagegen/http.py`）
```python
HttpImageProvider(base_url, api_key, model, request_template, response_path, static_dir=..., timeout=30.0, transport=None)
async def process(self, *, image, op, params) -> ImageResult
```
- 请求体 = `request_template`（JSON 字符串，替换 `{prompt}`→params["prompt"]、`{model}`→model）；`POST base_url`，`Authorization: Bearer {api_key}`（若 key）。
- 响应按 `response_path`（点路径，如 `data.0.url` / `output.image_url` / `data.0.b64_json`）提取值；含 `b64` 关键字或非 http 开头 → 按 b64 解码，否则按 url 下载。→ `_save_image_bytes` → `ImageResult(url, "http", meta)`。
- 提取失败明确 raise（可操作错误）。

### 2.4 配置扩展 + get_configured_gen_provider
- `schemas/imagegen.py` `ImagegenIn/Out` 加 `img_request_template: str = ""`、`img_response_path: str = ""`（非 secret）；`api/imagegen.py` read/write 带上（api_key 仍 secret 留空不覆盖）。
- `services/imagegen/config.py` `async def get_configured_gen_provider(session, *, static_dir) -> ImageProvider`：读 `/settings/imagegen` → provider=openai_compat → OpenAICompatImageProvider(...)；http → HttpImageProvider(...)；否则 MockImageProvider。无 key/无配 → mock。

### 2.5 接线
- `process_op(op, *, image, params, static_dir=..., gen_provider="mock", gen_provider_obj=None)`：gen 分支 `prov = gen_provider_obj or get_image_provider(gen_provider, static_dir=static_dir)`。本地 op 不变。
- `run_image_process_core(..., gen_provider_obj=None)` 透传给 process_op。
- `run_image_process`（ARQ worker）：`gen_provider_obj = await get_configured_gen_provider(s, static_dir=...)` 传入；sync `/images/process` API 路径仍 mock（gen_provider_obj=None → mock）。
- gen 仍 opt-in：ops 含 "gen" 且 params 带 prompt 才跑（默认 ops 无 gen，不变）。

## 3. 测试 + 验收 + 风险

### 3.1 测试（非 live 全 mock，httpx.MockTransport，0 warnings）
- OpenAICompatImageProvider：MockTransport 先返回 `{data:[{url:"http://x/i.png"}]}`、再返回图字节（或一次 `{data:[{b64_json:...}]}`）→ 断言 ImageResult.url 落 static、provider="openai_compat"；错误码重试。
- HttpImageProvider：MockTransport + 样例 template/response_path（url 与 b64 两种）→ 提取存 static。
- `get_configured_gen_provider`：openai_compat/http/mock 按配置选（无 key→mock）。
- `process_op`：gen_provider_obj 优先；无则按名 mock。
- `/settings/imagegen` round-trip 新字段（脱敏/留空不覆盖不变）。
- `@pytest.mark.live`（默认跳过）：真实生图。
- 前端 ImagegenSettings 渲染新字段。

### 3.2 验收标准
1. `/settings/imagegen` 配 openai_compat 或 http（+key，http 配 template/path）。
2. gen op 走真实生图 → 产物落 static、图片工作室可确认；`@live` 齐备。
3. sync `/images/process` 仍 mock。
4. 非 live 0 warnings + README/docs + 前端 build。

### 3.3 风险与降级
| 风险 | 应对 |
|---|---|
| 各家生图 API 格式不一 | OpenAICompat 走标准；Http 可配 template/path |
| url vs b64 响应 | 两种都支持 |
| gen 费 token/慢 | opt-in；worker 异步；失败可降级 fallback |
| key/服务未配 | get_configured_gen_provider 无配回退 mock 不崩 |
| Http 映射配错 | 提取失败明确报错；文档给样例 |

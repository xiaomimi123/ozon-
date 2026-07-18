# 设计文档：子项 A — 真实 LLM 接入（配置页 + 接线 + @live）

> 去 mock 化子项 A（见《去mock化-真实集成总规划.md》）。日期：2026-07-18。
> 依据：现有 `OpenAICompatLLM`(已完整实现)、`get_llm` 调用点、crawler/imagegen 配置页范式。

## 1. 目标与范围

**目标** = LLM 从 mock 切真实（默认通义千问 DashScope，OpenAI 兼容），译标题/抽属性/类目建议走真实模型；凭据走后台配置页（不再仅 env）。

**范围：**
1. `/settings/llm`(admin) 配置页：llm_provider(mock|openai)、llm_base_url、llm_api_key(Fernet 脱敏·留空不覆盖)、llm_model。存 `app_settings.llm`。
2. `get_configured_llm(session)`：读 `/settings/llm` → provider=openai 且有 key → `OpenAICompatLLM`；否则 MockLLM。配置空回退 env `settings.llm_*`（向后兼容）。
3. 接线（用真实）：`scorer.run_score`(异步 worker)、`/category/suggest`(交互式)、`/listing/build`(自建译标题)。**保持 mock**：`/score?sync=true`(批量 demo，遵 sync=mock 规律)。
4. 前端 LLM 配置页 + `@pytest.mark.live` 真实测试。

**不做**：换模型改代码（配置驱动）；embedder/CLIP（子项 D）。

## 2. 模块与接口

### 2.1 `/settings/llm`（`schemas/llm.py` + `api/llm.py`，仿 imagegen）
- `LlmIn`：llm_provider="mock"、llm_base_url=""、llm_api_key=""、llm_model=""。
- `LlmOut`：llm_provider、llm_base_url、llm_api_key(脱敏 None/`***`)、llm_model。
- `GET`：`get_category_masked`（api_key 为 secret → `***`）。
- `PUT`：`if body.llm_api_key:` 才 `set_value(is_secret=True)`（留空不覆盖）；provider/base_url/model 明文 `set_value(is_secret=False)`。
- 路由**须先于通用 `/settings/{category}` 注册**（同 imagegen/crawler）。

### 2.2 `get_configured_llm(session)`（`services/llm/config.py`）
```python
async def get_configured_llm(session) -> LLMProvider:
    conf = await get_category(session, "llm")            # 解密 dict
    provider = conf.get("llm_provider") or settings.llm_provider
    if provider == "openai":
        base = conf.get("llm_base_url") or settings.llm_base_url
        key  = conf.get("llm_api_key")  or settings.llm_api_key
        model= conf.get("llm_model")    or settings.llm_model
        if key:
            return OpenAICompatLLM(base, key, model)
    return get_llm("mock")
```

### 2.3 接线改动
- `app/workers/scorer.py`：`llm=get_llm(settings.llm_provider)` → `llm=await get_configured_llm(s)`（run_score 内有 session；若无则新开一个读配置）。
- `app/api/category.py::suggest`：`get_llm("mock")` → `await get_configured_llm(s)`。
- `app/api/listing.py`（build 端点）：`build_create_drafts(..., llm=await get_configured_llm(s))`。
- `app/api/score.py` sync 分支：**不变**（`get_llm("mock")`）。

## 3. 前端 + 测试 + 验收 + 风险

### 3.1 前端
`web/src/pages/settings/LlmSettings.tsx`（仿 ImagegenSettings）：provider(Select mock/openai)、base_url、api_key(Password，脱敏不回填)、model → PUT `/settings/llm`；提示"默认通义千问 DashScope；api_key 留空不修改"。`api/llm.ts`；路由 + 菜单。

### 3.2 测试（非 live 全 mock，0 warnings）
- `/settings/llm` 集成测：Fernet 脱敏、留空不覆盖、round-trip。
- `get_configured_llm`：openai+key→OpenAICompatLLM；无 key/mock→MockLLM；配置空→回退 env（monkeypatch settings）。
- 接线测：scorer/category suggest/build 经 `get_configured_llm`（monkeypatch 断言）；`/score?sync=true` 仍 mock。
- `@pytest.mark.live`（默认跳过）：真实 chat/translate/extract_json（`LLM_API_KEY` env），译文非空、抽属性 dict。
- 前端：LlmSettings 渲染 + 保存。

### 3.3 验收标准
1. 后台 LLM 配置页填 base_url/api_key/model（Fernet/脱敏/留空不覆盖）+ 切 provider。
2. 配 openai+key：评分 worker/类目建议/自建译标题走真实 LLM；`@live` 用例齐备。
3. sync=true 批量路径仍 mock。
4. 非 live 0 warnings + README/docs + 前端 build。

### 3.4 风险与降级
| 风险 | 应对 |
|---|---|
| key 未配/失效 | 无 key 回退 mock 不崩；chat 重试3次(已有) |
| 返回非结构化 JSON | `_parse_json_loose` 已容错 |
| 真实调用慢/超时 | timeout+重试(已有)；评分在 worker 异步 |
| sync demo 误用真实致慢/费 token | sync=true 恒 mock |

# 设计文档：子项 D — 真实 CLIP 启用（向量冒烟 + 构建核对 + 文档）

> 去 mock 化子项 D（见《去mock化-真实集成总规划.md》）。日期：2026-07-19。
> 依据：`ChineseClipEmbedder`(已完整)、embedder 工厂/调用点、Dockerfile INSTALL_ML、docker-compose worker。用户确认：保持 env 驱动(EMBEDDER=clip)，只加 @live 冒烟 + 文档 + 构建核对（不加 UI 切换）。

## 1. 目标与范围

**目标** = 货源匹配图片向量从 mock 切真实中文 CLIP（`cn_clip ViT-B/16` CPU 推理）。**代码已完整**（`ChineseClipEmbedder` 懒加载 torch/cn_clip；`get_embedder(settings.embedder)` env 驱动；matcher/scorer worker 已接；Dockerfile `INSTALL_ML=true`→`.[dev,ml]`；compose worker 传 `INSTALL_ML`+`EMBEDDER`）。本项是"打通验证 + 冒烟 + 文档"。

**范围：**
1. `@pytest.mark.live` 向量冒烟（真实 embed_image → 512 维归一化，默认跳过）。
2. 构建配置静态核对（pyproject [ml]、Dockerfile、compose 参数正确）。
3. 《真实 CLIP 启用说明》文档 + README「真实 CLIP」小节。

**不做**：UI embedder 切换（保持 env 驱动，用户确认）；实际构建多 GB [ml] 镜像（本环境不可行，静态核对）。

**依赖你**：目标服务器足够内存 + `INSTALL_ML=true` 重建 worker（多 GB）；@live 向量冒烟在你 [ml] 环境跑。

## 2. 测试 + 验收 + 风险

### 2.1 测试
- `server/tests/test_live_clip.py`（`@pytest.mark.live @pytest.mark.asyncio`）：`ChineseClipEmbedder().embed_image(<公开图 URL>)` → 断言 `len == 512`、全 float、L2 模长≈1（归一化）；无 [ml]/torch 时 `pytest.skip`（import 失败即跳过）。默认 `-m "not live"` 跳过。
- 非 live 全绿 0 warnings（clip 模块懒加载，不装 torch 也能 import——现状已保证）。

### 2.2 验收标准
1. `EMBEDDER=clip` + worker `INSTALL_ML=true` 构建后：matcher/scorer worker 走真实 CLIP、跨平台去重生效（用户 [ml] 环境验证）。
2. `@live` 向量冒烟齐备（512 维、归一化）。
3. 《真实 CLIP 启用说明》：启用步骤 + 资源占用 + 首次下模型 + CPU 推理取舍 + 注意事项。
4. 非 live 0 warnings + README「真实 CLIP」小节 + 总规划标 D 完成。

### 2.3 风险与降级
| 风险 | 应对 |
|---|---|
| torch/cn_clip 多 GB 本地装不下 | @live 默认跳过；冒烟在用户 [ml] 环境；本项只静态核对构建路径 |
| 首次下模型慢/占内存 | 文档标注资源需求 + 首次预热 |
| CPU 推理慢 | 文档说明；批量在 worker 异步不阻塞 API |
| 误设 EMBEDDER=clip 但没装 [ml] | worker 首次 embed 报 ImportError（懒加载）；文档强调二者须同时设 |

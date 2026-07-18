# 真实 CLIP 启用说明（货源匹配跨平台图片去重）

> 子项目 D（去 mock 化）。`ChineseClipEmbedder`（`server/app/services/embedding/clip.py`）代码已完整实现，本说明只覆盖**如何启用**——构建参数、资源占用、验证方式，不涉及新逻辑。

## 目的

M2 货源匹配在同一商品下把 1688/拼多多两个平台采回的候选做跨平台去重（近似重复折叠为 1 个代表候选）。去重依据是图片向量的余弦相似度，默认 `mock` embedder 用 SHA256 确定性归一化向量（无语义、仅保证同 URL 出稳定向量，供开发/CI 免 torch 跑通全链路）。启用真实 CLIP 后改用中文 CLIP（`cn_clip` ViT-B/16，CPU 推理）编码图片语义，去重效果才具备真实可比性。

## 启用步骤

1. 编辑 `.env`（未有则从 `.env.example` 复制），同时设置两个变量：
   ```
   INSTALL_ML=true
   EMBEDDER=clip
   ```
2. 重新构建并启动 `worker` 服务：
   ```bash
   docker compose up -d --build worker
   ```
   `INSTALL_ML=true` 会让 `docker-compose.yml` 里 `worker.build.args.INSTALL_ML` 传给 `server/Dockerfile` 的 `ARG INSTALL_ML`，触发 `pip install -e ".[dev,ml]"`（而非默认的 `".[dev]"`），装入 `[ml]` 依赖组（`pyproject.toml`：`torch>=2.2`、`cn-clip>=1.5`、`rembg>=2.0`）。
3. `worker` 启动后，`app.workers.matcher.run_match`（ARQ 任务入口）按 `settings.embedder`（读环境变量 `EMBEDDER`，默认 `mock`）选择 `get_embedder("clip")` 即 `ChineseClipEmbedder`，替换 `MockEmbedder`。

`api` 服务的构建**不受影响**，始终 `INSTALL_ML=false`（不做匹配计算，无需装 ML 依赖）；`POST /match/start?sync=true` 的同步演示路径固定用 `mock`，真实 CLIP 只在异步入队路径（`sync=false`，由 `worker` 消费）生效。

## 资源占用

- **镜像体积**：`worker` 镜像装 `torch` + `cn_clip` + 依赖后体积达**数 GB**，构建耗时明显增加（`api`/其余服务不受影响）。
- **运行内存**：模型懒加载——首次收到 embed 请求时才 `import torch` + `load_from_name("ViT-B-16", ...)`，加载后常驻进程内存中，需预留足够内存（CPU 推理，无需 GPU/显存）。
- **首次模型下载**：首次加载会从 `cn_clip` 默认源下载 ViT-B/16 预训练权重，需要 `worker` 容器能联网（或提前预热/挂载缓存目录），否则首次调用会因下载失败报错。

## CPU 推理取舍

CPU 推理单张图片编码明显慢于 GPU，但匹配任务本身跑在 `worker` 的 ARQ 异步队列里（`sync=false`），不阻塞 API 请求响应；`match_cursor` 记录已处理商品，暂停/失败后可从游标续跑，大批量货源可分批处理，不要求单次请求内跑完。

## 验证方式

**方式一：跑一次真实货源匹配任务**

1. 按上方步骤启用后，新建/复用一个采集任务，`POST /match/start?task_id=<id>&sync=false` 走异步入队。
2. `GET /match/monitor?task_id=<id>` 看 `match_status` 推进到 `done`。
3. 查 `GET /candidates?task_id=<id>` 或直接查库 `supply_candidates` 表：每条候选的 `embedding` 字段应为 512 维向量（非 mock 的 SHA256 确定性向量），且同款商品的跨平台候选应正确聚簇（`dedup_group` 相同、`is_representative` 只有一条为真）。

**方式二：`@live` 向量冒烟测试**（默认跳过，不影响日常回归；需已装 `[ml]`）

```bash
cd server
.venv/bin/pip install -e '.[ml]'
.venv/bin/python -m pytest tests/test_live_clip.py -m live -v
```

未装 `[ml]`（`ImportError`）时用例自动 `skip`；断言真实调用 `ChineseClipEmbedder.embed_image()` 对一张公开 Ozon 商品图返回 512 维 `list[float]`，且 L2 范数 ≈ 1（归一化）。

另有 `server/tests/test_build_config.py`（非 `live`，日常回归会跑）静态核对构建配置本身没有偏离——`pyproject.toml` 的 `[ml]` 组含 `torch`/`cn-clip`、`Dockerfile` 的 `INSTALL_ML` 分支装 `[dev,ml]`、`docker-compose.yml` 的 `worker` 服务同时透传 `INSTALL_ML` 构建参数与 `EMBEDDER` 环境变量。

## 注意事项

- **`EMBEDDER=clip` 与 `INSTALL_ML=true` 须同时设置**：只设 `EMBEDDER=clip` 而不重建镜像（`INSTALL_ML` 仍为 `false`），`worker` 容器里没装 `torch`/`cn_clip`，首次收到 embed 请求触发懒加载 `import torch` 时会抛 `ImportError`，导致该商品的匹配失败。
- 反过来只设 `INSTALL_ML=true`（镜像装了 `[ml]`）而 `EMBEDDER` 仍是默认 `mock`，则镜像变大但实际仍用 mock 向量，达不到真实去重效果——两者需配套修改。
- **回退**：把 `.env` 的 `EMBEDDER` 改回 `mock`（`INSTALL_ML` 可保留 `true` 或一并改回 `false` 缩小镜像），重启 `worker` 即恢复轻量 mock 链路，无需回退代码。

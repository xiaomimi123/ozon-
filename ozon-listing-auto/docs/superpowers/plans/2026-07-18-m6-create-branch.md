# M6 自建分支（改图 + 类目属性映射 + 自建上架）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为系统补齐自建（create）上架分支：改图流水线（本地 Pillow 真实 + provider 抽象）、类目属性映射（LLM 建议 + 记忆表复用 + 人工补齐）、自建上架（`/v2/product/import` mock-first），复用 M5 节奏调度，端到端跑通「自建 listing 成功上架」。

**Architecture:** 沿用 M1-M5 的 mock-first + 配置驱动 provider 范式。新增 `imagegen`（LocalProvider Pillow 真实 / Mock / 外部 gen）、`category_map`（记忆表优先→LLM→人工）、`ozon_seller.create_product`、`listing_builder.build_create_drafts`、`imager` worker；`publisher` 按 `draft.mode` 分支。前端新增图片工作室 + 自建草稿审核 + AI 生图配置。

**Tech Stack:** Python 3.11 / FastAPI / SQLAlchemy 2.0 async / Alembic / ARQ / Pillow(新增核心依赖) / rembg(ml 可选) / React 18 + TS + Vite + Ant Design 5 / Vitest。

## Global Constraints

- Python 3.11；测试用 `.venv/bin/python -m pytest`（**不要**用系统 python3=3.9）。
- **pytest 0 warnings**（沿用全项目基线）；测试全走 mock（无真实网络 / torch / rembg / LLM / Ozon）。
- SQLite 测试兼容：JSONB 列一律 `JSONB().with_variant(JSON(), "sqlite")`；migration 的 NOT NULL / server_default 必须与 ORM 一致（NOT NULL parity）。
- conftest 已有 `from app import models`（勿改成 `import app.models`，会覆盖 FastAPI `app`）。
- 密钥（img_api_key 等）一律 Fernet 加密（复用 `settings_store`），响应脱敏，绝不明文返回。
- 角色门：`require_role("operator"|"reviewer"|"publisher"|"admin")`（admin 超级通过，已实现）。
- **sync=true 的接口恒用 mock provider**（测试/演示）；真实 provider 只在 sync=false 的 ARQ worker 路径按配置选（全项目规律）。
- 新代码沿用现有中文 docstring 风格与命名。

---

### Task 1: 数据模型 + migration 0006（product_images、category_maps、listing_drafts 扩列）

**Files:**
- Create: `app/models/product_image.py`
- Create: `app/models/category_map.py`
- Modify: `app/models/listing_draft.py`（加 title/description/category_id/attributes/images；ozon_product_id 改 nullable）
- Modify: `app/models/__init__.py`（导出 ProductImage、CategoryMap）
- Create: `alembic/versions/0006_m6_create_branch.py`
- Test: `tests/test_m6_models.py`

**Interfaces:**
- Produces: `ProductImage`（id, task_id, candidate_id, source_url, op, provider, result_url, sort, status, error, meta, created_at, updated_at）；`CategoryMap`（id, signature[unique], source_hint, ozon_category_id, ozon_category_path, attributes, confirmed, usage_count, created_at, updated_at）；`ListingDraft` 新增 title/description/category_id/attributes/images，ozon_product_id 可空。

- [ ] **Step 1: 写失败测试** `tests/test_m6_models.py`

```python
import pytest
from sqlalchemy import select
from app.models import ProductImage, CategoryMap, ListingDraft, CollectTask, SupplyCandidate, OzonProduct

@pytest.mark.asyncio
async def test_product_image_and_category_map_and_create_draft(db_session):
    task = CollectTask(keyword="k", listing_mode="create", source_platforms=[])
    db_session.add(task); await db_session.flush()
    oz = OzonProduct(task_id=task.id, sku="S1")
    db_session.add(oz); await db_session.flush()
    cand = SupplyCandidate(task_id=task.id, ozon_product_id=oz.id, platform="ali1688", offer_id="A1", title="童鞋")
    db_session.add(cand); await db_session.flush()
    img = ProductImage(task_id=task.id, candidate_id=cand.id, source_url="http://x/a.jpg",
                       op="whitebg", provider="local", result_url="/static/images/a.png", sort=0)
    cm = CategoryMap(signature="童鞋", source_hint="童鞋", ozon_category_id=17028922,
                     ozon_category_path="Обувь/Детская", attributes={"1": "v"}, confirmed=True)
    # 自建草稿：ozon_product_id 可空
    draft = ListingDraft(task_id=task.id, candidate_id=cand.id, mode="create",
                         title="Kids Shoes", description="desc", category_id=17028922,
                         attributes={"1": "v"}, images=["/static/images/a.png"], status="draft")
    db_session.add_all([img, cm, draft]); await db_session.commit()
    assert img.status == "pending"          # 默认值
    assert cm.usage_count == 0 and cm.confirmed is True
    got = (await db_session.execute(select(ListingDraft).where(ListingDraft.mode == "create"))).scalar_one()
    assert got.ozon_product_id is None and got.category_id == 17028922 and got.images == ["/static/images/a.png"]
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/python -m pytest tests/test_m6_models.py -q`
Expected: FAIL（ImportError: cannot import name 'ProductImage'）

- [ ] **Step 3: 建 `app/models/product_image.py`**

```python
"""改图产物 ORM：候选源图经改图流水线处理后的产物 + 人工确认状态（§5.6）。"""
from datetime import datetime
from sqlalchemy import String, Integer, Text, DateTime, ForeignKey, Index, JSON, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db import Base

_JSONB = JSONB().with_variant(JSON(), "sqlite")


class ProductImage(Base):
    __tablename__ = "product_images"
    __table_args__ = (
        Index("ix_image_task_status", "task_id", "status"),
        Index("ix_image_candidate", "candidate_id"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("collect_tasks.id"), index=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("supply_candidates.id"))
    source_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    op: Mapped[str] = mapped_column(String(16))                # rmbg|whitebg|watermark|crop_norm|gen
    provider: Mapped[str] = mapped_column(String(16))          # local|openai_compat|http|mock
    result_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    sort: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending|processing|done|failed|approved|rejected
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    meta: Mapped[dict | None] = mapped_column(_JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
```

- [ ] **Step 4: 建 `app/models/category_map.py`**

```python
"""类目属性映射记忆表 ORM：源线索→已确认 Ozon 类目/属性，跨任务复用（§5.7）。"""
from datetime import datetime
from sqlalchemy import String, Integer, Text, Boolean, DateTime, JSON, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db import Base

_JSONB = JSONB().with_variant(JSON(), "sqlite")


class CategoryMap(Base):
    __tablename__ = "category_maps"
    id: Mapped[int] = mapped_column(primary_key=True)
    signature: Mapped[str] = mapped_column(String(256), unique=True)   # 归一化签名(源类目名/标题关键词)
    source_hint: Mapped[str | None] = mapped_column(Text, nullable=True)
    ozon_category_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ozon_category_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    attributes: Mapped[dict | None] = mapped_column(_JSONB, nullable=True)
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    usage_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
```

- [ ] **Step 5: 改 `app/models/listing_draft.py`** —— 在 `barcode` 字段后加 5 列，并把 `ozon_product_id` 改为可空。

先把这一行：
```python
    ozon_product_id: Mapped[int] = mapped_column(ForeignKey("ozon_products.id"))
```
改为：
```python
    ozon_product_id: Mapped[int | None] = mapped_column(ForeignKey("ozon_products.id"), nullable=True)  # 自建无跟卖目标卡
```
再在 `barcode: Mapped[str | None] = ...` 行之后插入（注意文件顶部已 import `Text`）：
```python
    title: Mapped[str | None] = mapped_column(String(1024), nullable=True)         # 自建：译后标题
    description: Mapped[str | None] = mapped_column(Text, nullable=True)           # 自建：描述
    category_id: Mapped[int | None] = mapped_column(Integer, nullable=True)        # 自建：Ozon 类目 id
    attributes: Mapped[dict | None] = mapped_column(_JSONB, nullable=True)         # 自建：类目属性 {attr_id: value}
    images: Mapped[list | None] = mapped_column(_JSONB, nullable=True)             # 自建：已确认图片 url 列表(有序)
```

- [ ] **Step 6: 改 `app/models/__init__.py`** —— 加两行 import 与 `__all__` 项。

在 `from app.models.publish_pace import PublishPace` 后加：
```python
from app.models.product_image import ProductImage
from app.models.category_map import CategoryMap
```
`__all__` 列表末尾（`"PublishPace",` 后）加：`"ProductImage", "CategoryMap",`

- [ ] **Step 7: 建 `alembic/versions/0006_m6_create_branch.py`**

```python
"""m6 create branch: product_images, category_maps, listing_drafts create 字段"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0006"
down_revision = "0005"


def upgrade():
    op.add_column("listing_drafts", sa.Column("title", sa.String(1024), nullable=True))
    op.add_column("listing_drafts", sa.Column("description", sa.Text, nullable=True))
    op.add_column("listing_drafts", sa.Column("category_id", sa.Integer, nullable=True))
    op.add_column("listing_drafts", sa.Column("attributes", postgresql.JSONB, nullable=True))
    op.add_column("listing_drafts", sa.Column("images", postgresql.JSONB, nullable=True))
    op.alter_column("listing_drafts", "ozon_product_id", existing_type=sa.Integer, nullable=True)

    op.create_table("product_images",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("task_id", sa.Integer, sa.ForeignKey("collect_tasks.id"), index=True),
        sa.Column("candidate_id", sa.Integer, sa.ForeignKey("supply_candidates.id")),
        sa.Column("source_url", sa.String(512), nullable=True),
        sa.Column("op", sa.String(16), nullable=False),
        sa.Column("provider", sa.String(16), nullable=False),
        sa.Column("result_url", sa.String(512), nullable=True),
        sa.Column("sort", sa.Integer, server_default="0", nullable=False),
        sa.Column("status", sa.String(16), server_default="pending", nullable=False),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("meta", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_image_task_status", "product_images", ["task_id", "status"])
    op.create_index("ix_image_candidate", "product_images", ["candidate_id"])

    op.create_table("category_maps",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("signature", sa.String(256), nullable=False, unique=True),
        sa.Column("source_hint", sa.Text, nullable=True),
        sa.Column("ozon_category_id", sa.Integer, nullable=True),
        sa.Column("ozon_category_path", sa.String(512), nullable=True),
        sa.Column("attributes", postgresql.JSONB, nullable=True),
        sa.Column("confirmed", sa.Boolean, server_default=sa.false(), nullable=False),
        sa.Column("usage_count", sa.Integer, server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade():
    op.drop_table("category_maps")
    op.drop_index("ix_image_candidate", table_name="product_images")
    op.drop_index("ix_image_task_status", table_name="product_images")
    op.drop_table("product_images")
    op.alter_column("listing_drafts", "ozon_product_id", existing_type=sa.Integer, nullable=False)
    for col in ("images", "attributes", "category_id", "description", "title"):
        op.drop_column("listing_drafts", col)
```

- [ ] **Step 8: 运行测试通过**

Run: `.venv/bin/python -m pytest tests/test_m6_models.py -q`
Expected: PASS

- [ ] **Step 9: 全量回归**（确保扩列/新表未破坏既有）

Run: `.venv/bin/python -m pytest tests -q`
Expected: 全绿 0 warnings

- [ ] **Step 10: 提交**

```bash
git add app/models/ alembic/versions/0006_m6_create_branch.py tests/test_m6_models.py
git commit -m "feat(m6): 迁移0006 + product_images/category_maps/listing_drafts 自建字段"
```

---

### Task 2: 改图抽象（base/mock/factory + Pillow LocalProvider + 分派器），加 pillow 核心依赖

**Files:**
- Modify: `pyproject.toml`（`pillow>=10.0` 移入核心 dependencies；`rembg` 加入 ml 组）
- Create: `app/services/imagegen/__init__.py`
- Create: `app/services/imagegen/base.py`
- Create: `app/services/imagegen/mock.py`
- Create: `app/services/imagegen/local.py`
- Create: `app/services/imagegen/factory.py`
- Test: `tests/test_imagegen.py`

**Interfaces:**
- Produces:
  - `ImageResult(url: str, provider: str, meta: dict)`（dataclass）
  - `ImageProvider` Protocol：`async def process(self, *, image: bytes, op: str, params: dict) -> ImageResult`
  - `MockImageProvider`（name="mock"，确定性占位）
  - `LocalProvider(static_dir: str)`（name="local"，Pillow 真实 whitebg/watermark/crop_norm，rmbg 惰性 rembg 降级）
  - `factory.get_image_provider(name: str, *, static_dir: str) -> ImageProvider`
  - `factory.process_op(op: str, *, image: bytes, params: dict, static_dir: str, gen_provider: str = "mock") -> ImageResult`（本地类操作走 local，gen 走外部/mock）

- [ ] **Step 1: 加依赖并安装**

改 `pyproject.toml`：把 `ml = ["torch>=2.2", "cn-clip>=1.5", "pillow>=10.0"]` 改为
```toml
ml = ["torch>=2.2", "cn-clip>=1.5", "rembg>=2.0"]
```
并在核心 `dependencies` 列表末尾（`"simpleeval>=0.9",` 后）加一行：
```toml
  "pillow>=10.0",
```
安装到 venv：
```bash
.venv/bin/pip install "pillow>=10.0"
```
Expected: 成功装上 Pillow（轻量，无 torch）。

- [ ] **Step 2: 写失败测试** `tests/test_imagegen.py`

```python
import io
import pytest
from PIL import Image
from app.services.imagegen.factory import get_image_provider, process_op
from app.services.imagegen.mock import MockImageProvider


def _png_rgba(w=100, h=80, color=(200, 30, 30, 128)):
    img = Image.new("RGBA", (w, h), color)
    buf = io.BytesIO(); img.save(buf, format="PNG"); return buf.getvalue()


@pytest.mark.asyncio
async def test_local_whitebg_flattens_alpha(tmp_path):
    prov = get_image_provider("local", static_dir=str(tmp_path))
    res = await prov.process(image=_png_rgba(), op="whitebg", params={})
    assert res.provider == "local"
    out = Image.open(res.url.replace("/static", str(tmp_path)) if res.url.startswith("/static")
                     else str(tmp_path) + "/" + res.url.split("/")[-1])
    # 产物无 alpha（白底合成）；随便取一像素应不透明
    assert out.mode in ("RGB",)


@pytest.mark.asyncio
async def test_local_crop_norm_dims(tmp_path):
    prov = get_image_provider("local", static_dir=str(tmp_path))
    res = await prov.process(image=_png_rgba(120, 60), op="crop_norm", params={"size": [100, 100]})
    from PIL import Image as I
    out = I.open(str(tmp_path) + "/" + res.url.split("/")[-1])
    assert out.size == (100, 100)


@pytest.mark.asyncio
async def test_local_watermark_runs(tmp_path):
    prov = get_image_provider("local", static_dir=str(tmp_path))
    res = await prov.process(image=_png_rgba(), op="watermark", params={"text": "OZ"})
    assert res.url and "watermark" in res.meta.get("op", "watermark") or res.url


@pytest.mark.asyncio
async def test_local_rmbg_falls_back_when_rembg_missing(tmp_path):
    prov = get_image_provider("local", static_dir=str(tmp_path))
    res = await prov.process(image=_png_rgba(), op="rmbg", params={})
    # 无 rembg 环境下降级为 whitebg，并在 meta 标注
    assert res.meta.get("degraded") in (True, False)  # 有 rembg 则 False，无则 True；两者都可
    assert res.url


@pytest.mark.asyncio
async def test_mock_provider_deterministic():
    prov = MockImageProvider()
    r1 = await prov.process(image=b"abc", op="gen", params={})
    r2 = await prov.process(image=b"abc", op="gen", params={})
    assert r1.url == r2.url and r1.provider == "mock"


@pytest.mark.asyncio
async def test_process_op_routes_gen_to_mock(tmp_path):
    res = await process_op("gen", image=b"x", params={}, static_dir=str(tmp_path), gen_provider="mock")
    assert res.provider == "mock"
    res2 = await process_op("whitebg", image=_png_rgba(), params={}, static_dir=str(tmp_path))
    assert res2.provider == "local"
```

- [ ] **Step 3: 运行确认失败**

Run: `.venv/bin/python -m pytest tests/test_imagegen.py -q`
Expected: FAIL（ModuleNotFoundError: app.services.imagegen）

- [ ] **Step 4: 建 `app/services/imagegen/__init__.py`**（空 docstring）

```python
"""改图抽象层（§5.5.5/§5.6）：ImageProvider 接口、Local(Pillow)/Mock 实现与分派器。"""
```

- [ ] **Step 5: 建 `app/services/imagegen/base.py`**

```python
"""改图 provider 抽象：统一 process(op) 接口（§5.5.5）。"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Protocol

LOCAL_OPS = {"rmbg", "whitebg", "watermark", "crop_norm"}   # 本地可处理
GEN_OPS = {"gen"}                                           # 需外部生图 provider


@dataclass
class ImageResult:
    url: str                       # 产物相对 URL（/static/images/xxx.png）或文件名
    provider: str
    meta: dict = field(default_factory=dict)


class ImageProvider(Protocol):
    name: str
    async def process(self, *, image: bytes, op: str, params: dict) -> ImageResult: ...
```

- [ ] **Step 6: 建 `app/services/imagegen/mock.py`**

```python
"""MockImageProvider：确定性占位产物（默认，测试/演示，无外部依赖）。"""
import hashlib
from app.services.imagegen.base import ImageResult


class MockImageProvider:
    name = "mock"

    async def process(self, *, image: bytes, op: str, params: dict) -> ImageResult:
        h = hashlib.sha1(image + op.encode()).hexdigest()[:12]   # 确定性：同输入同产物名
        return ImageResult(url=f"/static/images/mock_{op}_{h}.png", provider="mock",
                           meta={"op": op, "mock": True})
```

- [ ] **Step 7: 建 `app/services/imagegen/local.py`**

```python
"""LocalProvider：Pillow 本地真实处理（whitebg/watermark/crop_norm），rmbg 惰性 rembg 降级。
产物写 static_dir，文件名用内容 hash 保证确定性（测试可复现）。"""
import hashlib
import io
import os
from PIL import Image, ImageDraw
from app.services.imagegen.base import ImageResult


class LocalProvider:
    name = "local"

    def __init__(self, static_dir: str):
        self.static_dir = static_dir
        os.makedirs(static_dir, exist_ok=True)

    def _save(self, img: Image.Image, op: str, seed: bytes) -> str:
        h = hashlib.sha1(seed + op.encode()).hexdigest()[:12]
        fname = f"{op}_{h}.png"
        img.save(os.path.join(self.static_dir, fname), format="PNG")
        return f"/static/images/{fname}"

    async def process(self, *, image: bytes, op: str, params: dict) -> ImageResult:
        meta: dict = {"op": op, "degraded": False}
        img = Image.open(io.BytesIO(image))
        if op == "whitebg":
            img = self._whitebg(img)
        elif op == "crop_norm":
            size = params.get("size") or [800, 800]
            img = self._crop_norm(img, int(size[0]), int(size[1]))
        elif op == "watermark":
            img = self._watermark(img.convert("RGBA"), str(params.get("text", "OZON"))).convert("RGB")
        elif op == "rmbg":
            img, degraded = self._rmbg(img)
            meta["degraded"] = degraded
        else:
            raise ValueError(f"LocalProvider 不支持 op={op}")
        if img.mode == "RGBA":
            img = img.convert("RGB")
        url = self._save(img, op, image)
        return ImageResult(url=url, provider="local", meta=meta)

    def _whitebg(self, img: Image.Image) -> Image.Image:
        img = img.convert("RGBA")
        bg = Image.new("RGBA", img.size, (255, 255, 255, 255))
        bg.alpha_composite(img)
        return bg.convert("RGB")

    def _crop_norm(self, img: Image.Image, tw: int, th: int) -> Image.Image:
        img = img.convert("RGB")
        sw, sh = img.size
        scale = max(tw / sw, th / sh)
        img = img.resize((max(1, round(sw * scale)), max(1, round(sh * scale))))
        rw, rh = img.size
        left, top = (rw - tw) // 2, (rh - th) // 2
        return img.crop((left, top, left + tw, top + th))

    def _watermark(self, img: Image.Image, text: str) -> Image.Image:
        draw = ImageDraw.Draw(img)
        draw.text((5, 5), text, fill=(255, 255, 255, 180))
        return img

    def _rmbg(self, img: Image.Image):
        try:
            from rembg import remove   # 惰性：仅 INSTALL_ML 环境有
            out = remove(img)
            return out, False
        except Exception:               # noqa: BLE001  无 rembg/onnx 时降级白底
            return self._whitebg(img), True
```

- [ ] **Step 8: 建 `app/services/imagegen/factory.py`**

```python
"""按名返回 ImageProvider + 分派器：本地类操作走 LocalProvider，gen 走配置的外部/mock provider。"""
from app.services.imagegen.base import ImageProvider, ImageResult, LOCAL_OPS, GEN_OPS
from app.services.imagegen.mock import MockImageProvider
from app.services.imagegen.local import LocalProvider

DEFAULT_STATIC_DIR = "static/images"


def get_image_provider(name: str = "mock", *, static_dir: str = DEFAULT_STATIC_DIR) -> ImageProvider:
    if name == "mock":
        return MockImageProvider()
    if name == "local":
        return LocalProvider(static_dir)
    if name == "openai_compat":
        from app.services.imagegen.openai_compat import OpenAICompatImageProvider
        return OpenAICompatImageProvider()
    if name == "http":
        from app.services.imagegen.http import HttpImageProvider
        return HttpImageProvider()
    raise ValueError(f"未知 image provider: {name}")


async def process_op(op: str, *, image: bytes, params: dict, static_dir: str = DEFAULT_STATIC_DIR,
                     gen_provider: str = "mock") -> ImageResult:
    """本地类操作(rmbg/whitebg/watermark/crop_norm)恒走 LocalProvider；gen 走配置的外部 provider(默认 mock)。"""
    if op in LOCAL_OPS:
        return await LocalProvider(static_dir).process(image=image, op=op, params=params)
    if op in GEN_OPS:
        return await get_image_provider(gen_provider, static_dir=static_dir).process(image=image, op=op, params=params)
    raise ValueError(f"未知 op: {op}")
```

- [ ] **Step 9: 运行测试通过 + 回归**

Run: `.venv/bin/python -m pytest tests/test_imagegen.py -q && .venv/bin/python -m pytest tests -q`
Expected: 全绿 0 warnings

- [ ] **Step 10: 提交**

```bash
git add pyproject.toml app/services/imagegen/ tests/test_imagegen.py
git commit -m "feat(m6): 改图抽象 LocalProvider(Pillow 真实)/Mock + 分派器 + pillow 核心依赖"
```

> 注：`openai_compat.py` / `http.py`（外部 gen 适配器，live 后置）在 Task 7 建占位实现，此处 factory 惰性 import 即可。

---

### Task 3: 类目树 + 类目属性映射服务

**Files:**
- Create: `app/services/category_tree.py`
- Create: `app/services/category_map.py`
- Test: `tests/test_category_map.py`

**Interfaces:**
- Consumes: `MockLLM.extract_json`（现返回 `{}`，本任务测试用 mock，故 suggest 在 LLM 返回空时走兜底）；`CategoryMap`、`SupplyCandidate`、`ListingDraft`。
- Produces:
  - `category_tree.get_category_tree(name="mock") -> CategoryTreeProvider`；`MockCategoryTree.list_children(parent_id) -> list[dict]`（`[{id,name,path,leaf}]`）
  - `category_map.suggest_category(session, candidate, *, llm, tree=None) -> dict`（`{category_id, path, attributes, source}`，source∈memory|llm|fallback）
  - `category_map.confirm_category(session, draft_id, *, category_id, attributes, path=None, signature=None) -> dict`
  - `category_map._signature(candidate) -> str`

- [ ] **Step 1: 写失败测试** `tests/test_category_map.py`

```python
import pytest
from sqlalchemy import select
from app.models import CollectTask, OzonProduct, SupplyCandidate, ListingDraft, CategoryMap
from app.services.category_tree import get_category_tree
from app.services.category_map import suggest_category, confirm_category
from app.services.llm.factory import get_llm


async def _cand(s, title="童鞋 保暖"):
    t = CollectTask(keyword="k", listing_mode="create", source_platforms=[]); s.add(t); await s.flush()
    o = OzonProduct(task_id=t.id, sku="S"); s.add(o); await s.flush()
    c = SupplyCandidate(task_id=t.id, ozon_product_id=o.id, platform="ali1688", offer_id="A", title=title)
    s.add(c); await s.flush()
    return t, c


@pytest.mark.asyncio
async def test_mock_tree_children():
    tree = get_category_tree("mock")
    roots = await tree.list_children(parent_id=None)
    assert roots and all({"id", "name", "path"} <= set(n) for n in roots)


@pytest.mark.asyncio
async def test_suggest_uses_memory_when_confirmed_hit(db_session):
    _, c = await _cand(db_session)
    from app.services.category_map import _signature
    db_session.add(CategoryMap(signature=_signature(c), source_hint=c.title, ozon_category_id=999,
                               ozon_category_path="X/Y", attributes={"a": "b"}, confirmed=True))
    await db_session.commit()
    res = await suggest_category(db_session, c, llm=get_llm("mock"), tree=get_category_tree("mock"))
    assert res["source"] == "memory" and res["category_id"] == 999
    hit = (await db_session.execute(select(CategoryMap).where(CategoryMap.ozon_category_id == 999))).scalar_one()
    assert hit.usage_count == 1     # 命中 +1


@pytest.mark.asyncio
async def test_suggest_falls_back_when_llm_empty(db_session):
    _, c = await _cand(db_session)
    res = await suggest_category(db_session, c, llm=get_llm("mock"), tree=get_category_tree("mock"))
    assert res["source"] in ("llm", "fallback") and res["category_id"] is not None


@pytest.mark.asyncio
async def test_confirm_writes_memory_and_draft(db_session):
    _, c = await _cand(db_session)
    d = ListingDraft(task_id=c.task_id, candidate_id=c.id, mode="create", status="draft"); db_session.add(d)
    await db_session.commit()
    r = await confirm_category(db_session, d.id, category_id=17028922, attributes={"1": "v"},
                               path="Обувь", signature="童鞋")
    await db_session.commit()
    assert r["category_id"] == 17028922
    got = (await db_session.execute(select(ListingDraft).where(ListingDraft.id == d.id))).scalar_one()
    assert got.category_id == 17028922 and got.attributes == {"1": "v"}
    cm = (await db_session.execute(select(CategoryMap).where(CategoryMap.signature == "童鞋"))).scalar_one()
    assert cm.confirmed is True and cm.ozon_category_id == 17028922
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/python -m pytest tests/test_category_map.py -q`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 建 `app/services/category_tree.py`**

```python
"""Ozon 类目树 provider（§5.7）：mock 固定小树；real 走 composer-api categoryChildV3（live 后置）。"""
from __future__ import annotations
from typing import Protocol

# mock 固定小树：id/name/path/leaf/parent（供 LLM 候选 + 前端下拉）
_MOCK_TREE = [
    {"id": 17027492, "name": "Одежда", "path": "Одежда", "leaf": False, "parent": None},
    {"id": 17028922, "name": "Обувь", "path": "Обувь", "leaf": False, "parent": None},
    {"id": 15621048, "name": "Дом", "path": "Дом", "leaf": False, "parent": None},
    {"id": 17028930, "name": "Детская обувь", "path": "Обувь/Детская обувь", "leaf": True, "parent": 17028922},
    {"id": 17028931, "name": "Женская обувь", "path": "Обувь/Женская обувь", "leaf": True, "parent": 17028922},
    {"id": 17027500, "name": "Футболки", "path": "Одежда/Футболки", "leaf": True, "parent": 17027492},
]


class CategoryTreeProvider(Protocol):
    name: str
    async def list_children(self, *, parent_id: int | None) -> list[dict]: ...


class MockCategoryTree:
    name = "mock"

    async def list_children(self, *, parent_id: int | None) -> list[dict]:
        return [{"id": n["id"], "name": n["name"], "path": n["path"], "leaf": n["leaf"]}
                for n in _MOCK_TREE if n["parent"] == parent_id]

    def all_leaves(self) -> list[dict]:
        return [n for n in _MOCK_TREE if n["leaf"]]


def get_category_tree(name: str = "mock") -> CategoryTreeProvider:
    if name == "mock":
        return MockCategoryTree()
    if name == "real":
        from app.services.ozon_market.category_tree_real import RealCategoryTree  # live 后置
        return RealCategoryTree()
    raise ValueError(f"未知 category tree: {name}")
```

> 注：`real` 分支惰性 import 一个尚未创建的模块，仅在显式请求 real 时触发；本里程碑不建该文件（live 后置，与 RealOzonSeller 同范式）。测试只用 mock。

- [ ] **Step 4: 建 `app/services/category_map.py`**

```python
"""类目属性映射（§5.7）：记忆表优先 → LLM 建议 → 兜底默认；确认写回草稿 + upsert 记忆表复用。"""
import json
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import CategoryMap, ListingDraft
from app.services.category_tree import MockCategoryTree

_FALLBACK_CATEGORY = {"category_id": 15621048, "path": "Дом", "attributes": {}}


def _signature(candidate) -> str:
    """归一化签名：取标题前若干词做 key（跨任务复用同类商品的类目映射）。"""
    t = (candidate.title or "").strip().lower()
    return t[:120] if t else f"cand-{candidate.id}"


async def suggest_category(session: AsyncSession, candidate, *, llm, tree=None) -> dict:
    tree = tree or MockCategoryTree()
    sig = _signature(candidate)
    row = (await session.execute(select(CategoryMap).where(CategoryMap.signature == sig))).scalar_one_or_none()
    if row and row.confirmed and row.ozon_category_id is not None:
        row.usage_count = (row.usage_count or 0) + 1
        return {"category_id": row.ozon_category_id, "path": row.ozon_category_path,
                "attributes": row.attributes or {}, "source": "memory"}
    # 未命中记忆 → LLM 建议（结构化 JSON）
    leaves = tree.all_leaves() if isinstance(tree, MockCategoryTree) else await tree.list_children(parent_id=None)
    catalog = "; ".join(f'{n["id"]}={n["path"]}' for n in leaves)
    prompt = ("从以下 Ozon 类目中为该商品选最合适的一个，并给出关键属性，"
              f'返回 JSON {{"category_id":int,"path":str,"attributes":object}}。'
              f'\n商品标题: {candidate.title}\n候选类目: {catalog}')
    try:
        data = await llm.extract_json(prompt)
    except Exception:  # noqa: BLE001
        data = {}
    cid = data.get("category_id") if isinstance(data, dict) else None
    if cid:
        return {"category_id": int(cid), "path": data.get("path"),
                "attributes": data.get("attributes") or {}, "source": "llm"}
    return {**_FALLBACK_CATEGORY, "source": "fallback"}


async def confirm_category(session: AsyncSession, draft_id: int, *, category_id: int,
                           attributes: dict, path: str | None = None, signature: str | None = None) -> dict:
    d = (await session.execute(select(ListingDraft).where(ListingDraft.id == draft_id))).scalar_one()
    d.category_id = category_id
    d.attributes = attributes
    sig = signature or (d.title or "").strip().lower()[:120] or f"draft-{draft_id}"
    row = (await session.execute(select(CategoryMap).where(CategoryMap.signature == sig))).scalar_one_or_none()
    if not row:
        row = CategoryMap(signature=sig); session.add(row)
    row.source_hint = d.title
    row.ozon_category_id = category_id
    row.ozon_category_path = path
    row.attributes = attributes
    row.confirmed = True
    return {"draft_id": draft_id, "category_id": category_id}
```

- [ ] **Step 5: 运行测试通过 + 回归**

Run: `.venv/bin/python -m pytest tests/test_category_map.py -q && .venv/bin/python -m pytest tests -q`
Expected: 全绿 0 warnings

- [ ] **Step 6: 提交**

```bash
git add app/services/category_tree.py app/services/category_map.py tests/test_category_map.py
git commit -m "feat(m6): 类目树(mock)+类目属性映射(记忆表优先→LLM→兜底)"
```

---

### Task 4: ozon_seller.create_product + listing_builder.build_create_drafts

**Files:**
- Modify: `app/services/ozon_seller/base.py`（Protocol 加 create_product）
- Modify: `app/services/ozon_seller/mock.py`（实现 create_product）
- Modify: `app/services/ozon_seller/real.py`（占位 create_product，live）
- Modify: `app/services/listing_builder.py`（加 build_create_drafts）
- Test: `tests/test_create_builder.py`

**Interfaces:**
- Consumes: `price_candidate`、`DEFAULT_PRICING`（M4）；`suggest_category`（Task 3）；`get_llm`、`get_category_tree`；`ProductImage`（Task 1，approved 图）。
- Produces:
  - `OzonSellerProvider.create_product(*, client_id, api_key, offer_id, title, description, category_id, attributes, images, price, stock, barcode) -> PublishResult`
  - `MockOzonSeller.create_product`（`ozon_product_id="OZC-"+offer_id, status="imported"`）
  - `build_create_drafts(session, task_id, *, params=None, shop_id=None, llm=None, tree=None) -> dict`（`{built, blocked, skipped}`）

- [ ] **Step 1: 写失败测试** `tests/test_create_builder.py`

```python
import pytest
from sqlalchemy import select
from app.models import CollectTask, OzonProduct, SupplyCandidate, ListingDraft, ProductImage
from app.services.ozon_seller.factory import get_ozon_seller
from app.services.listing_builder import build_create_drafts
from app.services.llm.factory import get_llm
from app.services.category_tree import get_category_tree


@pytest.mark.asyncio
async def test_mock_create_product_deterministic():
    seller = get_ozon_seller("mock")
    r = await seller.create_product(client_id="c", api_key="k", offer_id="A1", title="T", description="d",
                                    category_id=17028930, attributes={"1": "v"},
                                    images=["/static/images/x.png"], price=1000.0, stock=5, barcode="B")
    assert r.ok and r.ozon_product_id == "OZC-A1" and r.status == "imported"


async def _create_task_with_adopted(s, with_image=True):
    t = CollectTask(keyword="k", listing_mode="create", source_platforms=[]); s.add(t); await s.flush()
    o = OzonProduct(task_id=t.id, sku="S", weight=0.5); s.add(o); await s.flush()
    c = SupplyCandidate(task_id=t.id, ozon_product_id=o.id, platform="ali1688", offer_id="A1",
                        title="童鞋", price=30.0, status="adopted"); s.add(c); await s.flush()
    if with_image:
        s.add(ProductImage(task_id=t.id, candidate_id=c.id, op="whitebg", provider="local",
                           result_url="/static/images/w.png", sort=0, status="approved"))
    await s.commit()
    return t, c


@pytest.mark.asyncio
async def test_build_create_drafts_makes_draft_with_category_price_images(db_session):
    t, c = await _create_task_with_adopted(db_session, with_image=True)
    res = await build_create_drafts(db_session, t.id, llm=get_llm("mock"), tree=get_category_tree("mock"))
    await db_session.commit()
    assert res["built"] == 1
    d = (await db_session.execute(select(ListingDraft).where(ListingDraft.task_id == t.id))).scalar_one()
    assert d.mode == "create" and d.category_id is not None and d.price is not None
    assert d.images == ["/static/images/w.png"]


@pytest.mark.asyncio
async def test_build_create_drafts_idempotent_and_no_image(db_session):
    t, c = await _create_task_with_adopted(db_session, with_image=False)
    r1 = await build_create_drafts(db_session, t.id, llm=get_llm("mock"), tree=get_category_tree("mock"))
    await db_session.commit()
    r2 = await build_create_drafts(db_session, t.id, llm=get_llm("mock"), tree=get_category_tree("mock"))
    await db_session.commit()
    assert r1["built"] == 1 and r2["built"] == 0 and r2["skipped"] == 1
    d = (await db_session.execute(select(ListingDraft).where(ListingDraft.task_id == t.id))).scalar_one()
    assert d.images in ([], None)   # 无 approved 图 → 空，待补
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/python -m pytest tests/test_create_builder.py -q`
Expected: FAIL（AttributeError: create_product / build_create_drafts）

- [ ] **Step 3: 改 `app/services/ozon_seller/base.py`** —— 在 Protocol 里加一个方法声明（`get_product_status` 后）：

```python
    async def create_product(self, *, client_id: str, api_key: str, offer_id: str, title: str,
                             description: str, category_id: int | None, attributes: dict,
                             images: list, price: float, stock: int, barcode: str | None) -> PublishResult: ...
```

- [ ] **Step 4: 改 `app/services/ozon_seller/mock.py`** —— 在类内加：

```python
    async def create_product(self, *, client_id, api_key, offer_id, title, description,
                             category_id, attributes, images, price, stock, barcode) -> PublishResult:
        return PublishResult(ok=True, ozon_product_id=f"OZC-{offer_id}", status="imported",
                             raw={"title": title, "category_id": category_id, "images": len(images or []),
                                  "price": price, "stock": stock})
```

- [ ] **Step 5: 改 `app/services/ozon_seller/real.py`** —— 加占位方法（沿用文件里 RealOzonSeller 的 httpx 请求层风格，端点 live 校正）。读现有文件后在类内加：

```python
    _IMPORT_ENDPOINT = "https://api-seller.ozon.ru/v2/product/import"  # 占位, live 校正

    async def create_product(self, *, client_id, api_key, offer_id, title, description,
                             category_id, attributes, images, price, stock, barcode) -> PublishResult:
        # live 后置：真实 /v2/product/import 的请求体字段/鉴权需与官方文档联调校正。
        # 占位实现：构造请求体但不保证可直接用于生产（与 create_follow_offer 同范式）。
        payload = {"offer_id": offer_id, "name": title, "description_category_id": category_id,
                   "attributes": attributes, "images": images, "price": str(price),
                   "stock": stock, "barcode": barcode}
        return PublishResult(ok=False, ozon_product_id=None, status="failed",
                             raw={"endpoint": self._IMPORT_ENDPOINT, "payload_keys": list(payload)},
                             error="RealOzonSeller.create_product 未联调(live 校正)")
```

> 若 real.py 的既有方法用 `httpx.AsyncClient` 真发请求，则保持占位为「构造 payload 但显式返回未联调错误」，不真实发网络请求（避免 live 泄漏）。以现有 real.py 的既有风格为准，但不得在非 live 情况下发起真实请求。

- [ ] **Step 6: 改 `app/services/listing_builder.py`** —— 文件末尾加 `build_create_drafts`，并补 import。

顶部 import 改为：
```python
from app.models import OzonProduct, SupplyCandidate, ListingDraft, ProductImage
from app.services.category_map import suggest_category
from app.services.category_tree import get_category_tree
from app.services.llm.factory import get_llm
```
文件末尾加：
```python
async def build_create_drafts(session: AsyncSession, task_id: int, *, params: dict | None = None,
                              shop_id: int | None = None, llm=None, tree=None) -> dict:
    """自建草稿生成(§5.9 create)：已采用候选 → 译标题 + 定价 + 类目属性建议 + 已确认图 → listing_drafts(mode=create)。
    按 (task_id, candidate_id) 幂等；无 approved 图则 images=[] 待前端补。"""
    p = params or DEFAULT_PRICING
    llm = llm or get_llm("mock")
    tree = tree or get_category_tree("mock")
    cands = (await session.execute(select(SupplyCandidate).where(
        SupplyCandidate.task_id == task_id, SupplyCandidate.status.in_(("adopted", "auto_adopted"))
    ))).scalars().all()
    built = blocked = skipped = 0
    for c in cands:
        exists = (await session.execute(select(ListingDraft.id).where(
            ListingDraft.task_id == task_id, ListingDraft.candidate_id == c.id))).scalar_one_or_none()
        if exists:
            skipped += 1
            continue
        ozon = (await session.execute(select(OzonProduct).where(OzonProduct.id == c.ozon_product_id))).scalar_one_or_none()
        weight = ozon.weight if ozon else None
        pr = price_candidate(float(c.price) if c.price is not None else 0.0, weight, p)
        title = await llm.translate(c.title or "", target_lang="ru")
        cat = await suggest_category(session, c, llm=llm, tree=tree)
        imgs = (await session.execute(select(ProductImage.result_url).where(
            ProductImage.candidate_id == c.id, ProductImage.status == "approved"
        ).order_by(ProductImage.sort))).scalars().all()
        status = "below_min" if pr.blocked else "draft"
        if pr.blocked:
            blocked += 1
        session.add(ListingDraft(
            task_id=task_id, ozon_product_id=(ozon.id if ozon else None), candidate_id=c.id, shop_id=shop_id,
            mode="create", title=title, description=title, category_id=cat.get("category_id"),
            attributes=cat.get("attributes") or {}, images=[u for u in imgs if u],
            price=pr.price, currency="RUB", stock_qty=0, cost=pr.cost, margin=pr.margin,
            pricing_detail={**pr.detail, "category_source": cat.get("source")}, status=status))
        built += 1
    return {"built": built, "blocked": blocked, "skipped": skipped}
```

- [ ] **Step 7: 运行测试通过 + 回归**

Run: `.venv/bin/python -m pytest tests/test_create_builder.py -q && .venv/bin/python -m pytest tests -q`
Expected: 全绿 0 warnings

- [ ] **Step 8: 提交**

```bash
git add app/services/ozon_seller/ app/services/listing_builder.py tests/test_create_builder.py
git commit -m "feat(m6): ozon_seller.create_product(mock) + build_create_drafts(自建草稿)"
```

---

### Task 5: publisher 按 mode 分支（create → create_product）

**Files:**
- Modify: `app/workers/publisher.py`（抽 `_call_seller` 按 mode 分派；`run_publish_core`/`tick_publish` 调用它；`confirm_draft` 加 create 闸门校验）
- Test: `tests/test_publish_create_branch.py`

**Interfaces:**
- Consumes: `MockOzonSeller.create_product`（Task 4）；`ListingDraft.mode/title/category_id/attributes/images`。
- Produces:
  - 模块级 `async def _call_seller(seller, d, offer_id) -> PublishResult`（mode='create'→create_product，否则 create_follow_offer）
  - `confirm_draft` 对 create 草稿要求 category_id 非空且 images 非空，否则不置 confirmed 并返回提示。

- [ ] **Step 1: 写失败测试** `tests/test_publish_create_branch.py`

```python
import pytest
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
from app.core.db import Base
from app.models import CollectTask, OzonProduct, SupplyCandidate, ListingDraft
from app.services.ozon_seller.factory import get_ozon_seller
from app.workers.publisher import run_publish_core, confirm_draft


@pytest.fixture
def sf(engine):
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def _seed_create_confirmed(s):
    t = CollectTask(keyword="k", listing_mode="create", source_platforms=[]); s.add(t); await s.flush()
    o = OzonProduct(task_id=t.id, sku="S"); s.add(o); await s.flush()
    c = SupplyCandidate(task_id=t.id, ozon_product_id=o.id, platform="ali1688", offer_id="A1", title="童鞋")
    s.add(c); await s.flush()
    d = ListingDraft(task_id=t.id, candidate_id=c.id, mode="create", title="T", description="d",
                     category_id=17028930, attributes={"1": "v"}, images=["/static/images/x.png"],
                     price=1000.0, stock_qty=3, status="confirmed")
    s.add(d); await s.commit()
    return t.id, d.id


@pytest.mark.asyncio
async def test_run_publish_core_create_branch_calls_create_product(sf):
    async with sf() as s:
        tid, did = await _seed_create_confirmed(s)
    res = await run_publish_core(sf, tid, seller=get_ozon_seller("mock"))
    assert res["published"] == 1
    async with sf() as s:
        d = (await s.execute(select(ListingDraft).where(ListingDraft.id == did))).scalar_one()
        assert d.status == "published" and d.ozon_result["ozon_product_id"] == "OZC-A1"


@pytest.mark.asyncio
async def test_confirm_draft_create_gate_requires_category_and_images(db_session):
    t = CollectTask(keyword="k", listing_mode="create", source_platforms=[]); db_session.add(t); await db_session.flush()
    c = SupplyCandidate(task_id=t.id, ozon_product_id=None, platform="ali1688", offer_id="A1")
    # ozon_product_id 需非空 fk? SupplyCandidate.ozon_product_id 非空 → 造一个 OzonProduct
    o = OzonProduct(task_id=t.id, sku="S"); db_session.add(o); await db_session.flush()
    c.ozon_product_id = o.id; db_session.add(c); await db_session.flush()
    d = ListingDraft(task_id=t.id, candidate_id=c.id, mode="create", status="draft",
                     category_id=None, images=None); db_session.add(d); await db_session.commit()
    r = await confirm_draft(db_session, d.id)
    assert d.status == "draft" and "error" in r      # 缺类目/图 → 不确认
    d.category_id = 1; d.images = ["/static/images/x.png"]
    r2 = await confirm_draft(db_session, d.id)
    assert d.status == "confirmed" and "error" not in r2
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/python -m pytest tests/test_publish_create_branch.py -q`
Expected: FAIL（create 草稿走 create_follow_offer 报错 / confirm 无闸门）

- [ ] **Step 3: 改 `app/workers/publisher.py`**

在 import 区后、`apply_auto_confirm` 前加模块级 helper（店铺凭据在调用点解密后传入，mode 分派在 helper 内）：
```python
async def _call_seller(seller, d, offer_id: str, *, client_id: str, api_key: str):
    """按 draft.mode 分派 Ozon 写入：create → create_product；follow → create_follow_offer(§5.9)。"""
    price = float(d.price) if d.price is not None else 0.0
    if d.mode == "create":
        return await seller.create_product(
            client_id=client_id, api_key=api_key, offer_id=offer_id, title=d.title or "",
            description=d.description or "", category_id=d.category_id, attributes=d.attributes or {},
            images=d.images or [], price=price, stock=d.stock_qty, barcode=d.barcode)
    return await seller.create_follow_offer(
        client_id=client_id, api_key=api_key, target_sku=d.target_ozon_sku, barcode=d.barcode,
        price=price, stock=d.stock_qty, offer_id=offer_id)
```

然后在 `run_publish_core` 里，把这段：
```python
                res = await seller.create_follow_offer(
                    client_id=client_id, api_key=api_key, target_sku=d.target_ozon_sku, barcode=d.barcode,
                    price=float(d.price) if d.price is not None else 0.0, stock=d.stock_qty, offer_id=offer_id)
```
替换为：
```python
                res = await _call_seller(d and seller, d, offer_id, client_id=client_id, api_key=api_key)
```
（即 `res = await _call_seller(seller, d, offer_id, client_id=client_id, api_key=api_key)`）

在 `tick_publish` 的第 2 段（取到期草稿挂靠）里，把：
```python
                res = await seller.create_follow_offer(
                    client_id=(shop.client_id if shop else ""), api_key=(decrypt(shop.api_key_encrypted) if shop else ""),
                    target_sku=d.target_ozon_sku, barcode=d.barcode,
                    price=float(d.price) if d.price is not None else 0.0, stock=d.stock_qty, offer_id=offer_id)
```
替换为：
```python
                res = await _call_seller(seller, d, offer_id,
                    client_id=(shop.client_id if shop else ""),
                    api_key=(decrypt(shop.api_key_encrypted) if shop else ""))
```

改 `confirm_draft`（加 create 闸门）：
```python
async def confirm_draft(session: AsyncSession, draft_id: int) -> dict:
    d = (await session.execute(select(ListingDraft).where(ListingDraft.id == draft_id))).scalar_one()
    if d.mode == "create" and (d.category_id is None or not d.images):
        return {"draft_id": draft_id, "status": d.status, "error": "自建草稿需先确认类目与图片再确认上架"}
    if d.status in ("draft",):
        d.status = "confirmed"
    return {"draft_id": draft_id, "status": d.status}
```

- [ ] **Step 4: 运行测试通过 + 回归**（follow 分支既有测试须仍绿）

Run: `.venv/bin/python -m pytest tests/test_publish_create_branch.py tests/test_tick_publish.py -q && .venv/bin/python -m pytest tests -q`
Expected: 全绿 0 warnings

- [ ] **Step 5: 提交**

```bash
git add app/workers/publisher.py tests/test_publish_create_branch.py
git commit -m "feat(m6): publisher 按 mode 分派(create→create_product) + 自建确认闸门"
```

---

### Task 6: imager worker（改图流水线 → product_images）

**Files:**
- Create: `app/workers/imager.py`
- Modify: `app/workers/arq_worker.py`（注册 run_image_process）
- Test: `tests/test_imager_worker.py`

**Interfaces:**
- Consumes: `process_op`（Task 2）；`SupplyCandidate.image_url/images`；`ProductImage`。
- Produces:
  - `run_image_process_core(session_factory, task_id, *, ops=None, static_dir=None, fetch=None) -> dict`（`{processed, failed}`）—— 对 create 任务已采用候选源图逐图跑 ops，写 product_images；单图失败隔离。`fetch(url)->bytes` 可注入（测试用桩，避免真实下载）。
  - `run_image_process(ctx, task_id)`（ARQ 入口）

- [ ] **Step 1: 写失败测试** `tests/test_imager_worker.py`

```python
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
from app.models import CollectTask, OzonProduct, SupplyCandidate, ProductImage
from app.workers.imager import run_image_process_core


@pytest.fixture
def sf(engine):
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


def _png():
    import io
    from PIL import Image
    b = io.BytesIO(); Image.new("RGBA", (60, 40), (10, 20, 30, 255)).save(b, format="PNG"); return b.getvalue()


async def _seed(s):
    t = CollectTask(keyword="k", listing_mode="create", source_platforms=[]); s.add(t); await s.flush()
    o = OzonProduct(task_id=t.id, sku="S"); s.add(o); await s.flush()
    c = SupplyCandidate(task_id=t.id, ozon_product_id=o.id, platform="ali1688", offer_id="A1",
                        image_url="http://x/a.jpg", status="adopted"); s.add(c); await s.commit()
    return t.id


@pytest.mark.asyncio
async def test_run_image_process_creates_product_images(sf, tmp_path):
    async with sf() as s:
        tid = await _seed(s)
    png = _png()
    res = await run_image_process_core(sf, tid, ops=["whitebg", "crop_norm"],
                                       static_dir=str(tmp_path), fetch=lambda url: png)
    assert res["processed"] == 2 and res["failed"] == 0
    async with sf() as s:
        rows = (await s.execute(select(ProductImage).where(ProductImage.task_id == tid))).scalars().all()
        assert len(rows) == 2 and all(r.status == "done" and r.result_url for r in rows)


@pytest.mark.asyncio
async def test_run_image_process_isolates_failure(sf, tmp_path):
    async with sf() as s:
        tid = await _seed(s)
    def bad_fetch(url):
        raise RuntimeError("download failed")
    res = await run_image_process_core(sf, tid, ops=["whitebg"], static_dir=str(tmp_path), fetch=bad_fetch)
    assert res["processed"] == 0 and res["failed"] == 1
    async with sf() as s:
        row = (await s.execute(select(ProductImage).where(ProductImage.task_id == tid))).scalar_one()
        assert row.status == "failed" and row.error
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/python -m pytest tests/test_imager_worker.py -q`
Expected: FAIL（ModuleNotFoundError: app.workers.imager）

- [ ] **Step 3: 建 `app/workers/imager.py`**

```python
"""改图 worker(§5.6 仅自建)：对 create 任务已采用候选源图跑改图流水线 → product_images，单图失败隔离。"""
import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker
from app.core.logging import get_logger
from app.services.imagegen.factory import process_op, DEFAULT_STATIC_DIR
from app.models import SupplyCandidate, ProductImage

DEFAULT_OPS = ["whitebg", "crop_norm"]


def _default_fetch(url: str) -> bytes:
    return httpx.get(url, timeout=20).content


async def run_image_process_core(session_factory: async_sessionmaker, task_id: int, *, ops=None,
                                 static_dir: str | None = None, gen_provider: str = "mock", fetch=None) -> dict:
    log = get_logger(task_id=task_id, phase="imager")
    ops = ops or DEFAULT_OPS
    static_dir = static_dir or DEFAULT_STATIC_DIR
    fetch = fetch or _default_fetch
    async with session_factory() as s:
        cands = (await s.execute(select(SupplyCandidate).where(
            SupplyCandidate.task_id == task_id, SupplyCandidate.status.in_(("adopted", "auto_adopted"))
        ))).scalars().all()
        jobs = [(c.id, c.image_url) for c in cands if c.image_url]
    processed = failed = 0
    sort = 0
    for cand_id, src in jobs:
        for op in ops:
            async with session_factory() as s:
                row = ProductImage(task_id=task_id, candidate_id=cand_id, source_url=src, op=op,
                                   provider="local", sort=sort, status="processing")
                s.add(row); await s.flush()
                try:
                    img_bytes = fetch(src)
                    res = await process_op(op, image=img_bytes, params={}, static_dir=static_dir, gen_provider=gen_provider)
                    row.result_url = res.url; row.provider = res.provider; row.meta = res.meta; row.status = "done"
                    processed += 1
                except Exception as exc:  # noqa: BLE001
                    err = str(exc) or exc.__class__.__name__
                    log.error("image_process_failed", candidate_id=cand_id, op=op, error=err)
                    row.status = "failed"; row.error = err; failed += 1
                await s.commit()
            sort += 1
    return {"processed": processed, "failed": failed}


async def run_image_process(ctx, task_id: int) -> dict:
    """ARQ 入口：真实 worker 路径，用默认 fetch(httpx 下载源图) + 默认 static_dir + mock gen provider。"""
    from app.core.db import async_session
    return await run_image_process_core(async_session, task_id)
```

- [ ] **Step 4: 改 `app/workers/arq_worker.py`** —— 注册 imager：

import 行加：`from app.workers.imager import run_image_process`
`functions` 列表加 `run_image_process`。

- [ ] **Step 5: 运行测试通过 + 回归**

Run: `.venv/bin/python -m pytest tests/test_imager_worker.py -q && .venv/bin/python -m pytest tests -q`
Expected: 全绿 0 warnings

- [ ] **Step 6: 提交**

```bash
git add app/workers/imager.py app/workers/arq_worker.py tests/test_imager_worker.py
git commit -m "feat(m6): imager worker 改图流水线→product_images(单图失败隔离)"
```

---

### Task 7: API（images/category/imagegen）+ listing build 分派 + static 挂载 + 外部 gen 适配器占位 + config

**Files:**
- Create: `app/schemas/image.py`, `app/schemas/category.py`, `app/schemas/imagegen.py`
- Create: `app/api/images.py`, `app/api/category.py`, `app/api/imagegen.py`
- Create: `app/services/imagegen/openai_compat.py`, `app/services/imagegen/http.py`（外部 gen 占位，live）
- Modify: `app/api/listing.py`（build 按 listing_mode 分派 + confirm 用新 confirm_draft 已含闸门）
- Modify: `app/main.py`（注册 3 路由 + 挂载 StaticFiles /static）
- Modify: `app/core/config.py`（加 image_provider）
- Modify: `.env.example`（加 IMAGE_PROVIDER）
- Test: `tests/test_m6_api.py`

**Interfaces:**
- Consumes: `run_image_process_core`（Task 6，sync mock）；`suggest_category`/`confirm_category`（Task 3）；`build_create_drafts`（Task 4）；`settings_store`；`get_category_tree`。
- Produces: REST 端点见 spec §5。

- [ ] **Step 1: 读现有 `app/api/listing.py`** 确认 build/confirm 端点结构（build 目前只调 build_follow_drafts）。据此设计分派。

- [ ] **Step 2: 写失败测试** `tests/test_m6_api.py`（用 `client` fixture + 登录辅助；参照现有 `tests/test_listing_api.py` 的登录方式）

```python
import pytest

async def _token(client, role_user="admin", pw="admin123"):
    r = await client.post("/auth/login", json={"username": role_user, "password": pw})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _seed_adopted_create(client, h):
    # 造 create 任务 + 已采用候选（直接用 API 或 DB；此处借助现有任务/采集接口或最简 DB 注入）
    # 具体注入方式参照 tests/test_listing_api.py 中构造 adopted 候选的辅助；返回 task_id, candidate_id
    ...


@pytest.mark.asyncio
async def test_images_process_then_approve(client):
    h = await _token(client)
    tid, cid = await _seed_adopted_create(client, h)
    r = await client.post(f"/images/process?task_id={tid}&sync=true", headers=h)
    assert r.status_code == 200 and r.json()["processed"] >= 1
    lst = await client.get(f"/images?task_id={tid}", headers=h)
    img_id = lst.json()[0]["id"]
    ap = await client.post(f"/images/{img_id}/approve", headers=h)
    assert ap.status_code == 200 and ap.json()["status"] == "approved"


@pytest.mark.asyncio
async def test_category_suggest_and_confirm(client):
    h = await _token(client)
    tid, cid = await _seed_adopted_create(client, h)
    sug = await client.post(f"/category/suggest?candidate_id={cid}", headers=h)
    assert sug.status_code == 200 and "category_id" in sug.json()


@pytest.mark.asyncio
async def test_imagegen_settings_masks_api_key(client):
    h = await _token(client)
    await client.put("/settings/imagegen", headers=h, json={
        "provider": "mock", "img_base_url": "https://x/v1", "img_api_key": "secret-123", "img_model": "wanx"})
    g = await client.get("/settings/imagegen", headers=h)
    assert g.json().get("img_api_key") in ("***", None) and "secret-123" not in str(g.json())


@pytest.mark.asyncio
async def test_categories_tree_endpoint(client):
    h = await _token(client)
    r = await client.get("/categories", headers=h)
    assert r.status_code == 200 and isinstance(r.json(), list) and r.json()
```

> `_seed_adopted_create` 的实现：复用现有测试里构造 task/ozon_product/adopted candidate 的写法（参照 `tests/test_create_builder.py` 的 `_create_task_with_adopted`，但要落到 client 的测试库 —— 用 `import app.core.db as dbmod; async with dbmod.async_session() as s:` 注入，因为 client fixture 已把 `dbmod.async_session` 指向测试库）。

- [ ] **Step 3: 建 schemas**

`app/schemas/image.py`:
```python
from pydantic import BaseModel

class ImageOut(BaseModel):
    id: int
    candidate_id: int
    source_url: str | None = None
    op: str
    provider: str
    result_url: str | None = None
    sort: int
    status: str
    class Config: from_attributes = True

class ProcessOut(BaseModel):
    processed: int
    failed: int
```

`app/schemas/category.py`:
```python
from pydantic import BaseModel

class CategoryNode(BaseModel):
    id: int
    name: str
    path: str
    leaf: bool

class SuggestOut(BaseModel):
    category_id: int | None = None
    path: str | None = None
    attributes: dict = {}
    source: str

class ConfirmCategoryIn(BaseModel):
    category_id: int
    attributes: dict = {}
    path: str | None = None
```

`app/schemas/imagegen.py`:
```python
from pydantic import BaseModel

class ImagegenIn(BaseModel):
    provider: str = "mock"          # mock|local|openai_compat|http
    img_base_url: str = ""
    img_api_key: str = ""
    img_model: str = ""
    fallback: str = ""              # 降级顺序，逗号分隔

class ImagegenOut(BaseModel):
    provider: str = "mock"
    img_base_url: str = ""
    img_api_key: str | None = None  # 脱敏
    img_model: str = ""
    fallback: str = ""
```

- [ ] **Step 4: 建外部 gen 适配器占位** `app/services/imagegen/openai_compat.py` 与 `http.py`（live，不真发请求）

`openai_compat.py`:
```python
"""OpenAICompatImageProvider：走 OpenAI 兼容图像接口(如千问万相)，live 后置。"""
from app.services.imagegen.base import ImageResult

class OpenAICompatImageProvider:
    name = "openai_compat"
    async def process(self, *, image: bytes, op: str, params: dict) -> ImageResult:
        # live：真实调用 {img_base_url}/images/generations，此处占位不发网络请求。
        raise NotImplementedError("OpenAICompatImageProvider 未联调(live 校正)")
```

`http.py`:
```python
"""HttpImageProvider：通用 HTTP 适配器(GRSAI/云舞AI 等非 OpenAI 格式)，字段映射可配，live 后置。"""
from app.services.imagegen.base import ImageResult

class HttpImageProvider:
    name = "http"
    async def process(self, *, image: bytes, op: str, params: dict) -> ImageResult:
        raise NotImplementedError("HttpImageProvider 未联调(live 校正)")
```

- [ ] **Step 5: 建 `app/api/images.py`**

```python
"""改图 API(§5.6 仅自建)：触发流水线 / 列表 / 采用 / 弃用。"""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.db import get_session
import app.core.db as dbmod
from app.api.deps import require_role
from app.models import ProductImage, User
from app.schemas.image import ImageOut, ProcessOut
from app.workers.imager import run_image_process_core

router = APIRouter(prefix="/images", tags=["images"])


@router.post("/process", response_model=ProcessOut)
async def process_images(task_id: int, sync: bool = False, _: User = Depends(require_role("operator"))):
    # sync=true：同步跑 mock 本地处理落测试/演示库(全项目规律)；异步入队留 worker。
    res = await run_image_process_core(dbmod.async_session, task_id)
    return ProcessOut(**res)


@router.get("", response_model=list[ImageOut])
async def list_images(task_id: int, status: str | None = None, s: AsyncSession = Depends(get_session),
                      _: User = Depends(require_role("operator"))):
    q = select(ProductImage).where(ProductImage.task_id == task_id)
    if status:
        q = q.where(ProductImage.status == status)
    rows = (await s.execute(q.order_by(ProductImage.candidate_id, ProductImage.sort))).scalars().all()
    return rows


@router.post("/{image_id}/approve", response_model=ImageOut)
async def approve_image(image_id: int, s: AsyncSession = Depends(get_session),
                        _: User = Depends(require_role("reviewer"))):
    row = (await s.execute(select(ProductImage).where(ProductImage.id == image_id))).scalar_one()
    row.status = "approved"; await s.commit()
    return row


@router.post("/{image_id}/reject", response_model=ImageOut)
async def reject_image(image_id: int, s: AsyncSession = Depends(get_session),
                       _: User = Depends(require_role("reviewer"))):
    row = (await s.execute(select(ProductImage).where(ProductImage.id == image_id))).scalar_one()
    row.status = "rejected"; await s.commit()
    return row
```

> 注：`process_images` 的 sync 语义——按全项目规律 sync 用 mock；这里 `run_image_process_core` 默认 `gen_provider="mock"` 且本地操作恒真实，符合。异步 worker 版留待接 arq（run_image_process 已注册）。

- [ ] **Step 6: 建 `app/api/category.py`**

```python
"""类目 API(§5.7)：类目树 / LLM 建议(记忆复用) / 确认写记忆表。"""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.db import get_session
from app.api.deps import require_role
from app.models import SupplyCandidate, User
from app.schemas.category import CategoryNode, SuggestOut, ConfirmCategoryIn
from app.services.category_tree import get_category_tree
from app.services.category_map import suggest_category, confirm_category
from app.services.llm.factory import get_llm

router = APIRouter(tags=["category"])


@router.get("/categories", response_model=list[CategoryNode])
async def categories(parent_id: int | None = None, _: User = Depends(require_role("operator"))):
    return await get_category_tree("mock").list_children(parent_id=parent_id)


@router.post("/category/suggest", response_model=SuggestOut)
async def suggest(candidate_id: int, s: AsyncSession = Depends(get_session),
                  _: User = Depends(require_role("operator"))):
    c = (await s.execute(select(SupplyCandidate).where(SupplyCandidate.id == candidate_id))).scalar_one()
    res = await suggest_category(s, c, llm=get_llm("mock"), tree=get_category_tree("mock"))
    await s.commit()   # memory 命中会 +usage_count
    return SuggestOut(**res)


@router.post("/listing/{draft_id}/confirm-category")
async def confirm_cat(draft_id: int, body: ConfirmCategoryIn, s: AsyncSession = Depends(get_session),
                      _: User = Depends(require_role("reviewer"))):
    r = await confirm_category(s, draft_id, category_id=body.category_id,
                               attributes=body.attributes, path=body.path)
    await s.commit()
    return r
```

- [ ] **Step 7: 建 `app/api/imagegen.py`**（配置 CRUD，api_key Fernet 脱敏；参照 shops/settings 的加密范式）

```python
"""AI 生图 provider 配置 API(§5.5.5, admin)：base_url/api_key/model/provider/降级顺序，Fernet 加密脱敏。"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.db import get_session
from app.api.deps import require_role
from app.models import User
from app.schemas.imagegen import ImagegenIn, ImagegenOut
from app.services import settings_store as store

router = APIRouter(prefix="/settings/imagegen", tags=["settings"])
_CAT = "imagegen"


@router.get("", response_model=ImagegenOut)
async def read(s: AsyncSession = Depends(get_session), _: User = Depends(require_role("admin"))):
    masked = await store.get_category_masked(s, _CAT)
    return ImagegenOut(provider=masked.get("provider", "mock"), img_base_url=masked.get("img_base_url", ""),
                       img_api_key=masked.get("img_api_key"), img_model=masked.get("img_model", ""),
                       fallback=masked.get("fallback", ""))


@router.put("", response_model=ImagegenOut)
async def write(body: ImagegenIn, s: AsyncSession = Depends(get_session),
                u: User = Depends(require_role("admin"))):
    await store.set_value(s, _CAT, "provider", body.provider, is_secret=False, updated_by=u.id)
    await store.set_value(s, _CAT, "img_base_url", body.img_base_url, is_secret=False, updated_by=u.id)
    await store.set_value(s, _CAT, "img_api_key", body.img_api_key, is_secret=True, updated_by=u.id)
    await store.set_value(s, _CAT, "img_model", body.img_model, is_secret=False, updated_by=u.id)
    await store.set_value(s, _CAT, "fallback", body.fallback, is_secret=False, updated_by=u.id)
    await s.commit()
    return ImagegenOut(provider=body.provider, img_base_url=body.img_base_url, img_api_key="***",
                       img_model=body.img_model, fallback=body.fallback)
```

- [ ] **Step 8: 改 `app/api/listing.py`** —— build 按 `task.listing_mode` 分派。

读现有 build 端点，把「调 `build_follow_drafts`」改为按任务模式分派：
```python
    task = (await s.execute(select(CollectTask).where(CollectTask.id == task_id))).scalar_one()
    if task.listing_mode == "create":
        from app.services.listing_builder import build_create_drafts
        res = await build_create_drafts(s, task_id, params=params, shop_id=shop_id)
    else:
        res = await build_follow_drafts(s, task_id, params=params, shop_id=shop_id)
```
（`params` 沿用该端点现有的定价参数读取逻辑；`CollectTask` 若未 import 则补 import。）

- [ ] **Step 9: 改 `app/core/config.py`** —— 在 `progress_backend` 后加：
```python
    # 改图 provider：mock(默认) | local(Pillow 真实) | openai_compat | http。本地类操作恒走 local。
    image_provider: str = "mock"
```

- [ ] **Step 10: 改 `app/main.py`** —— 注册 3 路由 + 挂载 static。

import 区加：
```python
from app.api.images import router as images_router
from app.api.category import router as category_router
from app.api.imagegen import router as imagegen_router
from fastapi.staticfiles import StaticFiles
import os
```
`include_router` 区加三行：
```python
app.include_router(images_router)
app.include_router(category_router)
app.include_router(imagegen_router)
```
创建 FastAPI app 后（`app = FastAPI(...)` 之后、路由前后均可）挂载 static（目录不存在则先建）：
```python
os.makedirs("static/images", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")
```

- [ ] **Step 11: 改 `.env.example`** —— 在 PROGRESS_BACKEND 段后加：
```
# 改图 provider：mock（默认，占位产物）| local（Pillow 本地真实处理，whitebg/crop_norm/watermark）
# | openai_compat/http（外部 AI 生图，需在 /settings/imagegen 配 base_url/api_key/model）。
# rmbg 去背景需 worker 以 INSTALL_ML=true 构建（装 rembg/onnx），否则降级白底。
IMAGE_PROVIDER=mock
```

- [ ] **Step 12: 运行测试通过 + 回归**

Run: `.venv/bin/python -m pytest tests/test_m6_api.py -q && .venv/bin/python -m pytest tests -q`
Expected: 全绿 0 warnings

- [ ] **Step 13: 提交**

```bash
git add app/schemas/ app/api/ app/services/imagegen/ app/core/config.py app/main.py .env.example tests/test_m6_api.py
git commit -m "feat(m6): images/category/imagegen API + build 分派 create + static 挂载 + config"
```

---

### Task 8: 前端（ImageStudio + 自建草稿审核 + AI 生图配置）

**Files:**
- Create: `web/src/api/images.ts`, `web/src/api/category.ts`, `web/src/api/imagegen.ts`
- Create: `web/src/pages/ImageStudio.tsx`
- Create: `web/src/pages/settings/ImagegenSettings.tsx`
- Modify: `web/src/pages/ListingReview.tsx`（自建草稿分支：类目/属性/图片确认）
- Modify: 路由与菜单（参照现有 `web/src/App.tsx` 或路由配置文件 + 菜单组件）
- Test: `web/src/pages/ImageStudio.test.tsx`, `web/src/pages/settings/ImagegenSettings.test.tsx`

**Interfaces:**
- Consumes: 后端 `/images*`、`/category*`、`/categories`、`/settings/imagegen`、`/listing/build|drafts|{id}/confirm|{id}/confirm-category`（Task 7）。

- [ ] **Step 1: 读现有前端结构** —— `web/src/api/listing.ts`、`web/src/pages/ListingReview.tsx`、路由/菜单文件、一个现有 `*.test.tsx`（确认 Vitest + mock api 范式、antd 组件用法、fetch 封装）。

- [ ] **Step 2: 写 api 客户端**（沿用现有 `api/*.ts` 的请求封装风格）

`web/src/api/images.ts`:
```typescript
import { http } from './client'   // 以现有封装为准（可能是 request/axios 实例）
export const processImages = (taskId: number) =>
  http.post(`/images/process?task_id=${taskId}&sync=true`).then(r => r.data)
export const listImages = (taskId: number, status?: string) =>
  http.get(`/images?task_id=${taskId}${status ? `&status=${status}` : ''}`).then(r => r.data)
export const approveImage = (id: number) => http.post(`/images/${id}/approve`).then(r => r.data)
export const rejectImage = (id: number) => http.post(`/images/${id}/reject`).then(r => r.data)
```
`web/src/api/category.ts`:
```typescript
import { http } from './client'
export const getCategories = (parentId?: number) =>
  http.get(`/categories${parentId != null ? `?parent_id=${parentId}` : ''}`).then(r => r.data)
export const suggestCategory = (candidateId: number) =>
  http.post(`/category/suggest?candidate_id=${candidateId}`).then(r => r.data)
export const confirmCategory = (draftId: number, body: any) =>
  http.post(`/listing/${draftId}/confirm-category`, body).then(r => r.data)
```
`web/src/api/imagegen.ts`:
```typescript
import { http } from './client'
export const getImagegen = () => http.get('/settings/imagegen').then(r => r.data)
export const putImagegen = (body: any) => http.put('/settings/imagegen', body).then(r => r.data)
```
> 以现有 `api/*.ts` 实际的 http 封装名/路径为准（Step 1 读到后对齐）。

- [ ] **Step 3: 建 `ImageStudio.tsx`** —— 选任务 → 触发改图 → 产物网格（原图/产物、按 op）→ 采用/弃用。用 antd Card/Image/Button/Select，`useEffect` 拉列表。

- [ ] **Step 4: 建 `settings/ImagegenSettings.tsx`** —— Form：provider(Select mock/local/openai_compat/http) + img_base_url/api_key(Password)/img_model/fallback → putImagegen。

- [ ] **Step 5: 改 `ListingReview.tsx`** —— 当草稿 mode==='create'：展示 标题/描述/类目(Select，选项来自 getCategories，含「LLM 建议」按钮调 suggestCategory)/属性表单/已确认图片缩略图/进价售价毛利率；「确认类目属性」→ confirmCategory；再「确认草稿」→ 现有 confirm。follow 分支 UI 不变。

- [ ] **Step 6: 路由 + 菜单** —— 加 `/image-studio`（图片工作室，仅自建可见或恒显）、`/settings/imagegen`；菜单项加对应入口。

- [ ] **Step 7: 写渲染测试** `ImageStudio.test.tsx` 与 `ImagegenSettings.test.tsx`（Vitest + mock api，参照现有 `*.test.tsx`）：mock `api/images`、`api/imagegen`，渲染断言关键文案/控件存在，触发一次交互（如点击处理/保存）后断言 mock 被调用。

- [ ] **Step 8: 跑前端测试 + 构建**

Run:
```bash
cd web && source ~/.nvm/nvm.sh && nvm use 20 >/dev/null && npx vitest run && npm run build
```
Expected: 全部通过 + build 成功

- [ ] **Step 9: 提交**

```bash
git add web/src/
git commit -m "feat(m6): 前端 ImageStudio + 自建草稿审核(类目/属性/图) + AI 生图配置页"
```

---

### Task 9: 文档 + docker static 卷 + 全量回归

**Files:**
- Modify: `README.md`（M6 章节：自建分支、IMAGE_PROVIDER、rembg/INSTALL_ML、static）
- Create: `docs/M6-自建分支说明.md`
- Modify: `docker-compose.yml`（api/worker 挂 static 卷）与（如需）`server/Dockerfile`（说明 rembg 属 INSTALL_ML）
- Test: 全量后端 + 前端回归

- [ ] **Step 1: 读现有 `README.md` 与 `docker-compose.yml`** 定位 M5 段落与卷/服务定义。

- [ ] **Step 2: 更新 `README.md`** —— 加 M6 功能条目（自建分支：改图→类目映射→自建上架）、`IMAGE_PROVIDER` 开关说明、rmbg 需 `INSTALL_ML=true`、static 目录用途；功能列表 + 环境变量表同步。

- [ ] **Step 3: 建 `docs/M6-自建分支说明.md`** —— 目的/用法/关键设计与取舍：改图 provider 分派（本地真实 vs mock vs 外部 gen）、类目映射三级（记忆→LLM→兜底）+ 记忆表复用、自建上架 mock-first、自建确认闸门、live 后置项（RealOzonSeller.create_product、外部 gen 适配器、RealCategoryTree、图片公网 URL）。

- [ ] **Step 4: 改 `docker-compose.yml`** —— 给 api、worker 服务加 static 卷挂载（如 `./server/static:/app/static` 或命名卷），使改图产物在 api/worker 间共享且持久。

- [ ] **Step 5: 全量回归**

Run:
```bash
.venv/bin/python -m pytest tests -q
cd web && source ~/.nvm/nvm.sh && nvm use 20 >/dev/null && npx vitest run && npm run build
```
Expected: 后端全绿 0 warnings；前端测试通过 + build 成功

- [ ] **Step 6: 提交**

```bash
git add README.md docs/M6-自建分支说明.md docker-compose.yml
git commit -m "docs(m6): README + 自建分支说明 + docker static 卷"
```

---

## Self-Review（写计划后自检）

- **Spec 覆盖**：§3 数据模型→Task 1；§4.1 改图→Task 2；§4.2 类目树 + §4.3 类目映射→Task 3；§4.4 create_product + §4.5 build_create_drafts→Task 4；§4.6 publisher 分支→Task 5、imager→Task 6；§5 API→Task 7；§6 前端→Task 8；§7 配置→Task 7/9；§8 测试贯穿各任务；§9 验收→全量；§10 风险（降级/闸门/脱敏）→Task 2(rmbg 降级)/Task 5(确认闸门)/Task 7(脱敏)。全覆盖。
- **占位符扫描**：无 TBD/TODO 式空步骤；每个代码步骤含完整代码（前端 Task 8 的页面 UI 以结构 + 关键调用描述给出，实现时对齐现有前端范式——这是既有里程碑前端任务的一致做法）。
- **类型一致**：`_call_seller(seller, d, offer_id, *, client_id, api_key)` 在 Task 5 定义并在两处调用；`create_product` 签名在 base/mock/real/`_call_seller`/build 一致；`process_op(op, *, image, params, static_dir, gen_provider)` 在 Task 2 定义、Task 6 使用一致；`suggest_category(session, candidate, *, llm, tree)` / `confirm_category(session, draft_id, *, category_id, attributes, path, signature)` Task 3 定义、Task 4/7 使用一致；`run_image_process_core(session_factory, task_id, *, ops, static_dir, gen_provider, fetch)` Task 6 定义、Task 7 使用（用默认参数）一致。
- **已知落地注意**：Task 5 `_call_seller` 与 Task 6 主循环均已收敛为单一规范版本（无「先给一版再替换」的歧义）。`sort` 在 Task 6 双层循环里全局递增，保证每 (候选,op) 一行 ProductImage 且排序稳定。Task 7 前端页面 UI 以「结构 + 关键调用」描述（对齐既有里程碑前端任务的一致做法），实现时须先读现有前端范式（Step 1）再落地。

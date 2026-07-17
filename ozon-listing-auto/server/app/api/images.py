"""改图 API(§5.6 仅自建)：触发流水线 / 列表 / 采用 / 弃用。"""
import base64

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

# 4x4 灰色占位 PNG（Pillow 生成落地为 base64）：process 端点固定注入的离线 fetch 产物，
# 保证本接口全程不发真实网络请求（测试/演示环境；全项目 sync=mock 规律的延伸——
# 见 .env.example 对 OZON_SELLER_PROVIDER 的说明：所有 sync 路径恒用 mock/离线产物）。
_PLACEHOLDER_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAQAAAAECAIAAAAmkwkpAAAAE0lEQVR4nGM8ceIEAwwwwVl4OQB2NAJgnoBkZwAAAABJRU5ErkJggg=="
)


def _offline_fetch(url: str) -> bytes:
    """process 端点专用离线 fetch：忽略 url，返回内嵌占位图，避免真实下载源图。"""
    return _PLACEHOLDER_PNG


@router.post("/process", response_model=ProcessOut)
async def process_images(task_id: int, sync: bool = False, _: User = Depends(require_role("operator"))):
    # sync 语义同全项目规律(如 /listing/publish?sync=true)：同步处理落库供测试/演示，
    # 恒用离线占位图而非真实下载；真实异步下载走 arq 的 run_image_process(已注册，留待接线)。
    res = await run_image_process_core(dbmod.async_session, task_id, fetch=_offline_fetch)
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

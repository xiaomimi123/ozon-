"""imager worker 测试：改图流水线 → product_images，单图失败隔离。"""
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
    t = CollectTask(name="k", entry_type="keyword", entry_value="k", listing_mode="create", source_platforms=[])
    s.add(t); await s.flush()
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

import pytest
from sqlalchemy import select, func
from app.services.ingest import dedup, upsert_products
from app.services.ozon_market.base import OzonProductDTO
from app.models import OzonProduct

def _dto(sku, phash=None, parent=None):
    return OzonProductDTO(sku=sku, title=sku, phash=phash, parent_sku=parent)

def test_dedup_by_sku_and_phash():
    dtos = [_dto("A", "p1"), _dto("A", "p1"), _dto("B", "p1"), _dto("C", "p2")]
    out = dedup(dtos)
    skus = sorted(d.sku for d in out)
    assert skus == ["A", "C"]   # A 保留; B 与 A 同 phash 去掉; C 不同 phash 保留

def test_dedup_keeps_variants():
    dtos = [_dto("V1", "px", parent="P"), _dto("V2", "py", parent="P")]
    out = dedup(dtos)
    assert {d.sku for d in out} == {"V1", "V2"}   # 变体不同 phash 各自保留

@pytest.mark.asyncio
async def test_upsert_idempotent(db_session):
    dtos = [_dto("A", "p1"), _dto("D", "p9")]
    r1 = await upsert_products(db_session, task_id=1, dtos=dtos)
    await db_session.commit()
    r2 = await upsert_products(db_session, task_id=1, dtos=dtos)  # 再来一次
    await db_session.commit()
    total = (await db_session.execute(select(func.count()).select_from(OzonProduct))).scalar_one()
    assert r1["inserted"] == 2
    assert r2["inserted"] == 0 and r2["skipped"] == 2
    assert total == 2

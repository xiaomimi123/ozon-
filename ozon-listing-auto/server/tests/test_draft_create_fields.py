"""ListingDraft 自建上品扩字段：type_id/尺寸/重量/单位。"""
import pytest
from app.models import ListingDraft


@pytest.mark.asyncio
async def test_draft_has_create_fields(db_session):
    d = ListingDraft(task_id=1, candidate_id=1, mode="create", type_id=971,
                     depth=100, width=80, height=50, weight=250)
    db_session.add(d); await db_session.flush()
    got = await db_session.get(ListingDraft, d.id)
    assert got.type_id == 971 and got.depth == 100 and got.dimension_unit == "mm" and got.weight_unit == "g"

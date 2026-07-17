import pytest
from sqlalchemy import select
from app.models import PublishPace, CollectTask

@pytest.mark.asyncio
async def test_publish_pace(db_session):
    t = CollectTask(name="t", entry_type="keyword", entry_value="x", provider="mock", source_platforms=["ali1688"])
    db_session.add(t); await db_session.flush()
    p = PublishPace(task_id=t.id, min_interval_sec=30, max_interval_sec=90, daily_limit=50, active_hours=[8, 22])
    db_session.add(p)
    g = PublishPace(task_id=None)  # 全局默认
    db_session.add(g); await db_session.commit()
    got = (await db_session.execute(select(PublishPace).where(PublishPace.task_id == t.id))).scalar_one()
    assert got.min_interval_sec == 30 and got.active_hours == [8, 22] and got.wait_ozon_approval is True
    assert g.daily_limit == 200 and g.active_hours == [9, 23]

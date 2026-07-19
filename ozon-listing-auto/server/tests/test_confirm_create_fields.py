"""confirm-create-fields 端点测试：写回自建草稿必填字段(type_id/尺寸/重量)后 confirm 才能通过。"""
import pytest
from app.core.security import hash_password
from app.models import User, CollectTask, OzonProduct, SupplyCandidate, ListingDraft


async def _seed_create_draft(client, db_session, role="admin"):
    """造一条 mode=create、有 category_id/images 但缺 type_id/尺寸/重量 的草稿。"""
    db_session.add(User(username="u", password_hash=hash_password("p"), role=role))
    t = CollectTask(name="t", entry_type="keyword", entry_value="x", listing_mode="create", source_platforms=[])
    db_session.add(t); await db_session.flush()
    o = OzonProduct(task_id=t.id, sku="S"); db_session.add(o); await db_session.flush()
    c = SupplyCandidate(task_id=t.id, ozon_product_id=o.id, platform="ali1688", offer_id="A1", title="童鞋")
    db_session.add(c); await db_session.flush()
    d = ListingDraft(task_id=t.id, candidate_id=c.id, mode="create", title="T", description="d",
                     category_id=17028930, images=["/static/images/x.png"], status="draft")
    db_session.add(d); await db_session.commit()
    tok = (await client.post("/auth/login", data={"username": "u", "password": "p"})).json()["access_token"]
    return d.id, {"Authorization": f"Bearer {tok}"}


@pytest.mark.asyncio
async def test_confirm_create_fields_writes_and_gates(client, db_session):
    did, h = await _seed_create_draft(client, db_session)
    # 缺 type_id/尺寸 时 confirm 被拒
    c0 = await client.post(f"/listing/{did}/confirm", headers=h)
    assert c0.status_code == 200
    assert "error" in c0.json()
    body = {"type_id": 93080, "depth": 100, "width": 80, "height": 50, "weight": 250,
            "attributes": {"85": {"dictionary_value_id": 1000}}}
    r = await client.post(f"/listing/{did}/confirm-create-fields", json=body, headers=h)
    assert r.status_code == 200
    assert r.json()["ok"] is True
    # 补齐后 confirm 通过
    c = await client.post(f"/listing/{did}/confirm", headers=h)
    assert c.status_code == 200
    assert c.json()["status"] == "confirmed"


@pytest.mark.asyncio
async def test_confirm_create_fields_requires_operator_role(client, db_session):
    did, h = await _seed_create_draft(client, db_session, role="reviewer")
    body = {"type_id": 93080, "depth": 100, "width": 80, "height": 50, "weight": 250}
    r = await client.post(f"/listing/{did}/confirm-create-fields", json=body, headers=h)
    assert r.status_code == 403

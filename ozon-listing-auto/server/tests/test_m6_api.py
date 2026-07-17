"""M6 API 测试：images(process/list/approve) + category(suggest) + imagegen 配置脱敏 + categories 树。"""
import pytest
from app.core.security import hash_password
from app.models import User, CollectTask, OzonProduct, SupplyCandidate


async def _seed_adopted_create(client, db_session):
    db_session.add(User(username="u", password_hash=hash_password("p"), role="admin"))
    t = CollectTask(name="t", entry_type="keyword", entry_value="x", listing_mode="create", provider="mock",
                    source_platforms=["ali1688"], review_config={"listing_review_required": True})
    db_session.add(t); await db_session.flush()
    p = OzonProduct(task_id=t.id, sku="OZSKU1", title="x", barcode="460", weight=0.5)
    db_session.add(p); await db_session.flush()
    c = SupplyCandidate(task_id=t.id, ozon_product_id=p.id, platform="ali1688", offer_id="A1", title="童鞋",
                        price=15.0, status="adopted", score_total=90.0, image_url="https://img.example/a.jpg")
    db_session.add(c); await db_session.commit()
    tok = (await client.post("/auth/login", data={"username": "u", "password": "p"})).json()["access_token"]
    return t.id, c.id, {"Authorization": f"Bearer {tok}"}


@pytest.mark.asyncio
async def test_images_process_then_approve(client, db_session):
    tid, cid, h = await _seed_adopted_create(client, db_session)
    r = await client.post(f"/images/process?task_id={tid}&sync=true", headers=h)
    assert r.status_code == 200 and r.json()["processed"] >= 1
    lst = await client.get(f"/images?task_id={tid}", headers=h)
    img_id = lst.json()[0]["id"]
    ap = await client.post(f"/images/{img_id}/approve", headers=h)
    assert ap.status_code == 200 and ap.json()["status"] == "approved"


@pytest.mark.asyncio
async def test_category_suggest_and_confirm(client, db_session):
    tid, cid, h = await _seed_adopted_create(client, db_session)
    sug = await client.post(f"/category/suggest?candidate_id={cid}", headers=h)
    assert sug.status_code == 200 and "category_id" in sug.json()


@pytest.mark.asyncio
async def test_imagegen_settings_masks_api_key(client, db_session):
    tid, cid, h = await _seed_adopted_create(client, db_session)
    await client.put("/settings/imagegen", headers=h, json={
        "provider": "mock", "img_base_url": "https://x/v1", "img_api_key": "secret-123", "img_model": "wanx"})
    g = await client.get("/settings/imagegen", headers=h)
    assert g.json().get("img_api_key") in ("***", None) and "secret-123" not in str(g.json())


@pytest.mark.asyncio
async def test_categories_tree_endpoint(client, db_session):
    tid, cid, h = await _seed_adopted_create(client, db_session)
    r = await client.get("/categories", headers=h)
    assert r.status_code == 200 and isinstance(r.json(), list) and r.json()

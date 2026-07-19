"""回归测试(最终审 BLOCKER)：PUT /settings/system 必须持久化 ozon_publish_dry_run，
否则 pydantic v2 会静默丢弃 SystemIn 里未声明的字段，导致 real 模式下 dry_run 永远读到默认 "true"，
无法真发(见 resolve_seller)。本测试从 API 层面覆盖：写入 -> 读回 -> resolve_seller 实际生效。"""
import pytest
from app.core.security import hash_password
from app.models import User
from app.services.ozon_seller.resolve import resolve_seller
from app.services.ozon_seller.real import RealOzonSeller


async def _seed_admin_login(client, db_session, username="u_dryrun"):
    db_session.add(User(username=username, password_hash=hash_password("p"), role="admin"))
    await db_session.commit()
    tok = (await client.post("/auth/login", data={"username": username, "password": "p"})).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


@pytest.mark.asyncio
async def test_put_system_persists_ozon_publish_dry_run_false(client, db_session):
    h = await _seed_admin_login(client, db_session)

    put = await client.put(
        "/settings/system",
        json={"ozon_seller_provider": "real", "category_tree_provider": "mock", "ozon_publish_dry_run": "false"},
        headers=h,
    )
    assert put.status_code == 200
    assert put.json()["ozon_publish_dry_run"] == "false"

    got = await client.get("/settings/system", headers=h)
    assert got.status_code == 200
    body = got.json()
    assert body["ozon_seller_provider"] == "real"
    assert body["ozon_publish_dry_run"] == "false", f"PUT 未持久化 dry_run 开关: {body}"

    seller = await resolve_seller(db_session)
    assert isinstance(seller, RealOzonSeller)
    assert seller._dry_run is False


@pytest.mark.asyncio
async def test_get_system_default_dry_run_true(client, db_session):
    h = await _seed_admin_login(client, db_session, username="u_dryrun_default")
    got = await client.get("/settings/system", headers=h)
    assert got.status_code == 200
    assert got.json()["ozon_publish_dry_run"] == "true"

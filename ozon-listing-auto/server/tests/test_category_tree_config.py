import pytest, httpx
from app.core.security import hash_password
from app.models import User


async def _admin(client, db_session):
    db_session.add(User(username="a", password_hash=hash_password("p"), role="admin"))
    await db_session.commit()
    tok = (await client.post("/auth/login", data={"username": "a", "password": "p"})).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


@pytest.mark.asyncio
async def test_system_category_tree_provider_roundtrip(client, db_session):
    h = await _admin(client, db_session)
    await client.put("/settings/system", headers=h, json={"ozon_seller_provider": "mock", "category_tree_provider": "real"})
    g = (await client.get("/settings/system", headers=h)).json()
    assert g["category_tree_provider"] == "real" and g["ozon_seller_provider"] == "mock"


@pytest.mark.asyncio
async def test_build_category_tree_selects(db_session):
    from app.services.category_tree import build_category_tree, MockCategoryTree
    from app.services.ozon_market.category_tree_real import RealCategoryTree
    assert isinstance(await build_category_tree(db_session, "mock"), MockCategoryTree)
    assert isinstance(await build_category_tree(db_session, "real"), RealCategoryTree)


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    async def _f(*a, **k): return None
    monkeypatch.setattr("app.services.ozon_market.composer_http.asyncio.sleep", _f)


@pytest.mark.asyncio
async def test_real_tree_blocks_raise():
    from app.services.ozon_market.category_tree_real import RealCategoryTree
    from app.services.ozon_market.composer_http import CrawlerBlockedError
    t = RealCategoryTree(max_retries=2, transport=httpx.MockTransport(lambda r: httpx.Response(403)))
    with pytest.raises(CrawlerBlockedError):
        await t.list_children(parent_id=None)


@pytest.mark.asyncio
async def test_categories_endpoint_default_mock(client, db_session):
    h = await _admin(client, db_session)
    r = await client.get("/categories", headers=h)   # 默认 mock, 返回固定小树根
    assert r.status_code == 200 and isinstance(r.json(), list) and r.json()


def test_parse_category_children_tolerant():
    from app.services.ozon_market.category_tree_real import _parse_category_children
    assert _parse_category_children([]) == []
    assert _parse_category_children({"categories": [1, 2, 3]}) == []
    out = _parse_category_children({"categories": [{"id": "abc"}, {"id": 5, "name": "X"}]})
    assert len(out) == 1 and out[0]["id"] == 5

import json, pytest, httpx
from app.core.security import hash_password
from app.models import User


async def _admin(client, db_session):
    db_session.add(User(username="a", password_hash=hash_password("p"), role="admin"))
    await db_session.commit()
    tok = (await client.post("/auth/login", data={"username": "a", "password": "p"})).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


@pytest.mark.asyncio
async def test_sources_settings_roundtrip(client, db_session):
    h = await _admin(client, db_session)
    await client.put("/settings/sources", headers=h, json={
        "ali1688_image_search_url": "https://h5.1688.com/img", "ali1688_method": "POST",
        "ali1688_extra_params": '{"sign":"X"}', "ali1688_offer_list_path": "result.items"})
    g = (await client.get("/settings/sources", headers=h)).json()
    assert g["ali1688_image_search_url"] == "https://h5.1688.com/img" and g["ali1688_method"] == "POST"
    assert g["ali1688_offer_list_path"] == "result.items"


@pytest.mark.asyncio
async def test_sources_import_token_mask_and_paths(client, db_session):
    h = await _admin(client, db_session)
    await client.put("/settings/sources", headers=h, json={
        "import_token": "tok-secret", "import_1688_list_path": "data.items"})
    g = (await client.get("/settings/sources", headers=h)).json()
    assert g["import_token"] == "***" and "tok-secret" not in str(g)
    assert g["import_1688_list_path"] == "data.items"

    # 留空不覆盖 import_token；其它路径字段正常整表覆盖
    await client.put("/settings/sources", headers=h, json={
        "import_token": "", "import_1688_list_path": "data.items2"})
    g2 = (await client.get("/settings/sources", headers=h)).json()
    assert g2["import_token"] == "***"          # 仍脱敏 → 底层值还在
    assert g2["import_1688_list_path"] == "data.items2"
    from app.services.settings_store import get_value
    assert await get_value(db_session, "sources", "import_token") == "tok-secret"  # 未被清空覆盖


@pytest.mark.asyncio
async def test_sources_ali1688_fields_unaffected_by_import_token(client, db_session):
    h = await _admin(client, db_session)
    await client.put("/settings/sources", headers=h, json={
        "ali1688_image_search_url": "https://h5.1688.com/img", "ali1688_method": "POST",
        "ali1688_extra_params": '{"sign":"X"}', "ali1688_offer_list_path": "result.items"})
    g = (await client.get("/settings/sources", headers=h)).json()
    assert g["ali1688_image_search_url"] == "https://h5.1688.com/img" and g["ali1688_method"] == "POST"
    assert g["ali1688_offer_list_path"] == "result.items"
    assert g["import_token"] == ""   # 未设置时明文空


@pytest.mark.asyncio
async def test_get_source_conf_parses_json(db_session):
    from app.services.sources.conf import get_source_conf, DEFAULT_SOURCE_CONF
    from app.services.settings_store import set_value
    conf = await get_source_conf(db_session)
    assert conf["ali1688_offer_list_path"] == DEFAULT_SOURCE_CONF["ali1688_offer_list_path"]
    await set_value(db_session, "sources", "ali1688_extra_params", '{"sign":"abc"}', is_secret=False)
    await set_value(db_session, "sources", "ali1688_extra_headers", "not-json", is_secret=False)
    await db_session.commit()
    conf2 = await get_source_conf(db_session)
    assert conf2["ali1688_extra_params"] == {"sign": "abc"}   # JSON 串→dict
    assert conf2["ali1688_extra_headers"] == {}               # 坏 JSON→回退默认值,不崩溃


@pytest.mark.asyncio
async def test_ali1688_image_search_uses_config(db_session):
    from app.services.sources.ali1688 import Ali1688Provider
    seen = {}
    def h(req):
        seen["url"] = str(req.url); seen["method"] = req.method
        seen["cookie"] = req.headers.get("Cookie")
        return httpx.Response(200, json={"result": {"items": [
            {"offerId": 12, "subject": "童鞋", "priceInfo": {"price": "9.9"}, "imageUrl": "u"}]}})
    conf = {"ali1688_image_search_url": "https://h5.1688.com/img", "ali1688_method": "GET",
            "ali1688_extra_params": {"sign": "S"}, "ali1688_extra_headers": {"x-h": "1"},
            "ali1688_offer_list_path": "result.items", "ali1688_keyword_search_url": ""}
    prov = Ali1688Provider(conf, transport=httpx.MockTransport(h))
    out = await prov.image_search("http://img/a.jpg", session={"cookie": "sess=1"})
    assert "h5.1688.com/img" in seen["url"] and "sign=S" in seen["url"] and "imageAddress" in seen["url"]
    assert seen["cookie"] == "sess=1" and len(out) == 1 and out[0].offer_id == "12" and out[0].price == 9.9


def test_parse_offers_configurable_path_and_tolerant():
    from app.services.sources.parser_ali import parse_offers
    p = {"result": {"items": [{"offerId": 1, "subject": "a"}, {"no": "id"}, "notdict"]}}
    out = parse_offers(p, "result.items")
    assert len(out) == 1 and out[0].offer_id == "1"
    assert parse_offers({}, "data.offerList") == [] and parse_offers([], "x") == []


@pytest.mark.asyncio
async def test_build_source_provider_ali1688(db_session):
    from app.services.sources.factory import build_source_provider
    from app.services.sources.ali1688 import Ali1688Provider
    from app.services.sources.mock import MockSourceProvider

    class _SF:
        def __call__(self): return _Ctx()
    class _Ctx:
        async def __aenter__(self): return db_session
        async def __aexit__(self, *a): return False
    prov = await build_source_provider(_SF(), "ali1688")
    assert isinstance(prov, Ali1688Provider)
    assert isinstance(await build_source_provider(_SF(), "mock"), MockSourceProvider)

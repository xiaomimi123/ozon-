import pytest
from app.core.security import hash_password
from app.models import User


async def _admin(client, db_session):
    db_session.add(User(username="a", password_hash=hash_password("p"), role="admin"))
    await db_session.commit()
    tok = (await client.post("/auth/login", data={"username": "a", "password": "p"})).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


@pytest.mark.asyncio
async def test_crawler_settings_mask_and_keep_blank(client, db_session):
    h = await _admin(client, db_session)
    await client.put("/settings/crawler", headers=h, json={
        "cookie": "abc=1; def=2", "proxy": "http://u:pw@h:8080", "timeout": 15, "max_retries": 3})
    g = (await client.get("/settings/crawler", headers=h)).json()
    assert g["cookie"] == "***" and g["proxy"] == "***"           # 脱敏
    assert str(g["timeout"]) in ("15", "15.0")
    # 留空不覆盖 cookie/proxy
    await client.put("/settings/crawler", headers=h, json={"cookie": "", "proxy": "", "timeout": 25})
    from app.services.crawler_conf import get_crawler_conf
    conf = await get_crawler_conf(db_session)
    assert conf["cookie"] == "abc=1; def=2" and conf["proxy"] == "http://u:pw@h:8080"
    assert conf["timeout"] == 25.0


@pytest.mark.asyncio
async def test_crawler_conf_defaults(db_session):
    from app.services.crawler_conf import get_crawler_conf, DEFAULT_CRAWLER
    conf = await get_crawler_conf(db_session)
    assert conf["max_retries"] == DEFAULT_CRAWLER["max_retries"] and conf["cookie"] in ("", None)


@pytest.mark.asyncio
async def test_system_seller_provider_toggle(client, db_session):
    h = await _admin(client, db_session)
    await client.put("/settings/system", headers=h, json={"ozon_seller_provider": "real"})
    g = (await client.get("/settings/system", headers=h)).json()
    assert g["ozon_seller_provider"] == "real"

import pytest
from app.core.security import hash_password
from app.models import User


async def _admin(client, db_session):
    db_session.add(User(username="a", password_hash=hash_password("p"), role="admin"))
    await db_session.commit()
    tok = (await client.post("/auth/login", data={"username": "a", "password": "p"})).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


@pytest.mark.asyncio
async def test_imagegen_settings_new_fields(client, db_session):
    h = await _admin(client, db_session)
    await client.put("/settings/imagegen", headers=h, json={
        "provider": "http", "img_base_url": "https://g/api", "img_api_key": "k", "img_model": "m",
        "fallback": "", "img_request_template": '{"p":"{prompt}"}', "img_response_path": "data.0.url"})
    g = (await client.get("/settings/imagegen", headers=h)).json()
    assert g["provider"] == "http" and g["img_request_template"] == '{"p":"{prompt}"}'
    assert g["img_response_path"] == "data.0.url" and g["img_api_key"] in ("***", None)


@pytest.mark.asyncio
async def test_get_configured_gen_provider(db_session, tmp_path):
    from app.services.imagegen.config import get_configured_gen_provider
    from app.services.imagegen.mock import MockImageProvider
    # 无配置 → mock
    assert isinstance(await get_configured_gen_provider(db_session, static_dir=str(tmp_path)), MockImageProvider)
    from app.services.settings_store import set_value
    await set_value(db_session, "imagegen", "provider", "openai_compat", is_secret=False)
    await set_value(db_session, "imagegen", "img_base_url", "https://a/v1", is_secret=False)
    await set_value(db_session, "imagegen", "img_api_key", "sk", is_secret=True)
    await set_value(db_session, "imagegen", "img_model", "wanx", is_secret=False)
    await db_session.commit()
    from app.services.imagegen.openai_compat import OpenAICompatImageProvider
    prov = await get_configured_gen_provider(db_session, static_dir=str(tmp_path))
    assert isinstance(prov, OpenAICompatImageProvider) and prov.model == "wanx"


@pytest.mark.asyncio
async def test_process_op_uses_gen_provider_obj(tmp_path):
    from app.services.imagegen.factory import process_op
    from app.services.imagegen.mock import MockImageProvider
    res = await process_op("gen", image=b"x", params={}, static_dir=str(tmp_path),
                           gen_provider_obj=MockImageProvider())
    assert res.provider == "mock"


def test_get_image_provider_rejects_openai_compat_and_http_by_name():
    from app.services.imagegen.factory import get_image_provider
    with pytest.raises(ValueError):
        get_image_provider("openai_compat")
    with pytest.raises(ValueError):
        get_image_provider("http")

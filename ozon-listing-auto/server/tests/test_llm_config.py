import pytest
from app.core.security import hash_password
from app.models import User


async def _admin(client, db_session):
    db_session.add(User(username="a", password_hash=hash_password("p"), role="admin"))
    await db_session.commit()
    tok = (await client.post("/auth/login", data={"username": "a", "password": "p"})).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


@pytest.mark.asyncio
async def test_llm_settings_mask_and_keep_blank(client, db_session):
    h = await _admin(client, db_session)
    await client.put("/settings/llm", headers=h, json={
        "llm_provider": "openai", "llm_base_url": "https://x/v1", "llm_api_key": "sk-secret", "llm_model": "qwen-plus"})
    g = (await client.get("/settings/llm", headers=h)).json()
    assert g["llm_api_key"] in ("***", None) and "sk-secret" not in str(g)
    assert g["llm_provider"] == "openai" and g["llm_model"] == "qwen-plus"
    # 留空不覆盖 api_key
    await client.put("/settings/llm", headers=h, json={
        "llm_provider": "openai", "llm_base_url": "https://y/v1", "llm_api_key": "", "llm_model": "qwen-max"})
    from app.services.settings_store import get_value
    assert await get_value(db_session, "llm", "llm_api_key") == "sk-secret"     # 密钥保留
    from app.services.settings_store import get_category
    assert (await get_category(db_session, "llm"))["llm_base_url"] == "https://y/v1"  # 其他字段更新


@pytest.mark.asyncio
async def test_get_configured_llm_selects_by_config(db_session, monkeypatch):
    from app.services.llm.config import get_configured_llm
    from app.services.llm.mock import MockLLM
    from app.services.llm.openai_compat import OpenAICompatLLM
    # 无配置 → 回退 env（默认 mock）
    llm = await get_configured_llm(db_session)
    assert isinstance(llm, MockLLM)
    # 配 openai + key → 真实
    from app.services.settings_store import set_value
    await set_value(db_session, "llm", "llm_provider", "openai", is_secret=False)
    await set_value(db_session, "llm", "llm_api_key", "sk-x", is_secret=True)
    await set_value(db_session, "llm", "llm_base_url", "https://x/v1", is_secret=False)
    await set_value(db_session, "llm", "llm_model", "qwen-plus", is_secret=False)
    await db_session.commit()
    llm2 = await get_configured_llm(db_session)
    assert isinstance(llm2, OpenAICompatLLM) and llm2.model == "qwen-plus"
    # openai 但无 key → 回退 mock
    await set_value(db_session, "llm", "llm_api_key", "", is_secret=True)   # 覆盖为空
    await db_session.commit()

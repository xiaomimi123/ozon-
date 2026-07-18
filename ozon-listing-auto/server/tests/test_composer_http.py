import pytest, httpx
from app.services.ozon_market.composer_http import composer_fetch, CrawlerBlockedError


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    async def _f(*a, **k): return None
    monkeypatch.setattr("app.services.ozon_market.composer_http.asyncio.sleep", _f)


@pytest.mark.asyncio
async def test_composer_fetch_injects_cookie_and_returns_json():
    seen = {}
    def h(req): seen["cookie"] = req.headers.get("Cookie"); return httpx.Response(200, json={"ok": 1})
    out = await composer_fetch("https://x/api", {"categoryId": 5}, cookie="a=1", transport=httpx.MockTransport(h))
    assert out == {"ok": 1} and seen["cookie"] == "a=1"


@pytest.mark.asyncio
async def test_composer_fetch_blocks_raise():
    def h(req): return httpx.Response(403)
    with pytest.raises(CrawlerBlockedError):
        await composer_fetch("https://x/api", {}, max_retries=2, transport=httpx.MockTransport(h))

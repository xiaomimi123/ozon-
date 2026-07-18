"""OzonComposerProvider 硬化测试：cookie 头注入、307/403/429 反爬退避、CrawlerBlockedError。"""
import pytest
import httpx
from app.services.ozon_market.composer import OzonComposerProvider, CrawlerBlockedError


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    async def _fast(*a, **k):
        return None
    monkeypatch.setattr("app.services.ozon_market.composer.asyncio.sleep", _fast)


@pytest.mark.asyncio
async def test_cookie_header_injected_and_success():
    seen = {}
    def handler(request: httpx.Request) -> httpx.Response:
        seen["cookie"] = request.headers.get("Cookie")
        return httpx.Response(200, json={"widgetStates": {}})
    prov = OzonComposerProvider(cookie="abc=1; def=2", transport=httpx.MockTransport(handler))
    await prov.search_by_keyword("phone", 1)
    assert seen["cookie"] == "abc=1; def=2"


@pytest.mark.asyncio
async def test_307_retried_then_success():
    calls = {"n": 0}
    def handler(request):
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(307, headers={"Location": "/challenge"})
        return httpx.Response(200, json={"widgetStates": {}})
    prov = OzonComposerProvider(max_retries=5, transport=httpx.MockTransport(handler))
    out = await prov.search_by_keyword("phone", 1)
    assert calls["n"] == 3 and out == []


@pytest.mark.asyncio
async def test_persistent_block_raises_actionable_error():
    def handler(request):
        return httpx.Response(403)
    prov = OzonComposerProvider(max_retries=3, transport=httpx.MockTransport(handler))
    with pytest.raises(CrawlerBlockedError):
        await prov.search_by_keyword("phone", 1)

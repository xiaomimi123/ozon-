import pytest
from app.services.sources.factory import get_source_provider
from app.services.sources.base import SupplyCandidateDTO

@pytest.mark.asyncio
async def test_factory_returns_mock():
    p = get_source_provider("mock")
    assert p.platform == "mock"
    items = await p.keyword_search("phone", session=None)
    assert items and isinstance(items[0], SupplyCandidateDTO)

def test_factory_unknown_raises():
    with pytest.raises(ValueError):
        get_source_provider("nope")

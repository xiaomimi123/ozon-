import math
import pytest
from app.services.embedding.mock import MockEmbedder
from app.services.embedding.factory import get_embedder

def _cos(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)); nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb)

@pytest.mark.asyncio
async def test_mock_embedder_deterministic_and_normalized():
    e = MockEmbedder()
    v1 = await e.embed_image("https://img/a.jpg")
    v1b = await e.embed_image("https://img/a.jpg")
    v2 = await e.embed_image("https://img/b.jpg")
    assert e.dim == 512 and len(v1) == 512
    assert _cos(v1, v1b) > 0.999          # 相同 URL → 相同向量
    assert _cos(v1, v2) < 0.5             # 不同 URL → 低相似
    assert abs(math.sqrt(sum(x * x for x in v1)) - 1.0) < 1e-6   # 归一化

def test_factory_default_mock():
    assert get_embedder("mock").dim == 512
    with pytest.raises(ValueError):
        get_embedder("nope")

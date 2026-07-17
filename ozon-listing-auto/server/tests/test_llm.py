import pytest
from app.services.llm.mock import MockLLM
from app.services.llm.factory import get_llm

@pytest.mark.asyncio
async def test_mock_llm_deterministic():
    m = MockLLM()
    assert m.name == "mock"
    assert await m.translate("привет", "zh") == "привет"      # 恒等透传(确定性)
    assert await m.extract_json("从标题抽属性: 黑色耳机") == {}
    assert await m.chat([{"role": "user", "content": "hi"}]) == "hi"

def test_factory_default_mock():
    assert get_llm().name == "mock"
    with pytest.raises(ValueError):
        get_llm("nope")

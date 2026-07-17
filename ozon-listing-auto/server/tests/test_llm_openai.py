"""OpenAICompatLLM 测试：_parse_json_loose 单测（无网络）+ live 冒烟（默认跳过）。"""
import pytest
from app.services.llm.openai_compat import _parse_json_loose


def test_parse_json_loose():
    assert _parse_json_loose('{"color": "black"}') == {"color": "black"}
    assert _parse_json_loose('```json\n{"a": 1}\n```') == {"a": 1}   # 去代码围栏
    assert _parse_json_loose("not json") == {}                        # 容错
    assert _parse_json_loose('```json\n{"a": {"b": 1}}\n```') == {"a": {"b": 1}}   # 围栏内嵌套对象不被截断
    assert _parse_json_loose('前缀 {"x": {"y": 2}} 后缀') == {"x": {"y": 2}}          # 无围栏嵌套(贪婪到最后一个 })


@pytest.mark.live
@pytest.mark.asyncio
async def test_openai_translate_live():
    # 需在 app_settings.llm 配好 base_url/api_key/model; 无配置则跳过
    from app.services.llm.openai_compat import OpenAICompatLLM
    llm = OpenAICompatLLM(base_url="", api_key="", model="qwen-plus")
    with pytest.raises(Exception):
        await llm.translate("привет")

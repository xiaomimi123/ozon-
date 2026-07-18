"""真实 LLM 冒烟(@live 默认跳过)。跑法：
先在 /settings/llm 配好，或设 LLM_BASE_URL/LLM_API_KEY/LLM_MODEL 环境变量后：
  LLM_API_KEY=sk-... .venv/bin/python -m pytest tests/test_live_llm.py -m live -v"""
import os
import pytest
from app.services.llm.openai_compat import OpenAICompatLLM


@pytest.mark.live
@pytest.mark.asyncio
async def test_live_translate_and_extract():
    key = os.environ.get("LLM_API_KEY")
    if not key:
        pytest.skip("需设置 LLM_API_KEY 环境变量")
    base = os.environ.get("LLM_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    model = os.environ.get("LLM_MODEL", "qwen-plus")
    llm = OpenAICompatLLM(base, key, model)
    out = await llm.chat([{"role": "user", "content": "把'蓝色童鞋'翻成俄语，只回译文"}])
    assert out and isinstance(out, str)

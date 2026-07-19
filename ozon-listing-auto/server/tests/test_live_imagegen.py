"""真实生图冒烟(@live 默认跳过)。先在 /settings/imagegen 配好, 或设 IMG_BASE_URL/IMG_API_KEY/IMG_MODEL 后:
  IMG_API_KEY=... .venv/bin/python -m pytest tests/test_live_imagegen.py -m live -v"""
import os, pytest


@pytest.mark.live
@pytest.mark.asyncio
async def test_live_openai_gen(tmp_path):
    key = os.environ.get("IMG_API_KEY")
    if not key:
        pytest.skip("需设置 IMG_API_KEY")
    from app.services.imagegen.openai_compat import OpenAICompatImageProvider
    prov = OpenAICompatImageProvider(os.environ.get("IMG_BASE_URL", ""), key,
                                     os.environ.get("IMG_MODEL", "wanx-v1"), static_dir=str(tmp_path))
    res = await prov.process(image=b"", op="gen", params={"prompt": "电商风格 蓝色童鞋 白底主图"})
    assert res.url.startswith("/static/images/")

import base64, io, pytest, httpx
from PIL import Image
from app.services.imagegen.openai_compat import OpenAICompatImageProvider


def _png_bytes():
    b = io.BytesIO(); Image.new("RGB", (8, 8), (1, 2, 3)).save(b, format="PNG"); return b.getvalue()


@pytest.mark.asyncio
async def test_openai_gen_url_response(tmp_path):
    png = _png_bytes()
    def handler(req):
        if req.url.path.endswith("/images/generations"):
            return httpx.Response(200, json={"data": [{"url": "https://img.test/x.png"}]})
        return httpx.Response(200, content=png)   # 图片下载
    prov = OpenAICompatImageProvider("https://api.test/v1", "sk-x", "wanx", static_dir=str(tmp_path),
                                     transport=httpx.MockTransport(handler))
    res = await prov.process(image=b"", op="gen", params={"prompt": "蓝色童鞋 电商主图"})
    assert res.provider == "openai_compat" and res.url.startswith("/static/images/")
    import os
    assert os.path.exists(os.path.join(str(tmp_path), res.url.split("/")[-1]))


@pytest.mark.asyncio
async def test_openai_gen_b64_response(tmp_path):
    b64 = base64.b64encode(_png_bytes()).decode()
    def handler(req):
        return httpx.Response(200, json={"data": [{"b64_json": b64}]})
    prov = OpenAICompatImageProvider("https://api.test/v1", "sk-x", "wanx", static_dir=str(tmp_path),
                                     transport=httpx.MockTransport(handler))
    res = await prov.process(image=b"", op="gen", params={"prompt": "x"})
    assert res.url.startswith("/static/images/")


@pytest.mark.asyncio
async def test_openai_gen_error_raises(tmp_path):
    def handler(req): return httpx.Response(500)
    prov = OpenAICompatImageProvider("https://api.test/v1", "sk-x", "wanx", static_dir=str(tmp_path),
                                     transport=httpx.MockTransport(handler))
    with pytest.raises(Exception):
        await prov.process(image=b"", op="gen", params={"prompt": "x"})

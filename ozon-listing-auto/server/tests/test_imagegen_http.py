import base64, io, json, pytest, httpx
from PIL import Image
from app.services.imagegen.http import HttpImageProvider


def _png(): b = io.BytesIO(); Image.new("RGB", (8, 8), (9, 9, 9)).save(b, format="PNG"); return b.getvalue()


@pytest.mark.asyncio
async def test_http_gen_url_path(tmp_path):
    png = _png()
    def handler(req):
        if req.url.host == "gen.test":
            body = json.loads(req.content)
            assert body["prompt"] == "电商主图" and body["model"] == "m1"   # 模板替换生效
            return httpx.Response(200, json={"output": {"image_url": "https://cdn.test/y.png"}})
        return httpx.Response(200, content=png)
    prov = HttpImageProvider("https://gen.test/api", "k", "m1",
                             request_template='{"prompt":"{prompt}","model":"{model}"}',
                             response_path="output.image_url", static_dir=str(tmp_path),
                             transport=httpx.MockTransport(handler))
    res = await prov.process(image=b"", op="gen", params={"prompt": "电商主图"})
    assert res.provider == "http" and res.url.startswith("/static/images/")


@pytest.mark.asyncio
async def test_http_gen_b64_path(tmp_path):
    b64 = base64.b64encode(_png()).decode()
    def handler(req):
        return httpx.Response(200, json={"data": [{"b64": b64}]})
    prov = HttpImageProvider("https://gen.test/api", "k", "m1",
                             request_template='{"prompt":"{prompt}"}',
                             response_path="data.0.b64", static_dir=str(tmp_path),
                             transport=httpx.MockTransport(handler))
    res = await prov.process(image=b"", op="gen", params={"prompt": "x"})
    assert res.url.startswith("/static/images/")


@pytest.mark.asyncio
async def test_http_missing_path_raises(tmp_path):
    def handler(req): return httpx.Response(200, json={"nope": 1})
    prov = HttpImageProvider("https://gen.test/api", "", "m", '{"p":"{prompt}"}', "output.image_url",
                             static_dir=str(tmp_path), transport=httpx.MockTransport(handler))
    with pytest.raises(Exception):
        await prov.process(image=b"", op="gen", params={"prompt": "x"})

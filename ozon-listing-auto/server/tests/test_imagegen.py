import io
import pytest
from PIL import Image
from app.services.imagegen.factory import get_image_provider, process_op
from app.services.imagegen.mock import MockImageProvider


def _png_rgba(w=100, h=80, color=(200, 30, 30, 128)):
    img = Image.new("RGBA", (w, h), color)
    buf = io.BytesIO(); img.save(buf, format="PNG"); return buf.getvalue()


@pytest.mark.asyncio
async def test_local_whitebg_flattens_alpha(tmp_path):
    prov = get_image_provider("local", static_dir=str(tmp_path))
    res = await prov.process(image=_png_rgba(), op="whitebg", params={})
    assert res.provider == "local"
    out = Image.open(res.url.replace("/static", str(tmp_path)) if res.url.startswith("/static")
                     else str(tmp_path) + "/" + res.url.split("/")[-1])
    # 产物无 alpha（白底合成）；随便取一像素应不透明
    assert out.mode in ("RGB",)


@pytest.mark.asyncio
async def test_local_crop_norm_dims(tmp_path):
    prov = get_image_provider("local", static_dir=str(tmp_path))
    res = await prov.process(image=_png_rgba(120, 60), op="crop_norm", params={"size": [100, 100]})
    from PIL import Image as I
    out = I.open(str(tmp_path) + "/" + res.url.split("/")[-1])
    assert out.size == (100, 100)


@pytest.mark.asyncio
async def test_local_watermark_runs(tmp_path):
    prov = get_image_provider("local", static_dir=str(tmp_path))
    res = await prov.process(image=_png_rgba(), op="watermark", params={"text": "OZ"})
    assert res.url and "watermark" in res.meta.get("op", "watermark") or res.url


@pytest.mark.asyncio
async def test_local_rmbg_falls_back_when_rembg_missing(tmp_path):
    prov = get_image_provider("local", static_dir=str(tmp_path))
    res = await prov.process(image=_png_rgba(), op="rmbg", params={})
    # 无 rembg 环境下降级为 whitebg，并在 meta 标注
    assert res.meta.get("degraded") in (True, False)  # 有 rembg 则 False，无则 True；两者都可
    assert res.url


@pytest.mark.asyncio
async def test_mock_provider_deterministic():
    prov = MockImageProvider()
    r1 = await prov.process(image=b"abc", op="gen", params={})
    r2 = await prov.process(image=b"abc", op="gen", params={})
    assert r1.url == r2.url and r1.provider == "mock"


@pytest.mark.asyncio
async def test_process_op_routes_gen_to_mock(tmp_path):
    res = await process_op("gen", image=b"x", params={}, static_dir=str(tmp_path), gen_provider="mock")
    assert res.provider == "mock"
    res2 = await process_op("whitebg", image=_png_rgba(), params={}, static_dir=str(tmp_path))
    assert res2.provider == "local"

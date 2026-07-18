"""真实 CLIP 向量冒烟(@live 默认跳过)。需先装 [ml]（torch/cn_clip，数 GB）。跑法：
  .venv/bin/pip install -e '.[ml]'   # 用户 [ml] 环境
  .venv/bin/python -m pytest tests/test_live_clip.py -m live -v"""
import math
import pytest

_IMG = "https://ir.ozone.ru/s3/multimedia-1-3/7473007263.jpg"   # 一张公开 Ozon 商品图


@pytest.mark.live
@pytest.mark.asyncio
async def test_live_clip_embed_512_normalized():
    try:
        from app.services.embedding.clip import ChineseClipEmbedder
        emb = ChineseClipEmbedder()
        vec = await emb.embed_image(_IMG)
    except ImportError:
        pytest.skip("需安装 [ml]（torch/cn_clip）")
    assert isinstance(vec, list) and len(vec) == 512
    assert all(isinstance(x, float) for x in vec)
    norm = math.sqrt(sum(x * x for x in vec))
    assert 0.9 < norm < 1.1        # L2 归一化, 模长≈1

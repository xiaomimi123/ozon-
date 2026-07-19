"""真实 1688 图搜冒烟(@live 默认跳过)。先在 /settings/sources 配好端点/sign, 货源账号池填 cookie；或设 env:
  ALI1688_URL=.. ALI1688_COOKIE=.. ALI1688_IMG=<商品图URL> \
    .venv/bin/python -m pytest tests/test_live_1688.py -m live -v"""
import os, json, pytest
from app.services.sources.ali1688 import Ali1688Provider


@pytest.mark.live
@pytest.mark.asyncio
async def test_live_1688_image_search():
    url, cookie, img = os.environ.get("ALI1688_URL"), os.environ.get("ALI1688_COOKIE"), os.environ.get("ALI1688_IMG")
    if not (url and cookie and img):
        pytest.skip("需设置 ALI1688_URL/ALI1688_COOKIE/ALI1688_IMG")
    conf = {"ali1688_image_search_url": url, "ali1688_method": os.environ.get("ALI1688_METHOD", "GET"),
            "ali1688_extra_params": json.loads(os.environ.get("ALI1688_PARAMS", "{}")),
            "ali1688_extra_headers": json.loads(os.environ.get("ALI1688_HEADERS", "{}")),
            "ali1688_offer_list_path": os.environ.get("ALI1688_PATH", "data.offerList")}
    out = await Ali1688Provider(conf).image_search(img, session={"cookie": cookie})
    assert isinstance(out, list)   # 真实响应结构对齐后应有候选

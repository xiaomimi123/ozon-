import pytest
from app.services.sources.pinduoduo import PinduoduoProvider, parse_pdd_items

@pytest.mark.asyncio
async def test_pdd_image_search_not_implemented_yet():
    p = PinduoduoProvider()
    with pytest.raises(NotImplementedError):
        await p.image_search("https://img/x.jpg", session=None)

def test_parse_pdd_items():
    payload = {"items": [{"goods_id": "G1", "goods_name": "耳机", "min_group_price": 1390,
                          "thumb_url": "https://pdd/g1.jpg", "mall_name": "店A"}]}
    dtos = parse_pdd_items(payload)
    assert len(dtos) == 1
    assert dtos[0].platform == "pinduoduo" and dtos[0].offer_id == "G1"
    assert dtos[0].price == 13.9            # 分→元
    assert dtos[0].supplier_name == "店A"

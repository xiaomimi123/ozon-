from app.services.sources.parser_excel import parse_1688_excel, DEFAULT_EXCEL_COLS

HEADER = ["标题", "产品ID", "产品链接", "图片链接", "价格", "是否包邮", "月销件数", "店铺名称"]
def _rows():
    return [
        HEADER,
        ["连衣裙", 891053144236, "https://detail.1688.com/offer/891053144236.html", "http://i/a.jpg", 0.56, "不包邮", 12, "义乌某厂"],
        ["缺ID但有链接", None, "https://detail.1688.com/offer/222.html", "http://i/b.jpg", "3.6", "包邮", "-", "广州店"],
        ["彻底缺ID", None, None, None, None, None, None, None],  # 跳过
    ]

def test_maps_real_headers():
    out = parse_1688_excel(_rows())
    assert len(out) == 2
    a = out[0]
    assert a["offer_id"] == "891053144236" and a["title"] == "连衣裙" and a["price"] == 0.56
    assert a["image_url"] == "http://i/a.jpg" and a["shop_name"] == "义乌某厂" and a["sales"] == 12
    assert a["detail_url"].endswith("891053144236.html")

def test_offer_id_from_link_when_missing():
    out = parse_1688_excel(_rows())
    assert out[1]["offer_id"] == "222" and out[1]["price"] == 3.6 and out[1]["sales"] is None

def test_custom_cols():
    rows = [["名称", "货号"], ["T", "9"]]
    out = parse_1688_excel(rows, {**DEFAULT_EXCEL_COLS, "title": "名称", "offer_id": "货号"})
    assert out[0]["offer_id"] == "9" and out[0]["title"] == "T"

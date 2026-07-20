from pydantic import BaseModel

class SourcesIn(BaseModel):
    ali1688_image_search_url: str = ""
    ali1688_keyword_search_url: str = ""
    ali1688_method: str = "GET"
    ali1688_extra_params: str = ""
    ali1688_extra_headers: str = ""
    ali1688_offer_list_path: str = "data.offerList"
    import_token: str = ""              # 脱敏；GET 返回 "***"，PUT 留空不覆盖
    import_1688_list_path: str = ""
    import_1688_offer_id_path: str = ""
    import_1688_title_path: str = ""
    import_1688_price_path: str = ""
    import_1688_image_path: str = ""
    import_1688_shop_path: str = ""
    import_1688_detail_url_path: str = ""
    import_1688_sales_path: str = ""

class SourcesOut(SourcesIn):
    pass

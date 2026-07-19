from pydantic import BaseModel

class SourcesIn(BaseModel):
    ali1688_image_search_url: str = ""
    ali1688_keyword_search_url: str = ""
    ali1688_method: str = "GET"
    ali1688_extra_params: str = ""
    ali1688_extra_headers: str = ""
    ali1688_offer_list_path: str = "data.offerList"

class SourcesOut(SourcesIn):
    pass

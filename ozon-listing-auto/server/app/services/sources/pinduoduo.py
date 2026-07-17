"""PinduoduoProvider：selenium/playwright + 代理截获移动端 API(一期先关键词, 不逆向 anti_content)。"""
from app.services.sources.base import SupplyCandidateDTO

def parse_pdd_items(payload: dict) -> list[SupplyCandidateDTO]:
    """解析截获的拼多多商品 JSON（价格为分, /100 得元）。"""
    out: list[SupplyCandidateDTO] = []
    for it in payload.get("items", []) or []:
        gid = it.get("goods_id")
        if gid is None:
            continue
        price = it.get("min_group_price")
        out.append(SupplyCandidateDTO(
            platform="pinduoduo", offer_id=str(gid), title=it.get("goods_name"),
            price=(price / 100.0) if isinstance(price, (int, float)) else None, currency="CNY",
            image_url=it.get("thumb_url"), detail_url=it.get("detail_url"),
            supplier_name=it.get("mall_name"), supplier_info={}, raw=it,
        ))
    return out

class PinduoduoProvider:
    platform = "pinduoduo"
    async def image_search(self, image_url: str, *, session) -> list[SupplyCandidateDTO]:
        raise NotImplementedError("拼多多图搜一期不做（签名复杂），后续增强；一期用 keyword_search")
    async def keyword_search(self, kw: str, *, session) -> list[SupplyCandidateDTO]:
        # 真实实现: selenium/playwright 打开移动端搜索 + 代理截获返回 JSON → parse_pdd_items
        # 一期真实联调走 live 测试; 此处返回空占位, 避免无 selenium 环境报错
        raise NotImplementedError("拼多多关键词搜索需 selenium+代理环境, 走 live 联调")
    async def fetch_detail(self, offer_id: str, *, session) -> SupplyCandidateDTO:
        return SupplyCandidateDTO(platform="pinduoduo", offer_id=offer_id)

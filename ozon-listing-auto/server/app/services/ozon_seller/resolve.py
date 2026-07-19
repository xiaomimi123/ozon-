"""按 system 配置解析 OzonSellerProvider：provider(mock|real) + real 时 dry-run 开关。"""
from app.core.config import settings
from app.services.settings_store import get_category
from app.services.ozon_seller.factory import get_ozon_seller
from app.services.ozon_seller.base import OzonSellerProvider


async def resolve_seller(session) -> OzonSellerProvider:
    conf = await get_category(session, "system")
    name = conf.get("ozon_seller_provider") or settings.ozon_seller_provider
    if name == "real":
        from app.services.ozon_seller.real import RealOzonSeller
        dry_run = conf.get("ozon_publish_dry_run", "true") != "false"
        return RealOzonSeller(dry_run=dry_run)
    return get_ozon_seller(name)

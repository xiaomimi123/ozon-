import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
from app.workers.publisher import apply_auto_confirm, run_publish_core, confirm_draft
from app.services.ozon_seller.mock import MockOzonSeller
from app.core.crypto import encrypt
from app.models import CollectTask, OzonProduct, SupplyCandidate, ListingDraft, Shop

async def _seed(sm, review_config, draft_status="draft", score=90.0):
    async with sm() as s:
        t = CollectTask(name="t", entry_type="keyword", entry_value="x", provider="mock",
                        source_platforms=["ali1688"], review_config=review_config)
        s.add(t); await s.flush()
        p = OzonProduct(task_id=t.id, sku="OZSKU1", title="phone", barcode="460")
        s.add(p); await s.flush()
        c = SupplyCandidate(task_id=t.id, ozon_product_id=p.id, platform="ali1688", offer_id="A1",
                            status="adopted", score_total=score)
        s.add(c); await s.flush()
        shop = Shop(name="店", client_id="C", api_key_encrypted=encrypt("SECRET"))
        s.add(shop); await s.flush()
        d = ListingDraft(task_id=t.id, ozon_product_id=p.id, candidate_id=c.id, shop_id=shop.id,
                         mode="follow", target_ozon_sku="OZSKU1", barcode="460", price=1290.0, stock_qty=5,
                         status=draft_status)
        s.add(d); await s.commit()
        return t.id, d.id

@pytest.mark.asyncio
async def test_auto_confirm_when_listing_review_off(engine):
    sm = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    tid, did = await _seed(sm, {"listing_review_required": False, "listing_score_min": 85})
    async with sm() as s:
        r = await apply_auto_confirm(s, tid); await s.commit()
    assert r["confirmed"] == 1
    async with sm() as s:
        d = (await s.execute(select(ListingDraft).where(ListingDraft.id == did))).scalar_one()
    assert d.status == "confirmed"

@pytest.mark.asyncio
async def test_run_publish_mock(engine):
    sm = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    tid, did = await _seed(sm, {"listing_review_required": True}, draft_status="confirmed")
    result = await run_publish_core(sm, tid, seller=MockOzonSeller())
    async with sm() as s:
        d = (await s.execute(select(ListingDraft).where(ListingDraft.id == did))).scalar_one()
    assert result["published"] == 1
    assert d.status == "published"
    assert d.ozon_result and d.ozon_result["ozon_product_id"] == "OZ-A1"

@pytest.mark.asyncio
async def test_publish_bad_credential_isolated(engine):
    # 一条草稿的 api_key 密文损坏 → 只该条 failed, run 不崩、返回干净结果
    sm = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    tid, did = await _seed(sm, {"listing_review_required": True}, draft_status="confirmed")
    async with sm() as s:
        shop = (await s.execute(select(Shop))).scalars().first()
        shop.api_key_encrypted = b"not-a-valid-fernet-token"   # 损坏密文 → decrypt 抛错
        await s.commit()
    result = await run_publish_core(sm, tid, seller=MockOzonSeller())   # 必须不抛异常
    async with sm() as s:
        d = (await s.execute(select(ListingDraft).where(ListingDraft.id == did))).scalar_one()
    assert result["failed"] == 1 and result["published"] == 0
    assert d.status == "failed" and d.error

def test_ozon_seller_config_default_mock():
    from app.core.config import settings
    from app.services.ozon_seller.factory import get_ozon_seller
    # 默认配置解析为 mock; 工厂能按配置名构造(real 分支惰性可用)
    assert settings.ozon_seller_provider == "mock"
    assert get_ozon_seller(settings.ozon_seller_provider).name == "mock"
    assert get_ozon_seller("real").name == "real"

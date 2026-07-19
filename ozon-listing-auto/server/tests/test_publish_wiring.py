"""Task3：同步便捷接口(/listing/publish?sync=true, /publish/tick?sync=true)与 arq(run_publish/run_publish_tick)
统一经 resolve_seller(session) 按 system 配置解析 provider——provider=mock 时行为不变(回归)；
provider=real+dry_run 时不真发网络，草稿 ozon_result.raw 携带 dry-run 构造的真实请求体
(见 resolve_seller/RealOzonSeller)。注：run_publish_core/tick_publish(无等审核门时) 只看 res.ok 决定
是否置为 published, 不看 res.status, 故 dry-run(ok=True) 下草稿仍会推进为 published/(等审核门时)pending_review，
但 ozon_product_id 固定为 "DRYRUN" 且带 dry_run 请求体, 与真实 mock 上品(OZ-<offer_id>)可区分。"""
from datetime import datetime, timezone, timedelta
import pytest
from sqlalchemy import select
from app.core.security import hash_password
from app.core.crypto import encrypt
from app.models import User, CollectTask, OzonProduct, SupplyCandidate, Shop, ListingDraft, PublishPace


async def _seed_follow_draft(client, db_session, *, username: str, sku: str = "298789742"):
    """建 follow 模式候选 + 店铺 + 登录, 走 /listing/build + /confirm 到 confirmed 状态, 返回 (task_id, headers)。
    sku 用纯数字字符串(如 test_ozon_seller_real.py 所用)：create_follow_offer 内部 int(target_sku),
    _seed_login()(test_listing_api.py) 用的 "OZSKU1" 这类非数字 sku 在 real 模式下会在 dry-run 短路前就因
    int() 转换失败, 故本 helper 专用数字 sku, 不复用 _seed_login。"""
    db_session.add(User(username=username, password_hash=hash_password("p"), role="admin"))
    t = CollectTask(name="t", entry_type="keyword", entry_value="x", provider="mock",
                    source_platforms=["ali1688"], review_config={"listing_review_required": True})
    db_session.add(t); await db_session.flush()
    p = OzonProduct(task_id=t.id, sku=sku, title="phone", barcode="460")
    db_session.add(p); await db_session.flush()
    db_session.add(SupplyCandidate(task_id=t.id, ozon_product_id=p.id, platform="ali1688", offer_id="A1",
                                   price=15.0, status="adopted", score_total=90.0))
    shop = Shop(name="店", client_id="C", api_key_encrypted=encrypt("K"))
    db_session.add(shop); await db_session.commit()
    tok = (await client.post("/auth/login", data={"username": username, "password": "p"})).json()["access_token"]
    headers = {"Authorization": f"Bearer {tok}"}
    b = await client.post(f"/listing/build?task_id={t.id}&shop_id={shop.id}", headers=headers)
    assert b.status_code == 200 and b.json()["built"] == 1
    drafts = (await client.get(f"/listing/drafts?task_id={t.id}", headers=headers)).json()
    did = drafts[0]["id"]
    c = await client.post(f"/listing/{did}/confirm", headers=headers)
    assert c.status_code == 200 and c.json()["status"] == "confirmed"
    return t.id, headers


@pytest.mark.asyncio
async def test_sync_listing_publish_mock_default_unchanged(client, db_session):
    """provider 未配置(默认 mock)时, 同步 /listing/publish 行为不变(回归)。"""
    tid, h = await _seed_follow_draft(client, db_session, username="u_mock")
    r = await client.post(f"/listing/publish?task_id={tid}&sync=true", headers=h)
    assert r.status_code == 200 and r.json() == {"published": 1, "failed": 0}
    drafts = (await client.get(f"/listing/drafts?task_id={tid}", headers=h)).json()
    assert drafts[0]["status"] == "published"
    assert drafts[0]["ozon_result"]["ozon_product_id"] == "OZ-A1"


@pytest.mark.asyncio
async def test_sync_listing_publish_real_dry_run_builds_body_without_network(client, db_session):
    """provider=real + dry_run=true 时: 同步 publish 不真发网络(无 transport 配置也不会挂起/报错——
    dry-run 在 RealOzonSeller 内部短路), ozon_result.raw.dry_run 携带真实请求体(sku/offer_id/price),
    且 ozon_product_id 为 "DRYRUN"(区别于 mock 的 "OZ-A1"), 证明确实经 resolve_seller 解到了 real+dry_run。"""
    tid, h = await _seed_follow_draft(client, db_session, username="u_real")
    put = await client.put("/settings/system",
                           json={"ozon_seller_provider": "real", "ozon_publish_dry_run": "true"}, headers=h)
    assert put.status_code == 200

    r = await client.post(f"/listing/publish?task_id={tid}&sync=true", headers=h)
    assert r.status_code == 200 and r.json() == {"published": 1, "failed": 0}

    drafts = (await client.get(f"/listing/drafts?task_id={tid}", headers=h)).json()
    d = drafts[0]
    assert d["status"] == "published"
    result = d["ozon_result"] or {}
    assert result.get("ozon_product_id") == "DRYRUN"
    dry_body = (result.get("raw") or {}).get("dry_run")
    assert dry_body is not None, f"ozon_result 未携带 dry_run 请求体: {result}"
    item = dry_body["items"][0]
    assert item["sku"] == 298789742
    assert item["offer_id"] == "A1"
    assert isinstance(item["price"], str) and item["price"]


@pytest.mark.asyncio
async def test_sync_publish_tick_real_dry_run_wired(client, db_session):
    """/publish/tick?sync=true 同样经 resolve_seller: provider=real+dry_run 下到期 scheduled 草稿
    被 dry-run 挂靠(ozon_product_id="DRYRUN"+带 dry_run 请求体), 而非误用写死的 mock provider(会是 "OZ-A1")。"""
    tid, h = await _seed_follow_draft(client, db_session, username="u_tick")
    put = await client.put("/settings/system",
                           json={"ozon_seller_provider": "real", "ozon_publish_dry_run": "true"}, headers=h)
    assert put.status_code == 200

    drafts = (await client.get(f"/listing/drafts?task_id={tid}", headers=h)).json()
    did = drafts[0]["id"]
    db_session.add(PublishPace(task_id=tid, wait_ozon_approval=False, min_interval_sec=1, max_interval_sec=1))
    d = (await db_session.execute(select(ListingDraft).where(ListingDraft.id == did))).scalar_one()
    d.status = "scheduled"
    d.scheduled_at = datetime.now(timezone.utc) - timedelta(seconds=10)
    await db_session.commit()

    r = await client.post(f"/publish/tick?task_id={tid}&sync=true", headers=h)
    assert r.status_code == 200 and r.json()["published"] == 1

    drafts2 = (await client.get(f"/listing/drafts?task_id={tid}", headers=h)).json()
    d2 = drafts2[0]
    assert d2["status"] == "published"
    result = d2["ozon_result"] or {}
    assert result.get("ozon_product_id") == "DRYRUN"
    assert (result.get("raw") or {}).get("dry_run") is not None

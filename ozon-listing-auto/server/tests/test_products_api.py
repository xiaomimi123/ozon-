"""商品列表 API 测试：登录后按 sales_min 筛选，验证分页 total 与命中项。"""
import pytest
from sqlalchemy import select
from app.core.security import hash_password
from app.models import User, CollectTask, OzonProduct

@pytest.mark.asyncio
async def test_products_filtered(client, db_session):
    db_session.add(User(username="op", password_hash=hash_password("p"), role="operator"))
    db_session.add(CollectTask(id=1, name="t", entry_type="keyword", entry_value="x", provider="mock", source_platforms=[]))
    db_session.add_all([
        OzonProduct(task_id=1, sku="A", title="phone", sales_monthly=100, rating=4.9),
        OzonProduct(task_id=1, sku="B", title="case", sales_monthly=5, rating=4.0),
    ])
    await db_session.commit()
    tok = (await client.post("/auth/login", data={"username":"op","password":"p"})).json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    r = await client.get("/products?task_id=1&sales_min=50", headers=h)
    assert r.status_code == 200
    assert r.json()["total"] == 1 and r.json()["items"][0]["sku"] == "A"

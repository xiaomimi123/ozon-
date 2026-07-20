"""合成 xlsx 上传, 入库+去重; 非xlsx 400; 非admin 403"""
import io, pytest, openpyxl
from sqlalchemy import select, func
from app.core.security import hash_password
from app.models import User, ImportedProduct, ImportCapture

def _xlsx_bytes():
    wb = openpyxl.Workbook(); ws = wb.active
    ws.append(["标题", "产品ID", "产品链接", "图片链接", "价格", "月销件数", "店铺名称"])
    ws.append(["裙子", 891053144236, "https://detail.1688.com/offer/891053144236.html", "http://i/a.jpg", 0.56, 12, "义乌厂"])
    ws.append(["鞋", 777, "https://detail.1688.com/offer/777.html", "http://i/b.jpg", 9.9, 5, "温州店"])
    b = io.BytesIO(); wb.save(b); return b.getvalue()

async def _admin_headers(client, db_session):
    db_session.add(User(username="adm", password_hash=hash_password("p"), role="admin")); await db_session.commit()
    tok = (await client.post("/auth/login", data={"username": "adm", "password": "p"})).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}

async def _operator_headers(client, db_session):
    db_session.add(User(username="op", password_hash=hash_password("p"), role="operator")); await db_session.commit()
    tok = (await client.post("/auth/login", data={"username": "op", "password": "p"})).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}

@pytest.mark.asyncio
async def test_upload_excel(client, db_session):
    h = await _admin_headers(client, db_session)
    files = {"file": ("ALL-ExportProduct.xlsx", _xlsx_bytes(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    r = await client.post("/import/excel", files=files, headers=h)
    assert r.status_code == 200 and r.json()["parsed"] == 2
    # 再传一次 → 去重
    await client.post("/import/excel", files={"file": ("x.xlsx", _xlsx_bytes(), "application/octet-stream")}, headers=h)
    n = (await db_session.execute(select(func.count()).select_from(ImportedProduct))).scalar_one()
    assert n == 2
    caps = (await db_session.execute(select(func.count()).select_from(ImportCapture))).scalar_one()
    assert caps == 2

@pytest.mark.asyncio
async def test_reject_non_xlsx(client, db_session):
    h = await _admin_headers(client, db_session)
    r = await client.post("/import/excel", files={"file": ("a.txt", b"x", "text/plain")}, headers=h)
    assert r.status_code == 400

@pytest.mark.asyncio
async def test_operator_forbidden(client, db_session):
    h = await _operator_headers(client, db_session)
    r = await client.post("/import/excel", files={"file": ("a.xlsx", _xlsx_bytes(), "application/octet-stream")}, headers=h)
    assert r.status_code == 403

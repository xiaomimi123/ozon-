"""采集导入 API：扩展回传搜索响应 → 存原始 + 路径可配解析入库。ingest 用 X-Import-Token 鉴权。"""
import io
from fastapi import APIRouter, Depends, Header, HTTPException, UploadFile, File, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.db import get_session
from app.api.deps import require_role
from app.models import User, ImportCapture, ImportedProduct
from app.services.sources.conf import get_source_conf
from app.services.sources.parser_import import parse_1688_search, DEFAULT_IMPORT_PATHS
from app.services.sources.parser_excel import parse_1688_excel, DEFAULT_EXCEL_COLS

router = APIRouter(prefix="/import", tags=["import"])

def _paths_from_conf(conf: dict) -> dict:
    paths = dict(DEFAULT_IMPORT_PATHS)
    for k in DEFAULT_IMPORT_PATHS:
        v = conf.get(f"import_1688_{k}_path") if k != "list" else conf.get("import_1688_list_path")
        if v:
            paths[k] = v
    return paths

@router.post("/offers")
async def ingest(payload: dict, keyword: str | None = None,
                 x_import_token: str | None = Header(default=None),
                 s: AsyncSession = Depends(get_session)):
    conf = await get_source_conf(s)
    token = conf.get("import_token") or ""
    if not token or x_import_token != token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "无效导入令牌")
    rows = parse_1688_search(payload, _paths_from_conf(conf))
    cap = ImportCapture(platform="ali1688", keyword=keyword, raw=payload, item_count=len(rows))
    s.add(cap); await s.flush()
    parsed = 0
    for r in rows:
        exists = (await s.execute(select(ImportedProduct).where(
            ImportedProduct.platform == "ali1688", ImportedProduct.offer_id == r["offer_id"]))).scalar_one_or_none()
        if exists:
            continue
        s.add(ImportedProduct(platform="ali1688", offer_id=r["offer_id"], title=r["title"], price=r["price"],
                              image_url=r["image_url"], shop_name=r["shop_name"], detail_url=r["detail_url"],
                              sales=r["sales"], raw=r["raw"], capture_id=cap.id))
        parsed += 1
    await s.commit()
    return {"capture_id": cap.id, "captured": len(rows), "parsed": parsed}

@router.post("/excel")
async def ingest_excel(file: UploadFile = File(...), s: AsyncSession = Depends(get_session), _: User = Depends(require_role("admin"))):
    if not (file.filename or "").lower().endswith(".xlsx"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "仅支持 .xlsx 文件")
    data = await file.read()
    try:
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        ws = wb.active
        rows = [list(r) for r in ws.iter_rows(values_only=True)]
        wb.close()
    except Exception:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "无法解析 Excel 文件")
    parsed_rows = parse_1688_excel(rows, DEFAULT_EXCEL_COLS)
    headers = [str(h) for h in (rows[0] if rows else []) if h is not None]
    cap = ImportCapture(platform="ali1688", keyword=file.filename,
                        raw={"headers": headers, "row_count": max(0, len(rows) - 1)}, item_count=len(parsed_rows))
    s.add(cap); await s.flush()
    parsed = 0
    for r in parsed_rows:
        exists = (await s.execute(select(ImportedProduct).where(
            ImportedProduct.platform == "ali1688", ImportedProduct.offer_id == r["offer_id"]))).scalar_one_or_none()
        if exists:
            continue
        s.add(ImportedProduct(platform="ali1688", offer_id=r["offer_id"], title=r["title"], price=r["price"],
                              image_url=r["image_url"], shop_name=r["shop_name"], detail_url=r["detail_url"],
                              sales=r["sales"], raw=r["raw"], capture_id=cap.id))
        parsed += 1
    await s.commit()
    return {"capture_id": cap.id, "captured": len(parsed_rows), "parsed": parsed, "skipped": len(parsed_rows) - parsed}

@router.get("/offers")
async def list_offers(platform: str | None = None, limit: int = 200,
                      s: AsyncSession = Depends(get_session), _: User = Depends(require_role("operator"))):
    q = select(ImportedProduct).order_by(ImportedProduct.id.desc()).limit(limit)
    if platform:
        q = q.where(ImportedProduct.platform == platform)
    rows = (await s.execute(q)).scalars().all()
    return [{"id": r.id, "platform": r.platform, "offer_id": r.offer_id, "title": r.title,
             "price": float(r.price) if r.price is not None else None, "image_url": r.image_url,
             "shop_name": r.shop_name, "detail_url": r.detail_url, "sales": r.sales,
             "created_at": r.created_at} for r in rows]

@router.get("/captures")
async def list_captures(limit: int = 50, s: AsyncSession = Depends(get_session), _: User = Depends(require_role("admin"))):
    rows = (await s.execute(select(ImportCapture).order_by(ImportCapture.id.desc()).limit(limit))).scalars().all()
    return [{"id": r.id, "platform": r.platform, "keyword": r.keyword, "item_count": r.item_count,
             "created_at": r.created_at} for r in rows]

@router.get("/captures/{cap_id}")
async def get_capture(cap_id: int, s: AsyncSession = Depends(get_session), _: User = Depends(require_role("admin"))):
    r = (await s.execute(select(ImportCapture).where(ImportCapture.id == cap_id))).scalar_one_or_none()
    if not r:
        raise HTTPException(404, "记录不存在")
    return {"id": r.id, "platform": r.platform, "keyword": r.keyword, "item_count": r.item_count, "raw": r.raw}

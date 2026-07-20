"""1688 采购助手导出 Excel → 导入商品 dict（表头名映射, 容错）。
默认列名按真实导出文件表头。cols 可覆盖(便于测试/未来插件改版)。"""
import re
from datetime import datetime, date

DEFAULT_EXCEL_COLS = {
    "title": "标题", "offer_id": "产品ID", "detail_url": "产品链接",
    "image_url": "图片链接", "price": "价格", "shop_name": "店铺名称", "sales": "月销件数",
}
_OFFER_RE = re.compile(r"offer/(\d+)")

def _price(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    m = re.search(r"[\d.]+", str(v))
    return float(m.group()) if m else None

def _int(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return int(v)
    m = re.search(r"\d+", str(v))
    return int(m.group()) if m else None

def _safe(v):
    if isinstance(v, (str, int, float, bool)) or v is None:
        return v
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    return str(v)

def _str(v):
    return None if v is None else str(v)

def parse_1688_excel(rows, cols=None):
    c = {**DEFAULT_EXCEL_COLS, **(cols or {})}
    if not rows:
        return []
    header = rows[0]
    idx = {str(h).strip(): i for i, h in enumerate(header) if h is not None}
    def cell(row, field):
        i = idx.get(c.get(field))
        return row[i] if (i is not None and i < len(row)) else None
    out = []
    for row in rows[1:]:
        if not any(v is not None for v in row):
            continue
        raw_oid = cell(row, "offer_id")
        detail = cell(row, "detail_url")
        oid = str(raw_oid).strip() if raw_oid not in (None, "") else None
        if oid and oid.endswith(".0"):  # openpyxl 可能把大整数读成 float
            oid = oid[:-2]
        if not oid and detail:
            m = _OFFER_RE.search(str(detail))
            oid = m.group(1) if m else None
        if not oid:
            continue
        raw = {h: _safe(row[i]) for h, i in idx.items() if i < len(row)}
        out.append({
            "offer_id": oid, "title": _str(cell(row, "title")), "price": _price(cell(row, "price")),
            "image_url": _str(cell(row, "image_url")), "shop_name": _str(cell(row, "shop_name")),
            "detail_url": _str(detail), "sales": _int(cell(row, "sales")), "raw": raw,
        })
    return out

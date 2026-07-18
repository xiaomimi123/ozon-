"""爬虫配置 API(admin)：cookie/proxy Fernet 加密脱敏、留空不覆盖；timeout/间隔/重试明文。"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.db import get_session
from app.api.deps import require_role
from app.models import User
from app.schemas.crawler import CrawlerIn, CrawlerOut
from app.services import settings_store as store

router = APIRouter(prefix="/settings/crawler", tags=["settings"])
_CAT = "crawler"


@router.get("", response_model=CrawlerOut)
async def read(s: AsyncSession = Depends(get_session), _: User = Depends(require_role("admin"))):
    m = await store.get_category_masked(s, _CAT)
    return CrawlerOut(cookie=m.get("cookie"), proxy=m.get("proxy"),
                      timeout=float(m.get("timeout") or 20.0), min_delay=float(m.get("min_delay") or 0.3),
                      max_delay=float(m.get("max_delay") or 1.0), max_retries=int(float(m.get("max_retries") or 4)))


@router.put("", response_model=CrawlerOut)
async def write(body: CrawlerIn, s: AsyncSession = Depends(get_session), u: User = Depends(require_role("admin"))):
    if body.cookie:
        await store.set_value(s, _CAT, "cookie", body.cookie, is_secret=True, updated_by=u.id)
    if body.proxy:
        await store.set_value(s, _CAT, "proxy", body.proxy, is_secret=True, updated_by=u.id)
    await store.set_value(s, _CAT, "timeout", str(body.timeout), is_secret=False, updated_by=u.id)
    await store.set_value(s, _CAT, "min_delay", str(body.min_delay), is_secret=False, updated_by=u.id)
    await store.set_value(s, _CAT, "max_delay", str(body.max_delay), is_secret=False, updated_by=u.id)
    await store.set_value(s, _CAT, "max_retries", str(body.max_retries), is_secret=False, updated_by=u.id)
    await s.commit()
    return CrawlerOut(cookie="***" if body.cookie else None, proxy="***" if body.proxy else None,
                      timeout=body.timeout, min_delay=body.min_delay, max_delay=body.max_delay,
                      max_retries=body.max_retries)

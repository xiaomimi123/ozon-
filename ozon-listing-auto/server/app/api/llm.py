"""LLM provider 配置 API(admin)：provider/base_url/api_key/model，Fernet 加密脱敏、留空不覆盖。"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.db import get_session
from app.api.deps import require_role
from app.models import User
from app.schemas.llm import LlmIn, LlmOut
from app.services import settings_store as store

router = APIRouter(prefix="/settings/llm", tags=["settings"])
_CAT = "llm"


@router.get("", response_model=LlmOut)
async def read(s: AsyncSession = Depends(get_session), _: User = Depends(require_role("admin"))):
    m = await store.get_category_masked(s, _CAT)
    return LlmOut(llm_provider=m.get("llm_provider", "mock"), llm_base_url=m.get("llm_base_url", ""),
                  llm_api_key=m.get("llm_api_key"), llm_model=m.get("llm_model", ""))


@router.put("", response_model=LlmOut)
async def write(body: LlmIn, s: AsyncSession = Depends(get_session), u: User = Depends(require_role("admin"))):
    await store.set_value(s, _CAT, "llm_provider", body.llm_provider, is_secret=False, updated_by=u.id)
    await store.set_value(s, _CAT, "llm_base_url", body.llm_base_url, is_secret=False, updated_by=u.id)
    if body.llm_api_key:
        await store.set_value(s, _CAT, "llm_api_key", body.llm_api_key, is_secret=True, updated_by=u.id)
    await store.set_value(s, _CAT, "llm_model", body.llm_model, is_secret=False, updated_by=u.id)
    await s.commit()
    return LlmOut(llm_provider=body.llm_provider, llm_base_url=body.llm_base_url,
                  llm_api_key="***" if body.llm_api_key else None, llm_model=body.llm_model)

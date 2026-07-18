"""类目 API(§5.7)：类目树 / LLM 建议(记忆复用) / 确认写记忆表。"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.db import get_session
from app.api.deps import require_role
from app.models import SupplyCandidate, User
from app.schemas.category import CategoryNode, SuggestOut, ConfirmCategoryIn
from app.services.category_tree import get_category_tree
from app.services.category_map import suggest_category, confirm_category
from app.services.llm.factory import get_llm

router = APIRouter(tags=["category"])


@router.get("/categories", response_model=list[CategoryNode])
async def categories(parent_id: int | None = None, _: User = Depends(require_role("operator"))):
    return await get_category_tree("mock").list_children(parent_id=parent_id)


@router.post("/category/suggest", response_model=SuggestOut)
async def suggest(candidate_id: int, s: AsyncSession = Depends(get_session),
                  _: User = Depends(require_role("operator"))):
    c = (await s.execute(select(SupplyCandidate).where(SupplyCandidate.id == candidate_id))).scalar_one_or_none()
    if not c:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "候选不存在")
    res = await suggest_category(s, c, llm=get_llm("mock"), tree=get_category_tree("mock"))
    await s.commit()   # memory 命中会 +usage_count
    return SuggestOut(**res)


@router.post("/listing/{draft_id}/confirm-category")
async def confirm_cat(draft_id: int, body: ConfirmCategoryIn, s: AsyncSession = Depends(get_session),
                      _: User = Depends(require_role("reviewer"))):
    r = await confirm_category(s, draft_id, category_id=body.category_id,
                               attributes=body.attributes, path=body.path)
    await s.commit()
    return r

"""账号池 CRUD（admin）：cookie/会话 Fernet 加密存, 响应脱敏。"""
import json
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.db import get_session
from app.core.crypto import encrypt
from app.api.deps import require_role
from app.models import SourceAccount, User
from app.schemas.account import AccountCreate, AccountUpdate, AccountOut

router = APIRouter(prefix="/accounts", tags=["accounts"])

@router.post("", response_model=AccountOut, status_code=201)
async def create_account(body: AccountCreate, s: AsyncSession = Depends(get_session), _: User = Depends(require_role("admin"))):
    if body.platform not in {"ali1688", "pinduoduo"}:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "非法平台")
    acc = SourceAccount(platform=body.platform, label=body.label,
                        credentials_encrypted=encrypt(json.dumps(body.credentials)),
                        daily_limit=body.daily_limit, min_interval_sec=body.min_interval_sec)
    s.add(acc); await s.commit(); await s.refresh(acc)
    return acc

@router.get("", response_model=list[AccountOut])
async def list_accounts(platform: str | None = None, s: AsyncSession = Depends(get_session), _: User = Depends(require_role("admin"))):
    q = select(SourceAccount)
    if platform:
        q = q.where(SourceAccount.platform == platform)
    return list((await s.execute(q.order_by(SourceAccount.id.desc()))).scalars().all())

@router.put("/{account_id}", response_model=AccountOut)
async def update_account(account_id: int, body: AccountUpdate, s: AsyncSession = Depends(get_session), _: User = Depends(require_role("admin"))):
    acc = (await s.execute(select(SourceAccount).where(SourceAccount.id == account_id))).scalar_one_or_none()
    if not acc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "账号不存在")
    for f in ("label", "daily_limit", "min_interval_sec", "status"):
        v = getattr(body, f)
        if v is not None:
            setattr(acc, f, v)
    if body.status == "active":
        acc.cooldown_until = None   # 手动恢复：清冷却, acquire 方可立即选中
    if body.credentials is not None:
        acc.credentials_encrypted = encrypt(json.dumps(body.credentials))
    await s.commit(); await s.refresh(acc)
    return acc

@router.delete("/{account_id}", status_code=204)
async def delete_account(account_id: int, s: AsyncSession = Depends(get_session), _: User = Depends(require_role("admin"))):
    acc = (await s.execute(select(SourceAccount).where(SourceAccount.id == account_id))).scalar_one_or_none()
    if acc:
        await s.delete(acc); await s.commit()

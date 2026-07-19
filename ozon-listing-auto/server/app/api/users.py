"""员工/用户管理 API(admin)：建/列/改角色·启停/重置密码/删；防锁死(保留可用 admin, 不操作自己)。"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.db import get_session
from app.core.security import hash_password
from app.api.deps import require_role
from app.models import User
from app.schemas.user import UserCreate, UserUpdate, PasswordReset, UserOut

router = APIRouter(prefix="/users", tags=["users"])
_ROLES = {"admin", "operator", "reviewer", "publisher"}


async def _active_admin_count(s: AsyncSession) -> int:
    return (await s.execute(select(func.count()).select_from(User).where(
        User.role == "admin", User.is_active == True))).scalar_one()   # noqa: E712


async def _get(s: AsyncSession, uid: int) -> User:
    u = (await s.execute(select(User).where(User.id == uid))).scalar_one_or_none()
    if not u:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "用户不存在")
    return u


@router.get("", response_model=list[UserOut])
async def list_users(s: AsyncSession = Depends(get_session), _: User = Depends(require_role("admin"))):
    return (await s.execute(select(User).order_by(User.id))).scalars().all()


@router.post("", response_model=UserOut)
async def create_user(body: UserCreate, s: AsyncSession = Depends(get_session), _: User = Depends(require_role("admin"))):
    if body.role not in _ROLES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"非法角色: {body.role}")
    exists = (await s.execute(select(User.id).where(User.username == body.username))).scalar_one_or_none()
    if exists:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "用户名已存在")
    u = User(username=body.username, password_hash=hash_password(body.password), role=body.role)
    s.add(u); await s.commit(); await s.refresh(u)
    return u


@router.put("/{uid}", response_model=UserOut)
async def update_user(uid: int, body: UserUpdate, s: AsyncSession = Depends(get_session),
                      cur: User = Depends(require_role("admin"))):
    u = await _get(s, uid)
    disabling = body.is_active is False
    demoting = body.role is not None and body.role != "admin"
    if (disabling or demoting) and u.role == "admin" and u.is_active:
        if uid == cur.id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "不能停用/降级当前登录的自己")
        if await _active_admin_count(s) <= 1:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "至少保留一个可用管理员")
    if body.role is not None:
        if body.role not in _ROLES:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"非法角色: {body.role}")
        u.role = body.role
    if body.is_active is not None:
        u.is_active = body.is_active
    await s.commit(); await s.refresh(u)
    return u


@router.post("/{uid}/password")
async def reset_password(uid: int, body: PasswordReset, s: AsyncSession = Depends(get_session),
                         _: User = Depends(require_role("admin"))):
    u = await _get(s, uid)
    u.password_hash = hash_password(body.password)
    await s.commit()
    return {"id": uid, "ok": True}


@router.delete("/{uid}")
async def delete_user(uid: int, s: AsyncSession = Depends(get_session), cur: User = Depends(require_role("admin"))):
    u = await _get(s, uid)
    if uid == cur.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "不能删除当前登录的自己")
    if u.role == "admin" and u.is_active and await _active_admin_count(s) <= 1:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "至少保留一个可用管理员")
    await s.delete(u); await s.commit()
    return {"id": uid, "ok": True}

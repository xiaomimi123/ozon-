"""FastAPI 依赖：当前登录用户解析与基于角色的访问控制。"""
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.db import get_session
from app.core.security import decode_token
from app.models import User

oauth2 = OAuth2PasswordBearer(tokenUrl="/auth/login")

async def get_current_user(token: str = Depends(oauth2), s: AsyncSession = Depends(get_session)) -> User:
    payload = decode_token(token)
    username = payload.get("sub")
    if not username:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "无效令牌")
    u = (await s.execute(select(User).where(User.username == username))).scalar_one_or_none()
    if not u or not u.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "用户不存在或停用")
    return u

def require_role(*roles: str):
    async def _dep(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles and user.role != "admin":
            raise HTTPException(status.HTTP_403_FORBIDDEN, "权限不足")
        return user
    return _dep

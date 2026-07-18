"""鉴权路由：登录签发 JWT、查询当前登录用户。"""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.db import get_session
from app.core.login_throttle import login_throttle
from app.core.security import verify_password, create_token
from app.models import User
from app.schemas.auth import TokenOut, UserOut
from app.api.deps import get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/login", response_model=TokenOut)
async def login(request: Request, form: OAuth2PasswordRequestForm = Depends(), s: AsyncSession = Depends(get_session)):
    ip = (request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
          or (request.client.host if request.client else "?"))   # 生产在 nginx 后, 取 XFF 首段
    key = f"{form.username}|{ip}"
    now = datetime.now(timezone.utc)
    remaining = login_throttle.check(key, now=now)
    if remaining is not None:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "登录尝试过多，请稍后再试",
                            headers={"Retry-After": str(remaining)})
    u = (await s.execute(select(User).where(User.username == form.username))).scalar_one_or_none()
    if not u or not verify_password(form.password, u.password_hash):
        login_throttle.record_failure(key, now=now)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "用户名或密码错误")
    login_throttle.reset(key)
    return TokenOut(access_token=create_token(u.username, u.role), role=u.role)

@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)):
    return UserOut(id=user.id, username=user.username, role=user.role)

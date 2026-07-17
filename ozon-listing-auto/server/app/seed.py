"""启动种子：确保系统存在首个管理员账号（幂等，可通过环境变量覆盖用户名/密码）。"""
import os
from sqlalchemy import select
from app.core.security import hash_password
from app.models import User

async def ensure_admin(session_factory) -> None:
    username = os.getenv("ADMIN_USER", "admin")
    password = os.getenv("ADMIN_PASSWORD", "admin123")
    async with session_factory() as s:
        exists = (await s.execute(select(User).where(User.username == username))).scalar_one_or_none()
        if not exists:
            s.add(User(username=username, password_hash=hash_password(password), role="admin"))
            await s.commit()

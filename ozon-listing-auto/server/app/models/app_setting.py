"""应用设置 ORM 模型：按 category/key 存储的加密配置项（如平台密钥、系统参数）。"""
from datetime import datetime

from sqlalchemy import String, Boolean, DateTime, LargeBinary, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class AppSetting(Base):
    __tablename__ = "app_settings"
    __table_args__ = (UniqueConstraint("category", "key", name="uq_category_key"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    category: Mapped[str] = mapped_column(String(32))
    key: Mapped[str] = mapped_column(String(64))
    value_encrypted: Mapped[bytes] = mapped_column(LargeBinary)
    is_secret: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_by: Mapped[int | None] = mapped_column(nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

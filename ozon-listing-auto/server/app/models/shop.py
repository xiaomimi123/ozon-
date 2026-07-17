"""Ozon 店铺凭据 ORM：Client-Id 明文 + Api-Key Fernet 加密。"""
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, LargeBinary, func
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db import Base

class Shop(Base):
    __tablename__ = "shops"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    platform: Mapped[str] = mapped_column(String(16), default="ozon")
    client_id: Mapped[str] = mapped_column(String(128))
    api_key_encrypted: Mapped[bytes] = mapped_column(LargeBinary)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_sandbox: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

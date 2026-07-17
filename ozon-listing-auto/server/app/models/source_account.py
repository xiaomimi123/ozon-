"""货源平台账号池 ORM：加密 cookie/会话 + 限速/冷却状态。"""
from datetime import datetime, date

from sqlalchemy import String, Integer, Boolean, DateTime, Date, LargeBinary, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class SourceAccount(Base):
    __tablename__ = "source_accounts"
    id: Mapped[int] = mapped_column(primary_key=True)
    platform: Mapped[str] = mapped_column(String(16), index=True)   # ali1688/pinduoduo
    label: Mapped[str | None] = mapped_column(String(128), nullable=True)
    credentials_encrypted: Mapped[bytes] = mapped_column(LargeBinary)
    status: Mapped[str] = mapped_column(String(16), default="active")  # active/cooldown/disabled
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    daily_used_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    daily_used_count: Mapped[int] = mapped_column(Integer, default=0)
    daily_limit: Mapped[int] = mapped_column(Integer, default=200)
    min_interval_sec: Mapped[int] = mapped_column(Integer, default=6)
    cooldown_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    risk_hits: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

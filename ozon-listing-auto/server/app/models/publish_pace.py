"""上架节奏配置 ORM（全局默认 task_id=null；按任务覆盖）。"""
from datetime import datetime
from sqlalchemy import Integer, Boolean, DateTime, ForeignKey, JSON, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db import Base

_JSONB = JSONB().with_variant(JSON(), "sqlite")

class PublishPace(Base):
    __tablename__ = "publish_pace"
    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int | None] = mapped_column(ForeignKey("collect_tasks.id"), nullable=True, index=True)
    min_interval_sec: Mapped[int] = mapped_column(Integer, default=60)
    max_interval_sec: Mapped[int] = mapped_column(Integer, default=180)
    daily_limit: Mapped[int] = mapped_column(Integer, default=200)
    active_hours: Mapped[list] = mapped_column(_JSONB, default=lambda: [9, 23])
    wait_ozon_approval: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

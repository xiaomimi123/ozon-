"""采集任务 ORM 模型：跟卖/铺货采集任务的配置、进度游标与统计信息。"""
from datetime import datetime

from sqlalchemy import JSON, String, Integer, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

# Postgres 用 JSONB，测试用的 SQLite 无 JSONB 类型，退化为通用 JSON。
_JSONB = JSONB().with_variant(JSON(), "sqlite")


class CollectTask(Base):
    __tablename__ = "collect_tasks"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    listing_mode: Mapped[str] = mapped_column(String(8), default="follow")   # follow/create
    entry_type: Mapped[str] = mapped_column(String(16))                       # keyword/category/seller/own_shop
    entry_value: Mapped[str] = mapped_column(String(512))
    provider: Mapped[str] = mapped_column(String(16), default="mock")         # mock/composer/apify
    source_platforms: Mapped[list] = mapped_column(_JSONB, default=list)
    review_config: Mapped[dict | None] = mapped_column(_JSONB, nullable=True)
    last_filter: Mapped[dict | None] = mapped_column(_JSONB, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="pending")        # pending/running/paused/done/failed
    cursor: Mapped[dict | None] = mapped_column(_JSONB, nullable=True)
    stats: Mapped[dict | None] = mapped_column(_JSONB, nullable=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

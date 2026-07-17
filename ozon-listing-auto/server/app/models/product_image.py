"""改图产物 ORM：候选源图经改图流水线处理后的产物 + 人工确认状态（§5.6）。"""
from datetime import datetime
from sqlalchemy import String, Integer, Text, DateTime, ForeignKey, Index, JSON, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db import Base

_JSONB = JSONB().with_variant(JSON(), "sqlite")


class ProductImage(Base):
    __tablename__ = "product_images"
    __table_args__ = (
        Index("ix_image_task_status", "task_id", "status"),
        Index("ix_image_candidate", "candidate_id"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("collect_tasks.id"), index=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("supply_candidates.id"))
    source_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    op: Mapped[str] = mapped_column(String(16))                # rmbg|whitebg|watermark|crop_norm|gen
    provider: Mapped[str] = mapped_column(String(16))          # local|openai_compat|http|mock
    result_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    sort: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending|processing|done|failed|approved|rejected
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    meta: Mapped[dict | None] = mapped_column(_JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

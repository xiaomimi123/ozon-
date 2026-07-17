"""跟卖上架草稿 ORM。"""
from datetime import datetime
from sqlalchemy import String, Integer, Numeric, Text, DateTime, ForeignKey, UniqueConstraint, Index, JSON, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db import Base

_JSONB = JSONB().with_variant(JSON(), "sqlite")

class ListingDraft(Base):
    __tablename__ = "listing_drafts"
    __table_args__ = (
        UniqueConstraint("task_id", "candidate_id", name="uq_draft_candidate"),
        Index("ix_draft_task_status", "task_id", "status"),
        Index("ix_draft_shop", "shop_id"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("collect_tasks.id"), index=True)
    ozon_product_id: Mapped[int] = mapped_column(ForeignKey("ozon_products.id"))
    candidate_id: Mapped[int] = mapped_column(ForeignKey("supply_candidates.id"))
    shop_id: Mapped[int | None] = mapped_column(ForeignKey("shops.id"), nullable=True)
    mode: Mapped[str] = mapped_column(String(8), default="follow")
    target_ozon_sku: Mapped[str | None] = mapped_column(String(64), nullable=True)
    barcode: Mapped[str | None] = mapped_column(String(64), nullable=True)
    price: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(8), default="RUB")
    stock_qty: Mapped[int] = mapped_column(Integer, default=0)
    cost: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    margin: Mapped[float | None] = mapped_column(Numeric(6, 4), nullable=True)
    pricing_detail: Mapped[dict | None] = mapped_column(_JSONB, nullable=True)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="draft")
    ozon_result: Mapped[dict | None] = mapped_column(_JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

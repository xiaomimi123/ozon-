"""货源候选 ORM：跨平台候选 + CLIP 向量 + 去重分组。"""
from datetime import datetime

from sqlalchemy import String, Integer, Float, Boolean, DateTime, ForeignKey, UniqueConstraint, Index, func, JSON
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from pgvector.sqlalchemy import Vector

from app.core.db import Base

EMBED_DIM = 512
_JSONB = JSONB().with_variant(JSON(), "sqlite")
_VECTOR = Vector(EMBED_DIM).with_variant(JSON(), "sqlite")


class SupplyCandidate(Base):
    __tablename__ = "supply_candidates"
    __table_args__ = (
        UniqueConstraint("task_id", "ozon_product_id", "platform", "offer_id", name="uq_candidate"),
        Index("ix_candidate_product", "task_id", "ozon_product_id"),
        Index("ix_candidate_product_platform", "ozon_product_id", "platform"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("collect_tasks.id"), index=True)
    ozon_product_id: Mapped[int] = mapped_column(ForeignKey("ozon_products.id"), index=True)
    platform: Mapped[str] = mapped_column(String(16))
    offer_id: Mapped[str] = mapped_column(String(64))
    title: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    quantity_begin: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quantity_prices: Mapped[list | None] = mapped_column(_JSONB, nullable=True)
    image_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    images: Mapped[list | None] = mapped_column(_JSONB, nullable=True)
    phash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    embedding: Mapped[list | None] = mapped_column(_VECTOR, nullable=True)
    detail_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    supplier_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    supplier_info: Mapped[dict | None] = mapped_column(_JSONB, nullable=True)
    dedup_group: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_representative: Mapped[bool] = mapped_column(Boolean, default=True)
    source_account_id: Mapped[int | None] = mapped_column(ForeignKey("source_accounts.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="candidate")
    raw: Mapped[dict | None] = mapped_column(_JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

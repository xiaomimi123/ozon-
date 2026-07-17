"""Ozon 商品 ORM 模型：采集到的商品明细、图片/属性等 JSON 字段与去重索引。"""
from datetime import datetime

from sqlalchemy import JSON, String, Integer, Float, DateTime, ForeignKey, UniqueConstraint, Index, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from pgvector.sqlalchemy import Vector

from app.core.db import Base
from app.models.supply_candidate import EMBED_DIM

# Postgres 用 JSONB，测试用的 SQLite 无 JSONB 类型，退化为通用 JSON。
_JSONB = JSONB().with_variant(JSON(), "sqlite")
# pgvector 在 SQLite 下不可用，退化为 JSON 存储浮点数组（供 M3 图片相似度评分使用）。
_VECTOR = Vector(EMBED_DIM).with_variant(JSON(), "sqlite")


class OzonProduct(Base):
    __tablename__ = "ozon_products"
    __table_args__ = (
        UniqueConstraint("task_id", "sku", name="uq_task_sku"),
        Index("ix_task_parent", "task_id", "parent_sku"),
        Index("ix_product_phash", "phash"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("collect_tasks.id"), index=True)
    sku: Mapped[str] = mapped_column(String(64))
    product_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    title: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    sales_monthly: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    reviews_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    weight: Mapped[float | None] = mapped_column(Float, nullable=True)
    listed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    follow_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    return_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    main_image_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    images: Mapped[list | None] = mapped_column(_JSONB, nullable=True)
    attributes: Mapped[dict | None] = mapped_column(_JSONB, nullable=True)
    parent_sku: Mapped[str | None] = mapped_column(String(64), nullable=True)
    phash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    embedding: Mapped[list | None] = mapped_column(_VECTOR, nullable=True)
    barcode: Mapped[str | None] = mapped_column(String(64), nullable=True)
    raw: Mapped[dict | None] = mapped_column(_JSONB, nullable=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

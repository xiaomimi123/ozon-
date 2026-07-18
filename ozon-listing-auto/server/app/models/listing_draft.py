"""跟卖上架草稿 ORM。"""
from datetime import datetime, timezone
from sqlalchemy import String, Integer, Numeric, Text, DateTime, ForeignKey, UniqueConstraint, Index, JSON, TypeDecorator, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db import Base

_JSONB = JSONB().with_variant(JSON(), "sqlite")


class _UTCDateTime(TypeDecorator):
    """SQLite 不落盘时区偏移(读出恒为 naive)，此处读回后补 UTC，
    使 scheduled_at 在跨 session 重新查询后仍可与 tz-aware 的 now 比较(§5.9 调度)，
    行为对齐 Postgres 原生 TIMESTAMPTZ；对 Postgres 无影响(读出已带 tzinfo)。"""
    impl = DateTime(timezone=True)
    cache_ok = True

    def process_result_value(self, value, dialect):
        if value is not None and value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value


class ListingDraft(Base):
    __tablename__ = "listing_drafts"
    __table_args__ = (
        UniqueConstraint("task_id", "candidate_id", name="uq_draft_candidate"),
        Index("ix_draft_task_status", "task_id", "status"),
        Index("ix_draft_shop", "shop_id"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("collect_tasks.id"), index=True)
    ozon_product_id: Mapped[int | None] = mapped_column(ForeignKey("ozon_products.id"), nullable=True)  # 自建无跟卖目标卡
    candidate_id: Mapped[int] = mapped_column(ForeignKey("supply_candidates.id"))
    shop_id: Mapped[int | None] = mapped_column(ForeignKey("shops.id"), nullable=True)
    mode: Mapped[str] = mapped_column(String(8), default="follow")
    target_ozon_sku: Mapped[str | None] = mapped_column(String(64), nullable=True)
    barcode: Mapped[str | None] = mapped_column(String(64), nullable=True)
    title: Mapped[str | None] = mapped_column(String(1024), nullable=True)         # 自建：译后标题
    description: Mapped[str | None] = mapped_column(Text, nullable=True)           # 自建：描述
    category_id: Mapped[int | None] = mapped_column(Integer, nullable=True)        # 自建：Ozon 类目 id
    attributes: Mapped[dict | None] = mapped_column(_JSONB, nullable=True)         # 自建：类目属性 {attr_id: value}
    images: Mapped[list | None] = mapped_column(_JSONB, nullable=True)             # 自建：已确认图片 url 列表(有序)
    price: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(8), default="RUB")
    stock_qty: Mapped[int] = mapped_column(Integer, default=0)
    cost: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    margin: Mapped[float | None] = mapped_column(Numeric(6, 4), nullable=True)
    pricing_detail: Mapped[dict | None] = mapped_column(_JSONB, nullable=True)
    scheduled_at: Mapped[datetime | None] = mapped_column(_UTCDateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="draft")
    ozon_result: Mapped[dict | None] = mapped_column(_JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

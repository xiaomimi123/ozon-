"""1688 采集 PoC：原始采集 payload（ImportCapture）与解析后商品（ImportedProduct），独立于 SupplyCandidate 流。"""
from datetime import datetime
from sqlalchemy import String, Integer, Numeric, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db import Base

_JSONB = JSONB().with_variant(JSON(), "sqlite")

class ImportCapture(Base):
    __tablename__ = "import_captures"
    id: Mapped[int] = mapped_column(primary_key=True)
    platform: Mapped[str] = mapped_column(String(16), index=True)
    keyword: Mapped[str | None] = mapped_column(String(256), nullable=True)
    raw: Mapped[dict | None] = mapped_column(_JSONB, nullable=True)
    item_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class ImportedProduct(Base):
    __tablename__ = "imported_products"
    __table_args__ = ({"sqlite_autoincrement": True},)
    id: Mapped[int] = mapped_column(primary_key=True)
    platform: Mapped[str] = mapped_column(String(16), index=True)
    offer_id: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    price: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    image_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    shop_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    detail_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    sales: Mapped[int | None] = mapped_column(Integer, nullable=True)
    raw: Mapped[dict | None] = mapped_column(_JSONB, nullable=True)
    capture_id: Mapped[int | None] = mapped_column(ForeignKey("import_captures.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

"""类目属性映射记忆表 ORM：源线索→已确认 Ozon 类目/属性，跨任务复用（§5.7）。"""
from datetime import datetime
from sqlalchemy import String, Integer, Text, Boolean, DateTime, JSON, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db import Base

_JSONB = JSONB().with_variant(JSON(), "sqlite")


class CategoryMap(Base):
    __tablename__ = "category_maps"
    id: Mapped[int] = mapped_column(primary_key=True)
    signature: Mapped[str] = mapped_column(String(256), unique=True)   # 归一化签名(源类目名/标题关键词)
    source_hint: Mapped[str | None] = mapped_column(Text, nullable=True)
    ozon_category_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ozon_category_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    attributes: Mapped[dict | None] = mapped_column(_JSONB, nullable=True)
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    usage_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

"""m1 init"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None


def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.create_table("users",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("username", sa.String(64), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(256), nullable=False),
        sa.Column("role", sa.String(16), server_default="operator"),
        sa.Column("is_active", sa.Boolean, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table("collect_tasks",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("listing_mode", sa.String(8), server_default="follow"),
        sa.Column("entry_type", sa.String(16), nullable=False),
        sa.Column("entry_value", sa.String(512), nullable=False),
        sa.Column("provider", sa.String(16), server_default="mock"),
        sa.Column("source_platforms", postgresql.JSONB, server_default="[]"),
        sa.Column("review_config", postgresql.JSONB, nullable=True),
        sa.Column("last_filter", postgresql.JSONB, nullable=True),
        sa.Column("status", sa.String(16), server_default="pending"),
        sa.Column("cursor", postgresql.JSONB, nullable=True),
        sa.Column("stats", postgresql.JSONB, nullable=True),
        sa.Column("created_by", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table("ozon_products",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("task_id", sa.Integer, sa.ForeignKey("collect_tasks.id"), nullable=False, index=True),
        sa.Column("sku", sa.String(64), nullable=False),
        sa.Column("product_url", sa.String(512)), sa.Column("title", sa.String(1024)),
        sa.Column("price", sa.Float), sa.Column("currency", sa.String(8)),
        sa.Column("sales_monthly", sa.Integer), sa.Column("rating", sa.Float),
        sa.Column("reviews_count", sa.Integer), sa.Column("weight", sa.Float),
        sa.Column("listed_at", sa.DateTime(timezone=True)),
        sa.Column("follow_count", sa.Integer), sa.Column("return_rate", sa.Float),
        sa.Column("main_image_url", sa.String(512)), sa.Column("images", postgresql.JSONB),
        sa.Column("attributes", postgresql.JSONB), sa.Column("parent_sku", sa.String(64)),
        sa.Column("phash", sa.String(64)), sa.Column("raw", postgresql.JSONB),
        sa.Column("collected_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("task_id", "sku", name="uq_task_sku"),
    )
    op.create_index("ix_task_parent", "ozon_products", ["task_id", "parent_sku"])
    op.create_index("ix_product_phash", "ozon_products", ["phash"])
    op.create_table("app_settings",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("key", sa.String(64), nullable=False),
        sa.Column("value_encrypted", sa.LargeBinary, nullable=False),
        sa.Column("is_secret", sa.Boolean, server_default=sa.true()),
        sa.Column("updated_by", sa.Integer, nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("category", "key", name="uq_category_key"),
    )


def downgrade():
    for t in ["app_settings", "ozon_products", "collect_tasks", "users"]:
        op.drop_table(t)

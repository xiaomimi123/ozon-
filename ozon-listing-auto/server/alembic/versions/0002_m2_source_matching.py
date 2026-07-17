"""m2 source matching"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from pgvector.sqlalchemy import Vector

revision = "0002"
down_revision = "0001"


def upgrade():
    op.create_table("source_accounts",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("platform", sa.String(16), nullable=False, index=True),
        sa.Column("label", sa.String(128)),
        sa.Column("credentials_encrypted", sa.LargeBinary, nullable=False),
        sa.Column("status", sa.String(16), server_default="active"),
        sa.Column("last_used_at", sa.DateTime(timezone=True)),
        sa.Column("daily_used_date", sa.Date),
        sa.Column("daily_used_count", sa.Integer, server_default="0"),
        sa.Column("daily_limit", sa.Integer, server_default="200"),
        sa.Column("min_interval_sec", sa.Integer, server_default="6"),
        sa.Column("cooldown_until", sa.DateTime(timezone=True)),
        sa.Column("risk_hits", sa.Integer, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table("supply_candidates",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("task_id", sa.Integer, sa.ForeignKey("collect_tasks.id"), nullable=False, index=True),
        sa.Column("ozon_product_id", sa.Integer, sa.ForeignKey("ozon_products.id"), nullable=False, index=True),
        sa.Column("platform", sa.String(16), nullable=False),
        sa.Column("offer_id", sa.String(64), nullable=False),
        sa.Column("title", sa.String(1024)), sa.Column("price", sa.Float), sa.Column("currency", sa.String(8)),
        sa.Column("quantity_begin", sa.Integer), sa.Column("quantity_prices", postgresql.JSONB),
        sa.Column("image_url", sa.String(512)), sa.Column("images", postgresql.JSONB),
        sa.Column("phash", sa.String(64)), sa.Column("embedding", Vector(512)),
        sa.Column("detail_url", sa.String(512)), sa.Column("supplier_name", sa.String(256)),
        sa.Column("supplier_info", postgresql.JSONB),
        sa.Column("dedup_group", sa.Integer), sa.Column("is_representative", sa.Boolean, server_default=sa.true()),
        sa.Column("source_account_id", sa.Integer, sa.ForeignKey("source_accounts.id")),
        sa.Column("status", sa.String(16), server_default="candidate"),
        sa.Column("raw", postgresql.JSONB),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("task_id", "ozon_product_id", "platform", "offer_id", name="uq_candidate"),
    )
    op.create_index("ix_candidate_product", "supply_candidates", ["task_id", "ozon_product_id"])
    op.create_index("ix_candidate_product_platform", "supply_candidates", ["ozon_product_id", "platform"])
    op.add_column("collect_tasks", sa.Column("match_status", sa.String(16), server_default="pending"))
    op.add_column("collect_tasks", sa.Column("match_cursor", postgresql.JSONB))
    op.add_column("collect_tasks", sa.Column("match_stats", postgresql.JSONB))


def downgrade():
    op.drop_column("collect_tasks", "match_stats")
    op.drop_column("collect_tasks", "match_cursor")
    op.drop_column("collect_tasks", "match_status")
    op.drop_table("supply_candidates")
    op.drop_table("source_accounts")

"""m4 pricing publish"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0004"
down_revision = "0003"

def upgrade():
    op.create_table("shops",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("platform", sa.String(16), server_default="ozon", nullable=False),
        sa.Column("client_id", sa.String(128), nullable=False),
        sa.Column("api_key_encrypted", sa.LargeBinary, nullable=False),
        sa.Column("is_active", sa.Boolean, server_default=sa.true(), nullable=False),
        sa.Column("is_sandbox", sa.Boolean, server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.add_column("ozon_products", sa.Column("barcode", sa.String(64)))
    op.create_table("listing_drafts",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("task_id", sa.Integer, sa.ForeignKey("collect_tasks.id"), nullable=False, index=True),
        sa.Column("ozon_product_id", sa.Integer, sa.ForeignKey("ozon_products.id"), nullable=False),
        sa.Column("candidate_id", sa.Integer, sa.ForeignKey("supply_candidates.id"), nullable=False),
        sa.Column("shop_id", sa.Integer, sa.ForeignKey("shops.id")),
        sa.Column("mode", sa.String(8), server_default="follow", nullable=False),
        sa.Column("target_ozon_sku", sa.String(64)),
        sa.Column("barcode", sa.String(64)),
        sa.Column("price", sa.Numeric(14, 2)),
        sa.Column("currency", sa.String(8), server_default="RUB", nullable=False),
        sa.Column("stock_qty", sa.Integer, server_default="0", nullable=False),
        sa.Column("cost", sa.Numeric(14, 2)),
        sa.Column("margin", sa.Numeric(6, 4)),
        sa.Column("pricing_detail", postgresql.JSONB),
        sa.Column("scheduled_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(16), server_default="draft", nullable=False),
        sa.Column("ozon_result", postgresql.JSONB),
        sa.Column("error", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("task_id", "candidate_id", name="uq_draft_candidate"),
    )
    op.create_index("ix_draft_task_status", "listing_drafts", ["task_id", "status"])
    op.create_index("ix_draft_shop", "listing_drafts", ["shop_id"])

def downgrade():
    op.drop_table("listing_drafts")
    op.drop_column("ozon_products", "barcode")
    op.drop_table("shops")

"""import poc: import_captures, imported_products"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0008"
down_revision = "0007"


def upgrade():
    op.create_table("import_captures",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("platform", sa.String(16), nullable=False, index=True),
        sa.Column("keyword", sa.String(256), nullable=True),
        sa.Column("raw", postgresql.JSONB, nullable=True),
        sa.Column("item_count", sa.Integer, server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table("imported_products",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("platform", sa.String(16), nullable=False, index=True),
        sa.Column("offer_id", sa.String(64), nullable=False, index=True),
        sa.Column("title", sa.String(1024), nullable=True),
        sa.Column("price", sa.Numeric(14, 2), nullable=True),
        sa.Column("image_url", sa.String(1024), nullable=True),
        sa.Column("shop_name", sa.String(256), nullable=True),
        sa.Column("detail_url", sa.String(1024), nullable=True),
        sa.Column("sales", sa.Integer, nullable=True),
        sa.Column("raw", postgresql.JSONB, nullable=True),
        sa.Column("capture_id", sa.Integer, sa.ForeignKey("import_captures.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("platform", "offer_id", name="uq_imported_offer"),
    )


def downgrade():
    op.drop_table("imported_products")
    op.drop_table("import_captures")

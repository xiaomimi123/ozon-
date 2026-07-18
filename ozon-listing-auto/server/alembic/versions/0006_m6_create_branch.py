"""m6 create branch: product_images, category_maps, listing_drafts create 字段"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0006"
down_revision = "0005"


def upgrade():
    op.add_column("listing_drafts", sa.Column("title", sa.String(1024), nullable=True))
    op.add_column("listing_drafts", sa.Column("description", sa.Text, nullable=True))
    op.add_column("listing_drafts", sa.Column("category_id", sa.Integer, nullable=True))
    op.add_column("listing_drafts", sa.Column("attributes", postgresql.JSONB, nullable=True))
    op.add_column("listing_drafts", sa.Column("images", postgresql.JSONB, nullable=True))
    op.alter_column("listing_drafts", "ozon_product_id", existing_type=sa.Integer, nullable=True)

    op.create_table("product_images",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("task_id", sa.Integer, sa.ForeignKey("collect_tasks.id"), index=True),
        sa.Column("candidate_id", sa.Integer, sa.ForeignKey("supply_candidates.id")),
        sa.Column("source_url", sa.String(512), nullable=True),
        sa.Column("op", sa.String(16), nullable=False),
        sa.Column("provider", sa.String(16), nullable=False),
        sa.Column("result_url", sa.String(512), nullable=True),
        sa.Column("sort", sa.Integer, server_default="0", nullable=False),
        sa.Column("status", sa.String(16), server_default="pending", nullable=False),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("meta", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_image_task_status", "product_images", ["task_id", "status"])
    op.create_index("ix_image_candidate", "product_images", ["candidate_id"])

    op.create_table("category_maps",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("signature", sa.String(256), nullable=False, unique=True),
        sa.Column("source_hint", sa.Text, nullable=True),
        sa.Column("ozon_category_id", sa.Integer, nullable=True),
        sa.Column("ozon_category_path", sa.String(512), nullable=True),
        sa.Column("attributes", postgresql.JSONB, nullable=True),
        sa.Column("confirmed", sa.Boolean, server_default=sa.false(), nullable=False),
        sa.Column("usage_count", sa.Integer, server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade():
    op.drop_table("category_maps")
    op.drop_index("ix_image_candidate", table_name="product_images")
    op.drop_index("ix_image_task_status", table_name="product_images")
    op.drop_table("product_images")
    op.alter_column("listing_drafts", "ozon_product_id", existing_type=sa.Integer, nullable=False)
    for col in ("images", "attributes", "category_id", "description", "title"):
        op.drop_column("listing_drafts", col)

"""m3 scoring review"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from pgvector.sqlalchemy import Vector

revision = "0003"
down_revision = "0002"


def upgrade():
    op.add_column("ozon_products", sa.Column("embedding", Vector(512)))
    for col in ["score_image", "score_title", "score_attr", "score_price", "score_supplier", "score_total"]:
        op.add_column("supply_candidates", sa.Column(col, sa.Float))
    op.add_column("supply_candidates", sa.Column("tier", sa.String(16)))
    op.add_column("supply_candidates", sa.Column("score_detail", postgresql.JSONB))
    op.add_column("collect_tasks", sa.Column("score_status", sa.String(16), server_default="pending", nullable=False))
    op.add_column("collect_tasks", sa.Column("score_cursor", postgresql.JSONB))
    op.add_column("collect_tasks", sa.Column("score_stats", postgresql.JSONB))
    op.create_table("review_decisions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("task_id", sa.Integer, sa.ForeignKey("collect_tasks.id"), nullable=False, index=True),
        sa.Column("ozon_product_id", sa.Integer, sa.ForeignKey("ozon_products.id"), nullable=False),
        sa.Column("candidate_id", sa.Integer, sa.ForeignKey("supply_candidates.id"), nullable=False),
        sa.Column("reviewer_id", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("decision", sa.String(16), nullable=False),
        sa.Column("note", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_review_task_product", "review_decisions", ["task_id", "ozon_product_id"])
    op.create_index("ix_review_candidate", "review_decisions", ["candidate_id"])


def downgrade():
    op.drop_table("review_decisions")
    for col in ["score_stats", "score_cursor", "score_status"]:
        op.drop_column("collect_tasks", col)
    for col in ["score_detail", "tier", "score_total", "score_supplier", "score_price", "score_attr", "score_title", "score_image"]:
        op.drop_column("supply_candidates", col)
    op.drop_column("ozon_products", "embedding")
